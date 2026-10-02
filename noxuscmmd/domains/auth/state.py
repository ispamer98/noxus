"""Quién es esta pestaña y qué puede hacer.

La identidad se sostiene en la cookie firmada (sessions.py), NO en la
suscripción push. Se apoyan la una en la otra pero no dependen: un navegador
al que le han borrado los avisos —o que nunca los aceptó, como un portátil—
sigue siendo el mismo dispositivo y conserva su acceso. La suscripción sirve
para reconocer de entrada a los aparatos que ya estaban dados de alta, que es
lo que evita tener que volver a presentar uno por uno los que ya funcionaban.
"""
import asyncio
from collections import OrderedDict
import os
import threading
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import reflex as rx

from . import permisos, sessions, store
from ..security import logs
from ...core import bus, sesiones

# Respaldo de `vigilar_acceso`: por si dispositivos.json lo tocara algo de
# fuera de este proceso, igual que en los demás sync_loop (ver core/bus.py).
# En el camino normal el aviso llega al instante, no a los tres segundos.
_VIGILANCIA = 3.0

# Un visitante aún no tiene ficha: estos ids viven únicamente en el proceso y
# en su cookie firmada. Recordarlos permite reconocer una recarga normal sin
# confundirla con la cookie de una ficha que un administrador acaba de borrar.
_VISITANTES: OrderedDict[str, tuple[float, str]] = OrderedDict()
_CANDADO_VISITANTES = threading.Lock()
_MAX_VISITANTES = 4096
_VIDA_VISITANTE = 24 * 3600

# Una visita repetida no debe llenar el histórico. La clave sigue siendo el id
# efímero; ni la cookie ni su firma se guardan jamás en el registro.
_VENTANA_INTENTO = 30 * 60

# Un origen no puede convertir las visitas anónimas en escrituras ilimitadas.
# Son ventanas fijas y contadores en memoria: cada decisión cuesta O(1) y la
# memoria tiene un techo incluso si cambian de IP en cada petición.
_VENTANA_INTENTOS_GLOBAL = 60.0
_MAX_INTENTOS_IP = 8
_MAX_INTENTOS_TOTAL = 80
_VENTANA_SOLICITUD = 10 * 60.0
_MAX_SOLICITUDES_IP = 3
_MAX_SOLICITUDES_VISITANTE = 3
_MAX_PENDIENTES = 20
_VENTANA_PUSH_ACCESO = 10 * 60.0
_MAX_PUSH_ACCESO = 6
_VPS_CONFIABLE = "100.98.98.10"

_PARAMETROS_SECRETOS = (
    "token", "codigo", "código", "invitacion", "invitación", "secret",
    "clave", "password", "passwd", "auth", "session", "sesion", "key",
)


class _LimitesVentana:
    """Contadores de ventana fija con memoria acotada y operaciones O(1)."""

    def __init__(self, max_claves: int):
        self._max_claves = max_claves
        self._datos: OrderedDict[str, tuple[int, int]] = OrderedDict()
        self._candado = threading.Lock()

    def admitir(self, claves: tuple[tuple[str, int], ...], ventana: float,
                ahora: float | None = None) -> bool:
        tramo = int((time.monotonic() if ahora is None else ahora) // ventana)
        with self._candado:
            for clave, limite in claves:
                guardado = self._datos.get(clave)
                if guardado and guardado[0] == tramo and guardado[1] >= limite:
                    return False
            for clave, _limite in claves:
                guardado = self._datos.get(clave)
                cuenta = guardado[1] + 1 if guardado and guardado[0] == tramo else 1
                self._datos[clave] = (tramo, cuenta)
                self._datos.move_to_end(clave)
                if len(self._datos) > self._max_claves:
                    self._datos.popitem(last=False)
        return True

    def vaciar(self) -> None:
        """Solo para aislar las pruebas; producción caduca por ventana."""
        with self._candado:
            self._datos.clear()


_LIMITES_INTENTOS = _LimitesVentana(1024)
_LIMITES_SOLICITUDES = _LimitesVentana(1024)
_LIMITES_PUSH_ACCESO = _LimitesVentana(1)


def _admitir_intento(ip: str) -> bool:
    return _LIMITES_INTENTOS.admitir(
        (("total", _MAX_INTENTOS_TOTAL), (f"ip:{ip}", _MAX_INTENTOS_IP)),
        _VENTANA_INTENTOS_GLOBAL,
    )


def _admitir_solicitud(ip: str, visitante: str) -> bool:
    return _LIMITES_SOLICITUDES.admitir(
        ((f"ip:{ip}", _MAX_SOLICITUDES_IP),
         (f"visitante:{visitante}", _MAX_SOLICITUDES_VISITANTE)),
        _VENTANA_SOLICITUD,
    )


def _recordar_visitante(id_visitante: str, motivo: str) -> None:
    ahora = time.monotonic()
    with _CANDADO_VISITANTES:
        _VISITANTES[id_visitante] = (ahora + _VIDA_VISITANTE, motivo)
        _VISITANTES.move_to_end(id_visitante)
        if len(_VISITANTES) > _MAX_VISITANTES:
            _VISITANTES.popitem(last=False)


def _motivo_visitante(id_visitante: str) -> str:
    ahora = time.monotonic()
    with _CANDADO_VISITANTES:
        dato = _VISITANTES.get(id_visitante)
        if dato is None:
            return ""
        expira, motivo = dato
        if expira <= ahora:
            _VISITANTES.pop(id_visitante, None)
            return ""
        _VISITANTES[id_visitante] = (ahora + _VIDA_VISITANTE, motivo)
        _VISITANTES.move_to_end(id_visitante)
        return motivo


def _olvidar_visitante(id_visitante: str) -> None:
    with _CANDADO_VISITANTES:
        _VISITANTES.pop(id_visitante, None)


def _recortar(valor: str, limite: int) -> str:
    """Una sola línea acotada; evita controles y detalles enormes en el log."""
    return " ".join((valor or "").split())[:limite]


def _cabeceras(router) -> dict[str, str]:
    return {str(k).lower(): str(v) for k, v in router.headers.raw_headers.items()}


def _ip_real(router) -> str:
    cabeceras = _cabeceras(router)
    directa = _recortar(router.session.client_ip, 64)
    if directa == _VPS_CONFIABLE:
        cadena = cabeceras.get("x-forwarded-for", "")
        reenviada = cadena.rsplit(",", 1)[-1].strip() if cadena else ""
        if reenviada:
            return _recortar(reenviada, 64)
    return directa or "desconocida"


def _resumir_ua(ua: str) -> str:
    """Nombre corto de navegador y sistema sin añadir otra dependencia."""
    texto = ua or ""
    navegadores = (
        ("Edg/", "Edge"), ("OPR/", "Opera"), ("CriOS/", "Chrome"),
        ("Chrome/", "Chrome"), ("FxiOS/", "Firefox"),
        ("Firefox/", "Firefox"), ("Version/", "Safari"),
    )
    navegador = "Navegador desconocido"
    for marca, nombre in navegadores:
        if marca in texto:
            version = texto.split(marca, 1)[1].split(".", 1)[0].split(" ", 1)[0]
            navegador = f"{nombre} {version}" if version.isdigit() else nombre
            break
    if "Android" in texto:
        sistema = "Android"
    elif "iPhone" in texto or "iPad" in texto:
        sistema = "iOS"
    elif "Windows" in texto:
        sistema = "Windows"
    elif "Mac OS X" in texto or "Macintosh" in texto:
        sistema = "macOS"
    elif "CrOS" in texto:
        sistema = "ChromeOS"
    elif "Linux" in texto:
        sistema = "Linux"
    else:
        sistema = "sistema desconocido"
    return f"{navegador} en {sistema}"


def _es_parametro_secreto(nombre: str) -> bool:
    normalizado = nombre.casefold()
    return any(p in normalizado for p in _PARAMETROS_SECRETOS)


def _url_sin_secretos(url: str, limite: int = 240) -> str:
    """Conserva la ruta útil y elimina códigos, claves y tokens de la query."""
    if not url:
        return ""
    try:
        partes = urlsplit(url)
        query = urlencode([
            (k, v) for k, v in parse_qsl(partes.query, keep_blank_values=True)
            if not _es_parametro_secreto(k)
        ])
        limpio = urlunsplit((partes.scheme, partes.netloc, partes.path, query, ""))
    except (TypeError, ValueError):
        limpio = url.split("?", 1)[0]
    return _recortar(limpio, limite)


def _contexto_peticion(router) -> dict[str, str]:
    cabeceras = _cabeceras(router)
    ua = _recortar(router.headers.user_agent or cabeceras.get("user-agent", ""), 220)
    return {
        "ip": _ip_real(router),
        "navegador": _resumir_ua(ua),
        "ua": ua or "desconocido",
        "idioma": _recortar(
            router.headers.accept_language or cabeceras.get("accept-language", ""),
            80,
        ) or "desconocido",
        "ruta": _url_sin_secretos(str(router.url)) or "/",
        "referer": _url_sin_secretos(cabeceras.get("referer", "")) or "directo",
    }


def _detalle_intento(contexto: dict[str, str], motivo: str,
                     id_visitante: str) -> str:
    return (
        f"IP {contexto['ip']} · {contexto['navegador']} · "
        f"idioma {contexto['idioma']} · ruta {contexto['ruta']} · "
        f"referer {contexto['referer']} · motivo {motivo} · "
        f"visitante {id_visitante[:8]} · UA {contexto['ua']}"
    )


class AuthState(rx.State):
    # La cookie. Es pública porque Reflex tiene que poder sincronizarla con el
    # navegador; su contenido no es secreto y va firmado, así que tocarla desde
    # el cliente solo consigue invalidarla.
    # `secure` sale del entorno y no va puesto a fuego. Marcarla significa que
    # el navegador solo la manda por HTTPS, que es lo correcto... salvo que esta
    # casa entra al panel TAMBIEN por HTTP dentro de la LAN
    # (http://192.168.1.x:3000): con secure fijo, esas sesiones dejarian de
    # funcionar y solo se podria entrar por el dominio de fuera. Asi que se deja
    # preparado y se enciende poniendo COOKIE_SECURE=1 en .env el dia que todo
    # el acceso sea por HTTPS.
    #
    # rx.Cookie declara sus flags al arrancar, no por peticion, asi que no se
    # puede decidir "secure si esta conexion es HTTPS": o para todas o para
    # ninguna.
    testigo: str = rx.Cookie(
        name=sessions.NOMBRE_COOKIE,
        max_age=sessions.DURACION,
        path="/",
        same_site="lax",
        secure=os.getenv("COOKIE_SECURE", "") == "1",
    )

    # Lo verificado en el servidor. Con guion bajo delante a propósito: así
    # Reflex no las manda al navegador NI genera un evento `set_` para ellas.
    # Sin el guion, cualquier pestaña conectada podría llamar
    # `set__rol("admin")` y darse permisos sola — que es justo lo que esto
    # viene a impedir.
    _id: str = ""
    _rol: str = store.PENDIENTE
    _nombre: str = ""
    _kiosco_estancia: str = ""
    _kiosco_camaras: bool = False
    # Una suscripción nueva puede llegar antes de que la persona rellene el
    # formulario. Se conserva solo en esta sesión y se persiste junto con la
    # ficha cuando nombre y motivo validan; nunca crea una ficha por sí sola.
    _endpoint_push: str = ""
    # Copia de si el bloqueo está en vigor. Mientras no lo esté, la interfaz
    # tiene que enseñarlo TODO: el rodaje sirve para ver quién es quién sin
    # quitarle nada a nadie, y esconder botones ya es quitar. Sin esto, un
    # aparato todavía sin reconocer se quedaba sin el botón de armar aunque el
    # sistema le hubiera dejado armar de todas formas — lo peor de los dos
    # mundos: no puede pulsar y encima parece roto.
    _bloqueo: bool = False
    # Si `identificar` ya ha corrido. Hasta entonces no se sabe si este
    # navegador tiene acceso, y no se puede pintar ni el panel (seria
    # ensenarselo a quien no debe) ni la puerta cerrada (un parpadeo de
    # "no tienes acceso" a quien si lo tiene). Se pinta "comprobando".
    _identificado: bool = False
    # Código de una invitación que espera el nombre de quien la usa. Es privado
    # porque cualquier var pública viaja por websocket aunque no se pinte.
    _invitacion_pendiente: str = ""
    nombre_invitado: str = ""

    # Lo que un aparato SIN acceso todavía deja escrito para identificarse —
    # ver _sin_acceso() en ui/pages/dashboard.py. El nombre es la parte que de
    # verdad hace falta (es lo que sale en la lista de Ajustes y en el propio
    # aviso); la nota es libre, para el contexto que ayude a decidir ("soy el
    # fontanero", "se me ha caído el móvil nuevo"). Ninguno de los dos viene
    # solo: sin suscripción push (o sin que el navegador la soporte, como
    # Chrome en iOS) el aparato no tiene NINGÚN nombre hasta que la persona
    # escribe uno.
    nombre_acceso: str = ""
    nota_acceso: str = ""
    # Casilla «Ver despliegue» de SU ficha: enseña el icono de la terminal.
    ve_despliegue: bool = False

    # ── Lo que la interfaz puede leer ────────────────────────────────────
    @rx.var
    def rol_actual(self) -> str:
        return self._rol

    @rx.var
    def nombre_rol(self) -> str:
        return store.NOMBRES_DE_ROL.get(self._rol, self._rol)

    @rx.var
    def nombre_dispositivo(self) -> str:
        return self._nombre

    def _ve(self, capacidad: str) -> bool:
        """Si la interfaz debe ENSEÑAR algo. No es lo mismo que poder hacerlo:
        mientras el bloqueo no esté en vigor se enseña todo, porque en rodaje
        nadie debe notar el cambio."""
        # Kiosco siempre queda encerrado aunque los permisos generales sigan
        # en rodaje: una tablet de pared no puede adquirir Ajustes o Armado por
        # una fase de despliegue pensada para los dispositivos personales.
        if self._rol == store.KIOSCO:
            return permisos.puede(self._id, capacidad)
        return (not self._bloqueo) or permisos.puede_rol(self._rol, capacidad)

    @rx.var
    def registrando(self) -> bool:
        """Hay una invitación válida esperando el nombre de quien la usa."""
        return self._invitacion_pendiente != ""

    @rx.var
    def comprobando(self) -> bool:
        """Todavia no se sabe quien es este navegador."""
        return not self._identificado

    @rx.var
    def es_admin(self) -> bool:
        return self._rol == store.ADMIN

    @rx.var
    def es_kiosco(self) -> bool:
        return self._rol == store.KIOSCO

    @rx.var
    def tiene_acceso(self) -> bool:
        return self._ve(permisos.VER)

    @rx.var
    def puede_armar(self) -> bool:
        return self._ve(permisos.ARMAR)

    @rx.var
    def puede_luces(self) -> bool:
        return self._ve(permisos.LUCES)

    @rx.var
    def puede_puertas(self) -> bool:
        return self._ve(permisos.PUERTAS)

    @rx.var
    def puede_equipos(self) -> bool:
        return self._ve(permisos.EQUIPOS)

    @rx.var
    def puede_mandos(self) -> bool:
        return self._ve(permisos.MANDOS)

    @rx.var
    def puede_camaras(self) -> bool:
        return self._ve(permisos.CAMARAS)

    @rx.var
    def puede_ajustes(self) -> bool:
        return self._ve(permisos.AJUSTES)

    # ── Preferencias de ESTE aparato (densidad y color de acento) ────────
    # Se leen en _refrescar y se guardan en su ficha, no en un ajuste global:
    # ver auth/store.preferencias.
    densidad: str = store.DENSIDAD_POR_DEFECTO
    acento: str = store.ACENTO_POR_DEFECTO

    @rx.var
    def es_pro(self) -> bool:
        return self.densidad == "pro"

    @rx.event
    def poner_densidad(self, valor: str):
        """La cambia para ESTE aparato. No pide permiso de ajustes: es como se
        ve su propia pantalla, no configuración de la casa — y un invitado en
        una tablet tiene el mismo derecho a ver los botones grandes."""
        if valor not in store.DENSIDADES or not self._id:
            return
        store.actualizar(self._id, densidad=valor)
        self.densidad = valor

    @rx.event
    def poner_acento(self, valor: str):
        if valor not in store.ACENTOS or not self._id:
            return
        store.actualizar(self._id, acento=valor)
        self.acento = valor

    @rx.var
    def densidades_ui(self) -> list[dict]:
        return [
            {"id": "casa", "nombre": "Casa", "detalle": "Cómoda, con aire",
             "activa": self.densidad == "casa"},
            {"id": "pro", "nombre": "Pro", "detalle": "Apretada, cabe más",
             "activa": self.densidad == "pro"},
        ]

    @rx.var
    def acentos_ui(self) -> list[dict]:
        return [{"id": a, "activo": self.acento == a} for a in store.ACENTOS]

    # ── Decisiones ───────────────────────────────────────────────────────
    def _tiene(self, capacidad: str) -> bool:
        """Si este dispositivo puede hacer algo, preguntado EN VIVO.

        Con guion bajo delante para que Reflex NO lo publique como evento: sin
        él aparecía en la lista de eventos invocables desde el navegador. No
        era peligroso —solo devuelve un sí o un no— pero todo lo que se pueda
        llamar desde fuera hay que poder justificarlo, y esto no hace falta.

        No usa `self._rol` a propósito: esa copia es de cuando se cargó la
        pestaña y sirve para pintar. Quitarle el permiso a alguien tiene que
        surtir efecto aunque tenga el panel abierto desde ayer, así que lo que
        decide va a mirar el fichero."""
        return permisos.puede(self._id, capacidad)

    def _refrescar(self) -> None:
        ficha = store.dispositivo(self._id) or {}
        self._rol = store.rol_de(self._id)
        self._nombre = ficha.get("nombre", "")
        self._kiosco_estancia = store.estancia_kiosco(self._id)
        self._kiosco_camaras = store.kiosco_puede_camaras(self._id)
        self._bloqueo = store.estricto()
        prefs = store.preferencias(self._id)
        self.densidad = prefs["densidad"]
        self.acento = prefs["acento"]
        self.nombre_acceso = ficha.get("nombre", "")
        self.nota_acceso = ficha.get("nota_acceso", "")
        self.ve_despliegue = bool(ficha.get("ver_despliegue"))
        # _refrescar es el punto por el que pasan los tres caminos de
        # identificar (cookie buena, cookie inservible y sin cookie), asi
        # que es el sitio donde marcarlo una sola vez.
        self._identificado = True

    def _redireccion_kiosco(self) -> str:
        """Destino forzoso del kiosco, o vacío si ya está en su única ruta."""
        if self._rol != store.KIOSCO or not self._kiosco_estancia:
            return ""
        pagina = getattr(self.router, "page", None)
        params = getattr(pagina, "params", {}) or {}
        path = (getattr(pagina, "raw_path", "")
                or getattr(pagina, "path", "") or "")
        if path.startswith("/estancia/") and params.get("eid") == self._kiosco_estancia:
            return ""
        return f"/estancia/{self._kiosco_estancia}"

    # ── Vigilancia en vivo ───────────────────────────────────────────────
    @rx.event(background=True)
    async def vigilar_acceso(self):
        """Relee del disco el rol de ESTE dispositivo en cuanto cambia algo.

        Sin esto, quitarle el acceso a un aparato no surtía efecto hasta que
        alguien recargaba la página: `_rol` es una copia del momento en que se
        cargó la pestaña, y es la que decide qué se pinta. Una tablet colgada en
        la pared con el panel abierto desde ayer seguía enseñándolo todo.

        Espera el aviso de quien escribe dispositivos.json (core/bus.py) en vez
        de sondear: a quien le quitan el admin en Ajustes se le cae la pantalla
        en el mismo instante en que se guarda el cambio, esté donde esté
        conectado, y no hasta su próxima ronda de sondeo. `_VIGILANCIA` queda
        como respaldo por si el fichero lo tocara algo de fuera de este proceso.

        Lo que se compara es el rol EFECTIVO (store.rol_de ya cuenta la
        caducidad), así que esto es también lo que hace que a un invitado con
        acceso de dos horas se le caiga la pantalla sola al cumplirse la hora, en
        vez de quedarse dentro mientras no toque nada.
        """
        guardia = await sesiones.guardia(self)
        aviso = bus.Aviso(bus.DISPOSITIVOS)
        while True:
            try:
                recargar = False
                async with self:
                    if self._id:
                        tenia_acceso = self._ve(permisos.VER)
                        rol = await asyncio.to_thread(store.rol_de, self._id)
                        bloqueo = await asyncio.to_thread(store.estricto)
                        ficha = await asyncio.to_thread(store.dispositivo, self._id) or {}
                        estancia = (str(ficha.get("kiosco_estancia") or "")
                                    if rol == store.KIOSCO else "")
                        camaras = bool(estancia and ficha.get("kiosco_camaras"))
                        if (rol != self._rol or bloqueo != self._bloqueo
                                or estancia != self._kiosco_estancia
                                or camaras != self._kiosco_camaras):
                            # Solo se refresca cuando ha cambiado algo: reasignar
                            # en cada vuelta repintaría el panel entero cada vez
                            # que se toca cualquier dispositivo, no solo el suyo.
                            self._refrescar()
                            recargar = not tenia_acceso and self._ve(permisos.VER)
                destino = self._redireccion_kiosco()
                if destino:
                    yield rx.redirect(destino)
                elif recargar:
                    # Al entrar sin permiso no se cargó ningún dominio de la
                    # casa. Una recarga ejecuta ahora el arranque completo.
                    yield rx.call_script("window.location.reload()")
                if not await aviso.espera(guardia, _VIGILANCIA):
                    return
            except Exception as e:
                print(f"⚠️ Error vigilando el acceso: {e}")
                if not await sesiones.espera(guardia, 10):
                    return

    # ── Entrada ──────────────────────────────────────────────────────────
    @rx.event
    def identificar(self):
        """Al abrir el panel: resolver quién es este navegador.

        Tres caminos: trae una cookie válida y se le reconoce; trae una cookie
        inservible (caducada, manipulada o de un servidor cuyo secreto ya no
        está) y se le trata como nuevo; o no trae nada y recibe una identidad
        efímera. Ninguno de los dos últimos crea ficha hasta que la persona
        envía nombre y motivo o canjea una invitación."""
        store.sembrar_si_hace_falta()

        id_dispositivo = sessions.verificar(self.testigo)

        if id_dispositivo and store.dispositivo(id_dispositivo):
            _olvidar_visitante(id_dispositivo)
            self._id = id_dispositivo
            store.visto(id_dispositivo)
            if sessions.hay_que_renovar(self.testigo):
                self.testigo = sessions.emitir(id_dispositivo)
            self._refrescar()
            destino = self._redireccion_kiosco()
            return rx.redirect(destino) if destino else None

        # Una cookie que ya dimos a un visitante efímero conserva su id durante
        # esta sesión de proceso. Cualquier otra cookie válida sin ficha era de
        # una ficha borrada: se sustituye por un visitante nuevo y NO se recrea.
        motivo = _motivo_visitante(id_dispositivo) if id_dispositivo else ""
        if motivo:
            nuevo = id_dispositivo
        else:
            if not self.testigo:
                motivo = "sin cookie"
            elif id_dispositivo:
                motivo = "cookie de una ficha borrada"
            else:
                motivo = "cookie caducada o manipulada"
            nuevo = sessions.nuevo_id()
            _recordar_visitante(nuevo, motivo)
            self.testigo = sessions.emitir(nuevo)
        self._id = nuevo
        self._refrescar()
        contexto = _contexto_peticion(self.router)
        if _admitir_intento(contexto["ip"]):
            logs.registrar_limitado(
                f"acceso-app:{nuevo}", _VENTANA_INTENTO,
                logs.ACCESO_APP, "INTENTO_ACCESO", "visitante",
                _detalle_intento(contexto, motivo, nuevo), entidad=nuevo,
            )

    @rx.event
    def vincular_push(self, endpoint: str, nombre: str = ""):
        """Casa esta sesión con la suscripción de avisos de este aparato.

        Lo llama PushState cuando el navegador le dice cuál es su suscripción.
        Sirve para dos cosas: reconocer de entrada a los que ya estaban dados
        de alta antes de que existieran los permisos —si no, el día del cambio
        se quedaban todos fuera— y para que el nombre que sale en los registros
        y el de la sesión sean el mismo.

        Sobre la confianza: el endpoint lo manda el navegador. Quien conociera
        el de otro aparato podría adoptar su identidad. Es un secreto que solo
        está en este servidor y en el aparato dueño, así que quien lo tenga ya
        ha entrado en uno de los dos; y hasta hoy el panel no pedía nada en
        absoluto, así que esto no abre ninguna puerta que estuviera cerrada.
        """
        if not endpoint:
            return

        id_conocido, _ = store.por_endpoint(endpoint)

        if id_conocido and id_conocido != self._id:
            # Este navegador ya era conocido. Se adopta su ficha —con su rol— y
            # se tira una ficha pendiente antigua si existía. El visitante
            # efímero nuevo no ha escrito nada y por tanto no deja basura.
            anterior = self._id
            if store.dispositivo(anterior) and store.rol_de(anterior) == store.PENDIENTE:
                store.eliminar(self._id)
            _olvidar_visitante(anterior)
            self._id = id_conocido
            self.testigo = sessions.emitir(id_conocido)
            store.visto(id_conocido)
            # Queda apuntado. Adoptar una ficha por su endpoint es el mecanismo
            # que reconoce a los aparatos de siempre, pero también es la única
            # via por la que una sesión toma la identidad —y el rol— de otra sin
            # que nadie lo autorice: si algún día pasa sin motivo, tiene que
            # poder verse en el registro en vez de no haber ocurrido nunca.
            rol_adoptado = store.rol_de(id_conocido)
            ficha_conocida = store.dispositivo(id_conocido) or {}
            logs.registrar(
                logs.ACCESOS, "DISPOSITIVO_RECONOCIDO",
                ficha_conocida.get("nombre", "") or nombre or "sin nombre",
                f"reconocido por su suscripción de avisos · rol {rol_adoptado}",
                entidad=id_conocido,
            )
            self._refrescar()
            return

        ficha = store.dispositivo(self._id)
        if ficha is None:
            # No se persiste todavía: si luego pide acceso, este endpoint entra
            # en la misma alta que su nombre y su motivo.
            self._endpoint_push = endpoint
            if nombre and not self.nombre_acceso:
                self.nombre_acceso = nombre[:40]
            return
        cambios = {}
        if not ficha.get("endpoint"):
            cambios["endpoint"] = endpoint
        if nombre and not ficha.get("nombre"):
            cambios["nombre"] = nombre
        if cambios:
            store.actualizar(self._id, **cambios)
            self._refrescar()
            # Aquí NO se avisa a nadie, aunque el aparato sea nuevo: tener una
            # suscripción de avisos no es pedir acceso. Quien quiera entrar se
            # identifica y pulsa «Enviar» (ver enviar_nota_acceso), y ese es el
            # único punto desde el que sale el aviso a los administradores.

    def _avisar_de_desconocido(self, nombre: str, nota: str = "") -> None:
        """Deja constancia y avisa a los administradores.

        Lo llama SOLO enviar_nota_acceso: alguien que se ha identificado y ha
        pulsado «Enviar». Abrir la página no llega hasta aquí — ver el comentario
        en `identificar`.

        El aviso va SOLO a los administradores, que son quienes pueden decidir,
        y con un tag propio para que dos intentos seguidos no apilen dos avisos.
        Lleva dentro el nombre y el motivo que escribió la persona: la diferencia
        entre «alguien quiere entrar» y «Marta dice que se le ha roto el móvil»
        es justo lo que permite decidir sin tener que abrir nada.
        """
        como = nombre or "sin nombre"
        # La marca de «está llamando a la puerta», que NO es lo mismo que tener
        # el rol «Sin acceso». Sin separarlas, poner a un aparato en «Sin
        # acceso» lo devolvía al aviso de desconocidos, y el aviso volvía a
        # saltar una y otra vez por una decisión que ya se había tomado.
        # La quita el administrador al decidir (ver AuthAdminState.cambiar_rol).
        store.actualizar(self._id, pide_acceso=True)
        logs.registrar(logs.ACCESOS, "DISPOSITIVO_NUEVO", como,
                       "pide acceso al panel" + (f' — «{nota}»' if nota else ""))
        if not _LIMITES_PUSH_ACCESO.admitir(
                (("total", _MAX_PUSH_ACCESO),), _VENTANA_PUSH_ACCESO):
            return
        try:
            from ..notifications import categorias
            from ..notifications.push import enviar_notificacion
            admins = [f.get("nombre") for f in store.leer()["dispositivos"].values()
                      if f.get("rol") == store.ADMIN and f.get("nombre")]
            if admins:
                cuerpo = f"«{como}» pide entrar en el panel."
                if nota:
                    cuerpo += f' Dice: «{nota}».'
                cuerpo += " Toca para darle acceso o bloquearlo."
                enviar_notificacion(
                    "🔓 Alguien pide acceso", cuerpo,
                    admins, "acceso:desconocido",
                    categoria=categorias.DESCONOCIDO,
                    # Lleva DIRECTO a la pantalla donde se decide, con la ficha
                    # del que pide ya a la vista. Sin esto el aviso abría el
                    # panel por donde estuviera y había que ir a buscarlo.
                    url="/panel?vista=usuarios",
                )
        except Exception as e:
            print(f"⚠️ No se pudo avisar del dispositivo desconocido: {e}")

    # ── Invitaciones: el lado de quien la recibe ─────────────────────────
    @rx.event
    def canjear_de_la_url(self):
        """Entrar con una invitación: /panel?invitacion=<código>.

        Se comprueba después de identificar, así que quien llega con un enlace
        válido pasa de no tener acceso a tenerlo sin más pasos: abre el enlace y
        ya está dentro. Un código inválido o caducado no dice por qué con
        detalle, solo que no vale."""
        codigo = self.router.url.query_parameters.get("invitacion", "")
        if not codigo or not self._id:
            return
        if permisos.puede(self._id, permisos.VER):
            return  # ya tenía acceso: la invitación no le hace falta

        # Antes de dejarle entrar se le pregunta cómo se llama, salvo que ya
        # traiga nombre de su suscripción push. No es burocracia: ese nombre es
        # el que queda escrito en cada línea del registro junto a lo que haga, y
        # sin él todo lo que toque un invitado se apunta como «Invitado», que en
        # una casa con dos invitados no distingue a nadie. Ver `registrarse`.
        if not self._nombre:
            self._invitacion_pendiente = codigo
            return

        return self._canjear(codigo, self._nombre)

    @rx.event
    def set_nombre_invitado(self, valor: str):
        self.nombre_invitado = valor

    @rx.event
    def registrarse(self):
        """Alta de un invitado con su nombre, por el tiempo que dure el enlace.

        El acceso NO se hace permanente por darse un nombre: la caducidad la pone
        la invitación (ver store.canjear) y cuando pasa la hora, rol_de deja de
        devolver su rol y el acceso se cae solo, sin que nadie tenga que ir a
        borrarlo."""
        nombre = self.nombre_invitado.strip()
        if len(nombre) < 2:
            return rx.toast.error("Escribe tu nombre para entrar.")
        codigo = self._invitacion_pendiente
        if not codigo:
            return
        self._invitacion_pendiente = ""
        return self._canjear(codigo, nombre)

    def _canjear(self, codigo: str, nombre: str):
        ok, motivo = store.canjear(codigo, self._id, nombre=nombre)
        if ok:
            if self._endpoint_push:
                store.actualizar(self._id, endpoint=self._endpoint_push)
            _olvidar_visitante(self._id)
        self._refrescar()
        if not ok:
            return rx.toast.error(motivo)

        inv = store.invitacion(codigo) or {}
        logs.registrar(
            logs.ACCESOS, "INVITACION_USADA", nombre or "invitado",
            f"invitación de {inv.get('creada_por', '?')} — "
            f"acceso hasta {_cuando(inv.get('caduca'))}",
        )
        return rx.toast.success(
            f"Acceso concedido hasta {_cuando(inv.get('caduca'))}.",
            duration=8000,
        )

    # ── Identificarse mientras se espera acceso ──────────────────────────
    @rx.event
    def set_nombre_acceso(self, valor: str):
        self.nombre_acceso = valor

    @rx.event
    def set_nota_acceso(self, valor: str):
        self.nota_acceso = valor

    @rx.event
    def enviar_nota_acceso(self):
        """Pedir acceso, de verdad: EL ÚNICO punto desde el que se avisa a los
        administradores.

        Los DOS campos son obligatorios. Un aviso que solo dice «alguien quiere
        entrar» obliga a ir a preguntar quién es y para qué antes de poder
        decidir nada, así que no merece la pena mandarlo: si se va a interrumpir
        a alguien en el móvil, que sea con lo que hace falta para contestar.

        Se puede mandar más de una vez —corregir lo que se escribió no debería
        obligar a empezar de cero—, y el tag del aviso hace que el segundo
        reemplace al primero en la pantalla del administrador en vez de apilarse.
        """
        if not self._id:
            return
        nombre = self.nombre_acceso.strip()[:40]
        texto = self.nota_acceso.strip()[:200]
        if len(nombre) < 2:
            return rx.toast.error("Escribe tu nombre para identificarte.")
        if len(texto) < 3:
            return rx.toast.error("Escribe por qué quieres entrar.")
        contexto = _contexto_peticion(self.router)
        if not _admitir_solicitud(contexto["ip"], self._id):
            return rx.toast.error(
                "Espera unos minutos antes de volver a pedir acceso.")
        ficha = store.dispositivo(self._id)
        if ficha is None and store.contar_pendientes(_MAX_PENDIENTES) >= _MAX_PENDIENTES:
            return rx.toast.error(
                "Ahora mismo hay demasiadas solicitudes pendientes. "
                "Inténtalo más tarde.")
        self.nombre_acceso = nombre
        self.nota_acceso = texto
        if ficha is None:
            store.alta(
                self._id, nombre=nombre, rol=store.PENDIENTE,
                endpoint=self._endpoint_push, nota_acceso=texto,
            )
            _olvidar_visitante(self._id)
        else:
            store.actualizar(self._id, nombre=nombre, nota_acceso=texto)
        self._refrescar()
        logs.registrar(
            logs.ACCESO_APP, "SOLICITUD_ACCESO", nombre,
            f"{nombre} · motivo {texto} · IP {contexto['ip']} · "
            f"{contexto['navegador']}",
            entidad=self._id,
        )
        if self._rol == store.PENDIENTE:
            self._avisar_de_desconocido(nombre, texto)
            return rx.toast.success(
                "Enviado. Un administrador lo ha recibido y decidirá si te "
                "da acceso.", duration=6000)
        return rx.toast.success("Guardado.")


def _cuando(marca: float | None) -> str:
    if not marca:
        return "sin fecha"
    from datetime import datetime
    return datetime.fromtimestamp(marca).strftime("%d/%m/%Y %H:%M")
