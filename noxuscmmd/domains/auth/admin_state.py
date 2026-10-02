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
import json
import secrets

import reflex as rx

from . import permisos, store
from ..nodes import store as nodes_store
from ..notifications import categorias, suscriptores
from ..security import audit, logs
from ...core import bus, sesiones


# Los iconos entre los que se puede elegir para un dispositivo — ver
# elegir_icono. Curados para aparatos personales de la familia, no
# infraestructura de la casa (ese catálogo es _HOST_ICONS, en equipment.py).
ICONOS_DISPOSITIVO = [
    "smartphone", "laptop", "monitor", "tablet", "watch",
    "tv", "gamepad-2", "server", "router", "printer",
]


_ICONO_CATEGORIA = {
    categorias.MOVIMIENTO: "scan-eye",
    categorias.ALARMA: "siren",
    categorias.DESCONOCIDO: "circle-help",
}


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
    estancias: list[dict] = []

    # Los códigos reales nunca son estado público: Reflex sincroniza todas las
    # vars públicas por websocket aunque la vista no llegue a pintarlas. La UI
    # recibe referencias opacas y los eventos autorizados las resuelven aquí.
    _codigos_invitacion: dict[str, str] = {}
    # Suscripciones de avisos que no son de ningún aparato registrado (restos de
    # una app desinstalada). Al navegador solo va una referencia: el endpoint es
    # la dirección con la que cualquiera podría mandarle avisos a ese aparato.
    suscripciones_sueltas: list[dict] = []
    _endpoints_sueltos: dict[str, str] = {}
    # A quién puede sustituir un aparato nuevo (ver sustituir): los que ya
    # tienen acceso.
    opciones_sustituir: list[dict] = []

    # Formulario de invitación
    horas_invitacion: str = "4"
    nota_invitacion: str = ""

    @rx.event
    async def on_load(self):
        if not await self._puede_cargar_ajustes():
            self._vaciar()
            return
        self._recargar()
        return AuthAdminState.vigilar_desconocidos

    async def _puede_cargar_ajustes(self) -> bool:
        """Comprueba el permiso real antes de volcar datos administrativos."""
        from .state import AuthState

        try:
            auth = await self.get_state(AuthState)
        except Exception:
            return False
        return auth._tiene(permisos.AJUSTES)

    def _vaciar(self) -> None:
        """Retira del websocket cualquier dato administrativo ya cargado."""
        self.dispositivos = []
        self.invitaciones = []
        self.estancias = []
        self._codigos_invitacion = {}

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
                    if not await self._puede_cargar_ajustes():
                        self._vaciar()
                        return
                    self._recargar()
                if not await aviso.espera(guardia, 3.0):
                    return
            except Exception as e:
                print(f"⚠️ Error vigilando dispositivos: {e}")
                if not await sesiones.espera(guardia, 10):
                    return

    def _recargar(self):
        subs = suscriptores.leer()
        endpoints_vivos = {s.get("endpoint") for s in subs}
        fichas = store.todos()
        catalogo = categorias.catalogo()
        con_acceso = [d for d in fichas
                      if store.rol_de(d["id"]) not in (store.PENDIENTE, store.BLOQUEADO)]
        self.opciones_sustituir = [
            {"id": d["id"], "nombre": d.get("nombre") or d["id"]} for d in con_acceso]

        def _candidato(d: dict) -> dict:
            """Para un aparato que pide entrar: el ya registrado con su mismo
            nombre, que casi seguro es él mismo antes de reinstalar."""
            if store.rol_de(d["id"]) != store.PENDIENTE and not d.get("pide_acceso"):
                return {}
            objetivo = store.normalizar(d.get("nombre") or "")
            if not objetivo:
                return {}
            return next((c for c in con_acceso if c["id"] != d["id"]
                         and store.normalizar(c.get("nombre") or "") == objetivo), {})

        de_fichas = {d.get("endpoint") for d in fichas if d.get("endpoint")}
        nombres_fichas = {store.normalizar(d.get("nombre") or "") for d in fichas}
        anteriores_sueltos = {e: r for r, e in self._endpoints_sueltos.items()}
        self._endpoints_sueltos = {}
        sueltas = []
        for s in subs:
            e = s.get("endpoint") or ""
            if not e or e in de_fichas or store.normalizar(
                    s.get("nombre_usuario") or "") in nombres_fichas:
                continue
            ref = anteriores_sueltos.get(e) or secrets.token_urlsafe(9)
            self._endpoints_sueltos[ref] = e
            sueltas.append({"ref": ref, "nombre": s.get("nombre_usuario") or "(sin nombre)"})
        self.suscripciones_sueltas = sueltas
        self.estancias = [
            {"id": room["id"], "nombre": room.get("name") or room["id"]}
            for room in nodes_store.list_rooms()
        ]
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
                "tiene_avisos": "sí" if d.get("endpoint") in endpoints_vivos else "no",
                "sustituye_a": _candidato(d).get("id", ""),
                "sustituye_nombre": _candidato(d).get("nombre", ""),
                "es_admin": store.rol_de(d["id"]) == store.ADMIN,
                "sin_acceso": store.rol_de(d["id"]) == store.PENDIENTE,
                "es_kiosco": store.rol_de(d["id"]) == store.KIOSCO,
                "kiosco_estancia": d.get("kiosco_estancia") or "",
                "kiosco_camaras": bool(d.get("kiosco_camaras")),
                # ¿Está llamando a la puerta AHORA? Ver
                # AuthState._avisar_de_desconocido: es una marca de la ficha, no
                # el rol, justo para que el aviso no vuelva a salir cada vez que
                # alguien deja un aparato en «Sin acceso».
                "pide_acceso": bool(d.get("pide_acceso")),
                "ver_despliegue": bool(d.get("ver_despliegue")),
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
                     "icono": _ICONO_CATEGORIA.get(cid, "siren"),
                     "activa": cid not in d.get("categorias_desactivadas", [])}
                    for cid, nombre in catalogo.items()
                ],
            }
            for d in fichas
        ]
        anteriores = {
            codigo: referencia
            for referencia, codigo in self._codigos_invitacion.items()
        }
        codigos: dict[str, str] = {}
        invitaciones = []
        for i in store.invitaciones_vivas():
            codigo = i["codigo"]
            referencia = anteriores.get(codigo) or secrets.token_urlsafe(9)
            while referencia in codigos:
                referencia = secrets.token_urlsafe(9)
            codigos[referencia] = codigo
            invitaciones.append({
                "referencia": referencia,
                "rol_nombre": store.NOMBRES_DE_ROL.get(i.get("rol", ""), i.get("rol", "")),
                "caduca": _fecha(i.get("caduca")),
                "queda": _queda(i.get("caduca")),
                "nota": i.get("nota") or "",
                "creada_por": i.get("creada_por") or "?",
                "usada": "sí" if i.get("usada_por") else "sin usar",
            })
        self._codigos_invitacion = codigos
        self.invitaciones = invitaciones

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

    # ── Cambios ──────────────────────────────────────────────────────────
    @rx.event
    async def cambiar_rol(self, id_dispositivo: str, rol: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        antes = store.dispositivo(id_dispositivo)
        if not antes:
            return rx.toast.error("Ese dispositivo ya no está.")
        # Al cambiar el rol a mano se quita la caducidad: subir a alguien de
        # invitado a familia y que se le siga cayendo el acceso a la hora sería
        # justo lo contrario de lo que se acaba de pedir.
        # `pide_acceso=False` porque asignar un rol ES la respuesta a la
        # llamada, sea la que sea: darle acceso, dejarlo sin acceso o bloquearlo.
        # Lo que no puede pasar es que el aviso siga preguntando algo que ya se
        # ha contestado.
        campos = {}
        if rol in (store.ADMIN, store.FAMILIA, store.INVITADO, store.KIOSCO):
            # Aceptar la solicitud la responde: el motivo que escribió quien
            # pedía entrar ya no sirve y no debe quedarse en la ficha. Si se
            # rechaza o se deja pendiente, sí se conserva (ayuda a decidir).
            campos["nota_acceso"] = ""
        if rol != store.KIOSCO:
            campos.update(kiosco_estancia="", kiosco_camaras=False)
        store.actualizar(id_dispositivo, rol=rol, caduca=None,
                         pide_acceso=False, **campos)
        self._recargar()
        await audit.registrar(
            self, logs.ACCESOS, "ROL_CAMBIADO",
            f"{antes.get('nombre') or id_dispositivo}: "
            f"{store.NOMBRES_DE_ROL.get(antes.get('rol'), antes.get('rol'))} → "
            f"{store.NOMBRES_DE_ROL.get(rol, rol)}",
        )
        return rx.toast.success(
            f"{antes.get('nombre') or 'El dispositivo'} pasa a "
            f"{store.NOMBRES_DE_ROL.get(rol, rol)}.")

    @rx.event
    async def asignar_kiosco_estancia(self, id_dispositivo: str, room_id: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        ficha = store.dispositivo(id_dispositivo)
        validas = {room["id"] for room in nodes_store.list_rooms()}
        if ficha is None or ficha.get("rol") != store.KIOSCO:
            return rx.toast.error("Ese dispositivo no es una tablet de habitación.")
        if room_id not in validas:
            return rx.toast.error("Esa estancia ya no existe.")
        store.actualizar(id_dispositivo, kiosco_estancia=room_id)
        self._recargar()
        await audit.registrar(
            self, logs.ACCESOS, "KIOSCO_ESTANCIA_CAMBIADA",
            f"{ficha.get('nombre') or id_dispositivo}: {room_id}",
        )

    @rx.event
    async def alternar_camaras_kiosco(self, id_dispositivo: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        ficha = store.dispositivo(id_dispositivo)
        if ficha is None or ficha.get("rol") != store.KIOSCO:
            return
        nuevo = not bool(ficha.get("kiosco_camaras"))
        store.actualizar(id_dispositivo, kiosco_camaras=nuevo)
        self._recargar()
        await audit.registrar(
            self, logs.ACCESOS, "KIOSCO_CAMARAS_CAMBIADAS",
            f"{ficha.get('nombre') or id_dispositivo}: "
            f"{'permitidas' if nuevo else 'retiradas'}",
        )

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
            f"{categorias.catalogo().get(categoria, categoria)} "
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
        # La ficha y la suscripción de avisos son dos ficheros distintos: si
        # solo se borraba la ficha, la suscripción se quedaba con su nombre y al
        # volver a instalar la app dar el MISMO nombre fallaba con «ya hay otro
        # dispositivo llamado…». Se van las dos: la del endpoint de la ficha y
        # cualquiera con ese nombre (los nombres de suscripción son únicos, así
        # que una con el mismo nombre es del mismo aparato).
        suscriptores.quitar_de(d)
        self._recargar()
        await audit.registrar(self, logs.ACCESOS, "DISPOSITIVO_ELIMINADO",
                              d.get("nombre") or id_dispositivo)
        return rx.toast.success("Dispositivo eliminado.")

    @rx.event
    async def sustituir(self, id_nuevo: str, id_viejo: str):
        """«Es X reinstalado»: el aparato que pide entrar se queda con todo lo
        de X (rol incluido) y X desaparece con su suscripción de avisos vieja.
        Solo para aparatos que están pidiendo acceso: sobre uno que ya lo tiene
        sería pisarle la identidad a un aparato en uso por un mal toque."""
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        nuevo = store.dispositivo(id_nuevo)
        if not nuevo or not id_viejo:
            return
        if store.rol_de(id_nuevo) != store.PENDIENTE and not nuevo.get("pide_acceso"):
            return rx.toast.error("Solo se puede sustituir con un aparato que está pidiendo acceso.")
        viejo = store.sustituir(id_nuevo, id_viejo)
        if viejo is None:
            return rx.toast.error("No se pudo: alguno de los dos ya no está.")
        suscriptores.quitar_de(viejo)
        self._recargar()
        nombre = viejo.get("nombre") or id_viejo
        await audit.registrar(self, logs.ACCESOS, "DISPOSITIVO_SUSTITUIDO",
                              f"{nombre}: reinstalado, hereda rol "
                              f"{store.NOMBRES_DE_ROL.get(viejo.get('rol'), viejo.get('rol'))}")
        return rx.toast.success(
            f"Listo: es «{nombre}» con su rol. Que active los avisos otra vez desde la app.")

    @rx.event
    async def alternar_despliegue(self, id_dispositivo: str):
        """Casilla «Ver despliegue»: el icono de la terminal del servicio."""
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        d = store.dispositivo(id_dispositivo)
        if not d:
            return
        store.actualizar(id_dispositivo, ver_despliegue=not d.get("ver_despliegue"))
        self._recargar()

    @rx.event
    async def quitar_avisos(self, id_dispositivo: str):
        """Deja de mandarle avisos a este aparato, sin quitarle el acceso."""
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        d = store.dispositivo(id_dispositivo)
        if not d:
            return
        suscriptores.quitar_de(d)
        store.actualizar(id_dispositivo, endpoint="")
        self._recargar()
        await audit.registrar(self, logs.ACCESOS, "AVISOS_QUITADOS",
                              d.get("nombre") or id_dispositivo)
        return rx.toast.success("Ya no recibirá avisos.")

    @rx.event
    async def borrar_suscripcion_suelta(self, ref: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        endpoint = self._endpoints_sueltos.get(ref)
        if not endpoint:
            return
        nombre = (suscriptores.buscar(endpoint) or {}).get("nombre_usuario", "")
        suscriptores.eliminar(endpoint)
        self._recargar()
        await audit.registrar(self, logs.ACCESOS, "AVISOS_QUITADOS",
                              f"{nombre or '(sin nombre)'} (suscripción suelta)")
        return rx.toast.success("Suscripción borrada.")

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
            return rx.toast.error("Pon cuántas horas dura, en números.")
        if horas <= 0:
            return rx.toast.error("La invitación tiene que durar algo.")

        quien = await audit.usuario_de(self)
        store.crear_invitacion(horas=horas, creada_por=quien,
                               nota=self.nota_invitacion.strip())
        self.nota_invitacion = ""
        self._recargar()
        logs.registrar(logs.ACCESOS, "INVITACION_CREADA", quien,
                       f"{horas:g} h" + (f" — {self.nota_invitacion}" if self.nota_invitacion else ""))
        return rx.toast.success("Invitación creada. Copia el enlace y mándalo.")

    @rx.event
    async def revocar(self, referencia: str):
        if not await self._puede_cargar_ajustes():
            self._vaciar()
            return rx.toast.error(permisos.motivo(permisos.AJUSTES))
        codigo = self._codigos_invitacion.get(referencia, "")
        if not codigo:
            return rx.toast.error("Esa invitación ya no está disponible.")
        store.revocar_invitacion(codigo)
        self._recargar()
        await audit.registrar(self, logs.ACCESOS, "INVITACION_REVOCADA",
                              "también se retira el acceso que hubiera dado")
        return rx.toast.success("Invitación retirada.")

    @rx.event
    async def copiar_enlace(self, referencia: str):
        """El enlace se arma EN EL NAVEGADOR con su propia dirección: el
        servidor no sabe por qué nombre se le llega."""
        if not await self._puede_cargar_ajustes():
            self._vaciar()
            return rx.toast.error(permisos.motivo(permisos.AJUSTES))
        codigo = self._codigos_invitacion.get(referencia, "")
        if not codigo:
            return rx.toast.error("Esa invitación ya no está disponible.")
        return rx.call_script(
            "navigator.clipboard.writeText("
            "window.location.origin + '/panel?invitacion=' + "
            f"{json.dumps(codigo)})"
        )
