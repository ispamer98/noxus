"""Pestaña «Estancias»: qué muestra la pantalla de cada habitación y cómo.

Cada cambio se guarda al instante en la ficha de la estancia (nodes/store.py) y
lo recoge la tablet sola. Todo exige AJUSTES.
"""
import reflex as rx

from ..auth import permisos
from ..security import audit, logs
from . import store
from .state import _ROOM_FAMILIES, _build_room_catalog

_OPCIONES = ("plano", "camaras", "sirena", "hora")


class EstanciasState(rx.State):
    salas: list[dict] = []
    sel: str = ""
    nombre: str = ""
    op_plano: bool = True
    op_camaras: bool = True
    op_sirena: bool = True
    op_hora: bool = True
    op_baldosas: str = "normales"
    sirena_activa: bool = False
    sirena_sonido: str = "sirena"
    sirena_volumen: str = "75"
    miembros: list[dict] = []
    catalogo: list[dict] = []
    anadiendo: bool = False
    nueva: str = ""

    def _sala(self, datos: dict) -> dict:
        return next((r for r in datos["rooms"] if r["id"] == self.sel), {})

    def _cargar(self) -> None:
        datos = store.read_all()
        self.salas = [{"id": r["id"], "name": r.get("name", r["id"]),
                       "total": len(store.referencias_estancia(r["id"], datos))}
                      for r in datos["rooms"]]
        if self.sel not in {r["id"] for r in datos["rooms"]}:
            self.sel = datos["rooms"][0]["id"] if datos["rooms"] else ""
        sala = self._sala(datos)
        if not sala:
            self.miembros, self.catalogo, self.nombre = [], [], ""
            return
        self.nombre = sala.get("name", "")
        p = store.get_room_pantalla(self.sel)
        self.op_plano, self.op_camaras = p["plano"], p["camaras"]
        self.op_sirena, self.op_hora = p["sirena"], p["hora"]
        self.op_baldosas = p["baldosas"]
        s = store.get_room_sirena(self.sel)
        self.sirena_activa, self.sirena_sonido = s["activa"], s["sonido"]
        self.sirena_volumen = s["volumen"]

        automaticas = {f"lights:{i['id']}" for i in datos["lights"]
                       if i.get("room_id") == self.sel}
        explicitas = list(sala.get("entidades") or [])
        pers = sala.get("personalizado") or {}
        orden = sala.get("orden") or []
        filas = []
        for coleccion, familia, _icono in _ROOM_FAMILIES:
            for item in datos[coleccion]:
                ref = f"{coleccion}:{item['id']}"
                if ref not in automaticas and ref not in explicitas:
                    continue
                ficha = pers.get(ref) or {}
                filas.append({
                    "ref": ref, "nombre": item.get("name") or item.get("label") or item["id"],
                    "familia": familia, "automatico": ref in automaticas,
                    "visible": not ficha.get("oculto"), "etiqueta": ficha.get("etiqueta", ""),
                })
        filas.sort(key=lambda m: orden.index(m["ref"]) if m["ref"] in orden else len(orden))
        self.miembros = filas
        self.catalogo = [
            {"label": f"{sec['label']} · {op['label']}", "value": op["value"]}
            for sec in _build_room_catalog(datos, self.sel, set(explicitas))
            for op in sec["options"]
        ]

    async def _anotar(self, detalle: str) -> None:
        await audit.registrar(self, logs.SISTEMA, "ESTANCIA_EDITADA", detalle)

    @rx.event
    async def cargar(self):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        self._cargar()

    @rx.event
    async def seleccionar(self, sala_id: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        self.sel, self.anadiendo = sala_id, False
        self._cargar()

    @rx.event
    async def crear(self, form_data: dict):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        nombre = " ".join(str(form_data.get("name", "")).split())[:40]
        if not nombre:
            return
        self.sel = store.add_room(nombre)["id"]
        self._cargar()
        await self._anotar(f"Estancia «{nombre}» creada")

    @rx.event
    async def renombrar(self, valor: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        nombre = " ".join(str(valor).split())[:40]
        sala = self._sala(store.read_all())
        if not sala or not nombre or nombre == sala.get("name"):
            return
        store.update_room(self.sel, nombre, sala.get("entidades") or [])
        self._cargar()
        await self._anotar(f"Estancia renombrada a «{nombre}»")

    @rx.event
    async def borrar(self):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        if not self.sel:
            return
        nombre = self.nombre
        store.delete_room(self.sel)
        self.sel = ""
        self._cargar()
        await self._anotar(f"Estancia «{nombre}» eliminada")

    @rx.event
    async def alternar_opcion(self, clave: str):
        if clave not in _OPCIONES:
            return
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        actual = store.get_room_pantalla(self.sel)[clave]
        store.set_room_pantalla(self.sel, clave, not actual)
        self._cargar()
        await self._anotar(f"{self.nombre}: «{clave}» {'oculto' if actual else 'visible'}")

    @rx.event
    async def elegir_baldosas(self, valor: str):
        if valor not in store.ESTANCIA_BALDOSAS:
            return
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        store.set_room_pantalla(self.sel, "baldosas", valor)
        self._cargar()

    async def _guardar_sirena(self, activa: bool, sonido: str, volumen: str) -> None:
        store.set_room_sirena(self.sel, activa, sonido, volumen)
        self._cargar()
        await self._anotar(f"{self.nombre}: sirena {'activada' if activa else 'desactivada'}, "
                           f"{sonido}, volumen {volumen}")

    @rx.event
    async def sirena_alternar(self):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        await self._guardar_sirena(not self.sirena_activa, self.sirena_sonido, self.sirena_volumen)

    @rx.event
    async def sirena_sonido_elegir(self, valor: str):
        if valor not in store.SIRENA_SONIDOS:
            return
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        await self._guardar_sirena(self.sirena_activa, valor, self.sirena_volumen)

    @rx.event
    async def sirena_volumen_elegir(self, valor: str):
        if valor not in store.SIRENA_VOLUMENES:
            return
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        await self._guardar_sirena(self.sirena_activa, self.sirena_sonido, valor)

    @rx.event
    async def sirena_probar(self):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        if not self.sel:
            return
        store.probar_sirena(self.sel)
        await self._anotar(f"{self.nombre}: prueba de tono en la tablet")
        return rx.toast.info("Prueba enviada: la tablet sonará unos segundos si está abierta "
                             "y ya se ha tocado su pantalla.")

    def _es_miembro(self, ref: str) -> bool:
        return any(m["ref"] == ref for m in self.miembros)

    @rx.event
    async def miembro_visible(self, ref: str, visible: bool):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        if self._es_miembro(ref):
            store.set_room_miembro(self.sel, ref, oculto=not visible)
            self._cargar()

    @rx.event
    async def miembro_etiqueta(self, ref: str, texto: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        actual = next((m["etiqueta"] for m in self.miembros if m["ref"] == ref), None)
        if actual is None or " ".join(texto.split()) == actual:
            return
        store.set_room_miembro(self.sel, ref, etiqueta=texto)
        self._cargar()

    @rx.event
    async def mover(self, ref: str, delta: int):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        refs = [m["ref"] for m in self.miembros]
        if ref not in refs or delta not in (-1, 1):
            return
        i, j = refs.index(ref), refs.index(ref) + delta
        if not 0 <= j < len(refs):
            return
        refs[i], refs[j] = refs[j], refs[i]
        store.set_room_orden(self.sel, refs)
        self._cargar()

    @rx.event
    async def quitar(self, ref: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        sala = self._sala(store.read_all())
        propios = list(sala.get("entidades") or [])
        if ref not in propios:
            return
        store.update_room(self.sel, sala.get("name", ""), [r for r in propios if r != ref])
        self._cargar()
        await self._anotar(f"{self.nombre}: elemento {ref} quitado")

    @rx.event
    async def alternar_anadir(self):
        self.anadiendo = not self.anadiendo

    @rx.event
    async def anadir(self, ref: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        if ref not in {c["value"] for c in self.catalogo}:
            return
        sala = self._sala(store.read_all())
        store.update_room(self.sel, sala.get("name", ""), [*(sala.get("entidades") or []), ref])
        self._cargar()
        await self._anotar(f"{self.nombre}: elemento {ref} añadido")
