"""Gestión de dispositivos, roles e invitaciones — la parte de administrador.

Todo lo que cambia algo aquí comprueba el permiso de AJUSTES antes de tocar
nada: esconder la pantalla no es protegerla, porque sus eventos se pueden
llamar por el websocket sin haberla abierto nunca.

Los textos que se pintan van armados EN PYTHON, no en la vista. En esta
versión de Reflex, concatenar el valor de una clave de un diccionario dentro
de un rx.foreach sin pasarlo por .to(str) revienta al compilar el frontend
—ya tiró el servicio una vez—, así que cada fila llega con sus cadenas hechas
y la vista solo las coloca.
"""
from datetime import datetime

import reflex as rx

from . import permisos, store
from ..notifications import categorias
from ..security import audit, logs
from ...core import bus, sesiones


# Los iconos entre los que se puede elegir para un dispositivo — ver
# elegir_icono. Curados para aparatos personales de la familia, no
# infraestructura de la casa (ese catálogo es _HOST_ICONS, en equipment.py).
ICONOS_DISPOSITIVO = [
    "smartphone", "laptop", "monitor", "tablet", "watch",
    "tv", "gamepad-2", "server", "router", "printer",
]


def _icono_de_partida(nombre: str) -> str:
    """Propuesta de icono según el nombre, para no arrancar todos los
    dispositivos con el mismo icono genérico. No se guarda hasta que alguien
    lo confirma o lo cambia a mano (ver elegir_icono): esto es solo lo que se
    PROPONE mientras nadie ha elegido nada."""
    n = nombre.lower()
    if any(p in n for p in ("ipad", "tablet")):
        return "tablet"
    if any(p in n for p in ("portátil", "portatil", "laptop", "macbook")):
        return "laptop"
    if any(p in n for p in ("pc", "ordenador", "desktop", "torre", "sobremesa")):
        return "monitor"
    if any(p in n for p in ("tv", "televisor")):
        return "tv"
    return "smartphone"  # el caso más común en una casa: móviles


def _fecha(marca: float | None) -> str:
    if not marca:
        return "nunca"
    return datetime.fromtimestamp(marca).strftime("%d/%m/%Y %H:%M")


def _hace_cuanto(marca: float | None) -> str:
    if not marca:
        return "no ha entrado nunca"
    import time
    segundos = time.time() - marca
    if segundos < 3600:
        return f"hace {int(segundos // 60)} min"
    if segundos < 86400:
        return f"hace {int(segundos // 3600)} h"
    return f"hace {int(segundos // 86400)} días"


def _queda(marca: float | None) -> str:
    if not marca:
        return ""
    import time
    segundos = marca - time.time()
    if segundos <= 0:
        return "caducada"
    if segundos < 3600:
        return f"quedan {int(segundos // 60)} min"
    if segundos < 86400:
        return f"quedan {int(segundos // 3600)} h"
    return f"quedan {int(segundos // 86400)} días"


class AuthAdminState(rx.State):
    dispositivos: list[dict] = []
    invitaciones: list[dict] = []
    bloqueo_activo: bool = False

    # Lo último creado, para poder enseñar el enlace una sola vez.
    codigo_nuevo: str = ""

    # Formulario de invitación
    horas_invitacion: str = "4"
    nota_invitacion: str = ""

    @rx.event
    def on_load(self):
        self._recargar()
        return AuthAdminState.vigilar_desconocidos

    @rx.event(background=True)
    async def vigilar_desconocidos(self):
        """Releé la lista de dispositivos en cuanto cambia algo, en cualquier
        pestaña.

        Es lo que hace que el aviso de «hay un aparato desconocido pidiendo
        entrar» aparezca con el panel ya abierto, en vez de solo al recargar: sin
        esto, un administrador con el panel puesto no se enteraba de nada hasta
        que recargaba, y el aviso al móvil era el único camino.

        También es lo que hace que dos administradores con Ajustes abierto a la
        vez se vean el uno al otro: si uno cambia un rol, revoca una invitación o
        da de baja un aparato, la lista del otro se actualiza sola. Espera el
        aviso de quien escribe (core/bus.py) en vez de sondear: como solo
        despierta cuando alguien ha escrito de verdad, no hace falta comparar
        antes de recargar."""
        guardia = await sesiones.guardia(self)
        aviso = bus.Aviso(bus.DISPOSITIVOS)
        while True:
            try:
                async with self:
                    self._recargar()
                if not await aviso.espera(guardia, 3.0):
                    return
            except Exception as e:
                print(f"⚠️ Error vigilando dispositivos: {e}")
                if not await sesiones.espera(guardia, 10):
                    return

    def _recargar(self):
        self.bloqueo_activo = store.estricto()
        self.dispositivos = [
            {
                "id": d["id"],
                "nombre": d.get("nombre") or "(sin nombre)",
                # Lo que se pinta grande en la tarjeta. d.get("icono") es lo
                # que alguien eligió a mano (ver elegir_icono); mientras nadie
                # lo toque, se propone uno según el nombre — un "iPhone Ana"
                # nace ya con forma de móvil, no con un icono genérico igual
                # para todos.
                "icono": d.get("icono") or _icono_de_partida(d.get("nombre", "")),
                "rol": store.rol_de(d["id"]),
                "rol_nombre": store.NOMBRES_DE_ROL.get(
                    store.rol_de(d["id"]), store.rol_de(d["id"])),
                "visto": _hace_cuanto(d.get("visto")),
                "caduca": _queda(d.get("caduca")) if d.get("caduca") else "",
                "tiene_avisos": "sí" if d.get("endpoint") else "no",
                "es_admin": store.rol_de(d["id"]) == store.ADMIN,
                "sin_acceso": store.rol_de(d["id"]) == store.PENDIENTE,
                # ¿Está llamando a la puerta AHORA? Ver
                # AuthState._avisar_de_desconocido: es una marca de la ficha, no
                # el rol, justo para que el aviso no vuelva a salir cada vez que
                # alguien deja un aparato en «Sin acceso».
                "pide_acceso": bool(d.get("pide_acceso")),
                # Lo que la propia persona escribió para identificarse mientras
                # esperaba acceso (ver AuthState.enviar_nota_acceso). Se queda
                # aunque ya se le haya resuelto: es contexto de por qué se le
                # dio o no el rol que tiene, no solo mientras pide_acceso.
                "nota_acceso": d.get("nota_acceso") or "",
                # Qué avisos de sistema recibe ESTE aparato — solo tiene sentido
                # elegirlo si puede recibir avisos en absoluto (ver "tiene_avisos"
                # arriba). "activa" en Python y no en la vista por lo mismo que el
                # resto de esta pantalla: un rx.foreach no puede comparar contra
                # una lista dentro de otra lista sin que Reflex se atragante.
                "categorias": [
                    {"id": cid, "nombre": nombre,
                     "activa": cid not in d.get("categorias_desactivadas", [])}
                    for cid, nombre in categorias.CATEGORIAS.items()
                ],
            }
            for d in store.todos()
        ]
        self.invitaciones = [
            {
                "codigo": i["codigo"],
                "rol_nombre": store.NOMBRES_DE_ROL.get(i.get("rol", ""), i.get("rol", "")),
                "caduca": _fecha(i.get("caduca")),
                "queda": _queda(i.get("caduca")),
                "nota": i.get("nota") or "",
                "creada_por": i.get("creada_por") or "?",
                "usada": "sí" if i.get("usada_por") else "sin usar",
            }
            for i in store.invitaciones_vivas()
        ]

    @rx.var
    def desconocidos(self) -> list[dict]:
        """Los aparatos que estan pidiendo acceso ahora mismo.

        Los que tienen la marca `pide_acceso`, NO los que tienen rol «Sin
        acceso». La diferencia es la que hacía que el aviso volviera a saltar
        solo: poner a un aparato en «Sin acceso» es una respuesta, no una
        pregunta nueva. La marca la pone el aparato al presentarse y la quita el
        administrador al decidir cualquier cosa."""
        return [d for d in self.dispositivos if d["pide_acceso"]]

    @rx.var
    def hay_desconocidos(self) -> bool:
        return len(self.desconocidos) > 0

    @rx.var
    def hay_admin(self) -> bool:
        return any(d["es_admin"] for d in self.dispositivos)

    @rx.var
    def resumen_bloqueo(self) -> str:
        if self.bloqueo_activo:
            return ("Los permisos están EN VIGOR: quien no tenga rol para algo, "
                    "no puede hacerlo.")
        return ("Los permisos están EN RODAJE: se apunta en los registros quién "
                "haría qué, pero todavía no se impide nada. Enciéndelos cuando "
                "la lista de abajo esté como debe.")

    # ── Cambios ──────────────────────────────────────────────────────────
    @rx.event
    async def cambiar_rol(self, id_dispositivo: str, rol: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        antes = store.dispositivo(id_dispositivo)
        if not antes:
            return rx.toast.error("Ese dispositivo ya no está.", position="top-center")
        # Al cambiar el rol a mano se quita la caducidad: subir a alguien de
        # invitado a familia y que se le siga cayendo el acceso a la hora sería
        # justo lo contrario de lo que se acaba de pedir.
        # `pide_acceso=False` porque asignar un rol ES la respuesta a la
        # llamada, sea la que sea: darle acceso, dejarlo sin acceso o bloquearlo.
        # Lo que no puede pasar es que el aviso siga preguntando algo que ya se
        # ha contestado.
        store.actualizar(id_dispositivo, rol=rol, caduca=None, pide_acceso=False)
        self._recargar()
        await audit.registrar(
            self, logs.ACCESOS, "ROL_CAMBIADO",
            f"{antes.get('nombre') or id_dispositivo}: "
            f"{store.NOMBRES_DE_ROL.get(antes.get('rol'), antes.get('rol'))} → "
            f"{store.NOMBRES_DE_ROL.get(rol, rol)}",
        )
        return rx.toast.success(
            f"{antes.get('nombre') or 'El dispositivo'} pasa a "
            f"{store.NOMBRES_DE_ROL.get(rol, rol)}.", position="top-center")

    @rx.event
    async def alternar_categoria(self, id_dispositivo: str, categoria: str):
        """Silencia o reactiva un tipo de aviso para ESTE aparato — no toca a
        los demás. Guardado como lista de categorías DESACTIVADAS (ver
        auth/store.categorias_desactivadas): así un dispositivo que nunca ha
        tocado este ajuste sigue recibiendo todo, igual que antes de que esto
        existiera."""
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        d = store.dispositivo(id_dispositivo)
        if d is None:
            return
        desactivadas = set(d.get("categorias_desactivadas", []))
        si_estaba_activa = categoria not in desactivadas
        if si_estaba_activa:
            desactivadas.add(categoria)
        else:
            desactivadas.discard(categoria)
        store.actualizar(id_dispositivo, categorias_desactivadas=sorted(desactivadas))
        self._recargar()
        await audit.registrar(
            self, logs.ACCESOS, "AVISOS_CAMBIADOS",
            f"{d.get('nombre') or id_dispositivo}: "
            f"{categorias.CATEGORIAS.get(categoria, categoria)} "
            f"{'desactivado' if si_estaba_activa else 'activado'}",
        )

    @rx.event
    async def elegir_icono(self, id_dispositivo: str, icono: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        if icono not in ICONOS_DISPOSITIVO or not store.dispositivo(id_dispositivo):
            return
        store.actualizar(id_dispositivo, icono=icono)
        self._recargar()

    @rx.event
    async def eliminar_dispositivo(self, id_dispositivo: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        d = store.dispositivo(id_dispositivo) or {}
        store.eliminar(id_dispositivo)
        self._recargar()
        await audit.registrar(self, logs.ACCESOS, "DISPOSITIVO_ELIMINADO",
                              d.get("nombre") or id_dispositivo)
        return rx.toast.success("Dispositivo eliminado.", position="top-center")

    @rx.event
    async def alternar_bloqueo(self):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        nuevo = not store.estricto()
        if nuevo and not self.hay_admin:
            return rx.toast.error(
                "No hay ningún administrador: si se activa ahora, nadie podría "
                "volver a entrar aquí. Pon admin a un dispositivo primero.",
                position="top-center", duration=10000)
        store.poner_estricto(nuevo)
        self._recargar()
        # Que esta misma sesión vea el cambio sin recargar la página: la
        # interfaz decide qué enseña con una copia del estado del bloqueo.
        from .state import AuthState
        (await self.get_state(AuthState))._refrescar()
        await audit.registrar(
            self, logs.ACCESOS, "ROL_CAMBIADO",
            "permisos EN VIGOR" if nuevo else "permisos en rodaje")
        return rx.toast.success(
            "Permisos en vigor." if nuevo else "Permisos en rodaje.",
            position="top-center")

    # ── Invitaciones ─────────────────────────────────────────────────────
    @rx.event
    def set_horas_invitacion(self, valor: str):
        self.horas_invitacion = valor

    @rx.event
    def set_nota_invitacion(self, valor: str):
        self.nota_invitacion = valor

    @rx.event
    async def crear_invitacion(self):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        try:
            horas = float((self.horas_invitacion or "").replace(",", "."))
        except ValueError:
            return rx.toast.error("Pon cuántas horas dura, en números.",
                                  position="top-center")
        if horas <= 0:
            return rx.toast.error("La invitación tiene que durar algo.",
                                  position="top-center")

        quien = await audit.usuario_de(self)
        codigo = store.crear_invitacion(horas=horas, creada_por=quien,
                                        nota=self.nota_invitacion.strip())
        self.codigo_nuevo = codigo
        self.nota_invitacion = ""
        self._recargar()
        logs.registrar(logs.ACCESOS, "INVITACION_CREADA", quien,
                       f"{horas:g} h" + (f" — {self.nota_invitacion}" if self.nota_invitacion else ""))
        return rx.toast.success("Invitación creada. Copia el enlace y mándalo.",
                                position="top-center")

    @rx.event
    async def revocar(self, codigo: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        store.revocar_invitacion(codigo)
        if self.codigo_nuevo == codigo:
            self.codigo_nuevo = ""
        self._recargar()
        await audit.registrar(self, logs.ACCESOS, "INVITACION_REVOCADA",
                              "también se retira el acceso que hubiera dado")
        return rx.toast.success("Invitación retirada.", position="top-center")

    @rx.event
    def copiar_enlace(self, codigo: str):
        """El enlace se arma EN EL NAVEGADOR con su propia dirección: el
        servidor no sabe por qué nombre se le llega."""
        return rx.call_script(
            "navigator.clipboard.writeText("
            f"window.location.origin + '/panel?invitacion={codigo}')"
        )
