"""Poner un modo y configurarlos.

Poner un modo pide el mismo permiso que armar: un modo puede armar la casa,
apagar luces y cerrar puertas de una sola pulsación, así que no es menos
importante que el botón de la alarma. Editarlos, en cambio, es configuración.
"""
import reflex as rx

from . import store
from ..auth import permisos
from ..automations import actions
from ..automations import store as auto_store
from ..security import audit, logs


async def aplicar(modo_id: str, quien: str = audit.SISTEMA) -> tuple[bool, str]:
    """Pone el modo y lanza sus reglas. Devuelve (salió bien, resumen).

    Las reglas se lanzan con el mismo dispatch que usa el motor —una acción
    «ejecutar regla»—, no con un ejecutor propio: si algún día cambia lo que
    significa ejecutar una regla, los modos cambian con ello sin enterarse.

    El modo se guarda ANTES de lanzar nada. Es a propósito: las reglas del modo
    pueden mirar en qué modo está la casa, y si se guardara después verían
    todavía el anterior. Además, si una regla falla, el modo ya está puesto y
    la casa no se queda a medio camino sin que se sepa en cuál.
    """
    modo = store.get(modo_id)
    if modo is None:
        return False, "Ese modo ya no existe."

    store.poner_activo(modo_id, quien)

    fallos = []
    hechas = 0
    for regla_id in modo.get("reglas", []):
        if auto_store.get_rule(regla_id) is None:
            fallos.append("una regla que ya no existe")
            continue
        try:
            await actions.dispatch({"type": "rule.run", "target": f"rule:{regla_id}"})
            hechas += 1
        except Exception as e:
            regla = auto_store.get_rule(regla_id) or {}
            fallos.append(f"{regla.get('name', regla_id)}: {e}")

    resumen = f"{hechas} regla(s)" if hechas else "sin reglas"
    if fallos:
        resumen += f" — falló {len(fallos)}: {'; '.join(fallos[:3])}"
    logs.registrar(logs.SISTEMA, "MODO_CAMBIADO", quien,
                   f"{modo['nombre']} — {resumen}")
    return not fallos, resumen


class ModesState(rx.State):
    modos: list[dict] = []
    activo: str = ""
    aplicando: str = ""

    # Editor
    editando: str = ""
    ed_nombre: str = ""
    ed_descripcion: str = ""
    ed_reglas: list[str] = []
    reglas_disponibles: list[dict] = []

    @rx.event
    def on_load(self):
        self._recargar()

    def _recargar(self):
        datos = store.leer()
        self.activo = datos.get("activo", "")
        self.modos = [
            {
                "id": m["id"],
                "nombre": m["nombre"],
                "icono": m.get("icono", "house"),
                "color": m.get("color", "#38bdf8"),
                "descripcion": m.get("descripcion", ""),
                "activo": m["id"] == self.activo,
                # Ya contado aquí: hacerlo en la vista obligaría a componer
                # texto dentro de un foreach, que es justo lo que rompe.
                "resumen": _resumen_reglas(m.get("reglas", [])),
            }
            for m in sorted(datos["modos"], key=lambda m: m.get("orden", 0))
        ]

    @rx.event(background=True)
    async def poner(self, modo_id: str):
        """Pone un modo. En segundo plano porque sus reglas pueden tardar
        (un SSH, un pulso de puerta) y el botón no debe congelar la pantalla."""
        async with self:
            no = await permisos.denegar(self, permisos.ARMAR)
        if no:
            yield no
            return

        async with self:
            self.aplicando = modo_id
            quien = await audit.usuario_de(self)

        ok, resumen = await aplicar(modo_id, quien)

        async with self:
            self.aplicando = ""
            self._recargar()
            nombre = next((m["nombre"] for m in self.modos if m["id"] == modo_id),
                          "el modo")
        if ok:
            yield rx.toast.success(f"Casa en «{nombre}» · {resumen}",
                                   position="top-center")
        else:
            yield rx.toast.error(f"«{nombre}»: {resumen}",
                                 position="top-center", duration=10000)

    # ── Editor ───────────────────────────────────────────────────────────
    @rx.event
    def abrir_editor(self, modo_id: str):
        modo = store.get(modo_id)
        if modo is None:
            return
        self.editando = modo_id
        self.ed_nombre = modo["nombre"]
        self.ed_descripcion = modo.get("descripcion", "")
        self.ed_reglas = list(modo.get("reglas", []))
        self.reglas_disponibles = [
            {"id": r["id"], "nombre": r.get("name", r["id"]),
             "elegida": r["id"] in self.ed_reglas}
            for r in auto_store.read_all()
        ]

    @rx.event
    def cerrar_editor(self):
        self.editando = ""

    @rx.event
    def set_ed_nombre(self, v: str):
        self.ed_nombre = v

    @rx.event
    def set_ed_descripcion(self, v: str):
        self.ed_descripcion = v

    @rx.event
    def alternar_regla(self, regla_id: str):
        if regla_id in self.ed_reglas:
            self.ed_reglas = [r for r in self.ed_reglas if r != regla_id]
        else:
            self.ed_reglas = [*self.ed_reglas, regla_id]
        self.reglas_disponibles = [
            {**r, "elegida": r["id"] in self.ed_reglas}
            for r in self.reglas_disponibles
        ]

    @rx.event
    async def guardar(self):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        if not self.editando:
            return
        store.editar(self.editando, nombre=self.ed_nombre,
                     descripcion=self.ed_descripcion, reglas=self.ed_reglas)
        nombre = self.ed_nombre
        self.editando = ""
        self._recargar()
        await audit.registrar(self, logs.SISTEMA, "MODO_EDITADO", nombre)
        return rx.toast.success(f"Modo «{nombre}» guardado.",
                                position="top-center")

    @rx.event
    async def crear(self):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        modo = store.crear("Modo nuevo")
        self._recargar()
        self.abrir_editor(modo["id"])
        return rx.toast.success("Modo creado. Ponle nombre y sus reglas.",
                                position="top-center")

    @rx.event
    async def borrar(self, modo_id: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        modo = store.get(modo_id) or {}
        store.borrar(modo_id)
        if self.editando == modo_id:
            self.editando = ""
        self._recargar()
        await audit.registrar(self, logs.SISTEMA, "MODO_BORRADO",
                              modo.get("nombre", modo_id))
        return rx.toast.success("Modo borrado.", position="top-center")


def _resumen_reglas(ids: list[str]) -> str:
    vivas = [r for r in ids if auto_store.get_rule(r) is not None]
    if not vivas:
        return "sin reglas todavía"
    if len(vivas) == 1:
        regla = auto_store.get_rule(vivas[0]) or {}
        return f"lanza «{regla.get('name', '?')}»"
    return f"lanza {len(vivas)} reglas"
