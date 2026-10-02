"""Entrada al panel sin ensuciar dispositivos y su rastro de auditoría.

Todo escribe en la casa temporal de ``tests.comun``. Los avisos push y n8n se
anulan aquí: esta prueba comprueba decisiones y persistencia, no contacta con
ningún servicio ni con los móviles reales de la casa.
"""
import asyncio
import time

from reflex.istate.data import RouterData

from tests.comun import Caso

from noxuscmmd.core import sesiones as sesiones_panel
from noxuscmmd.domains.auth import permisos, sessions, store
from noxuscmmd.domains.auth import state as auth_state_module
from noxuscmmd.domains.auth.admin_state import AuthAdminState
from noxuscmmd.domains.auth.state import (
    AuthState,
    _LIMITES_INTENTOS,
    _LIMITES_PUSH_ACCESO,
    _LIMITES_SOLICITUDES,
    _MAX_INTENTOS_IP,
    _MAX_INTENTOS_TOTAL,
    _MAX_PENDIENTES,
    _MAX_PUSH_ACCESO,
    _MAX_SOLICITUDES_IP,
    _MAX_SOLICITUDES_VISITANTE,
    _VENTANA_INTENTO,
    _admitir_intento,
    _admitir_solicitud,
    _ip_real,
    _olvidar_visitante,
)
from noxuscmmd.domains.security import logs, logs_store


def _router(ip: str = "10.0.0.2",
            reenviada: str = "203.0.113.8, 10.0.0.2") -> RouterData:
    return RouterData.from_router_data({
        "pathname": "/panel",
        "asPath": "/panel?vista=logs&invitacion=CODIGO-SECRETO&token=TOKEN-SECRETO",
        "query": {
            "vista": "logs",
            "invitacion": "CODIGO-SECRETO",
            "token": "TOKEN-SECRETO",
        },
        "ip": ip,
        "headers": {
            "origin": "https://panel.noxuscmmd.uk",
            "x-forwarded-for": reenviada,
            "x-real-ip": "198.51.100.4",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36"
            ),
            "accept-language": "es-ES,es;q=0.9",
            "referer": (
                "https://panel.noxuscmmd.uk/panel?invitacion=REFERER-SECRETO"
                "&vista=overview"
            ),
            "cookie": "noxus_sesion=COOKIE-QUE-NUNCA-DEBE-GUARDARSE",
        },
    })


def _estado(testigo: str = "", router: RouterData | None = None) -> AuthState:
    estado = AuthState(_reflex_internal_init=True)
    # ``router`` pertenece al estado raíz en Reflex; esta instancia aislada no
    # tiene padre, así que se coloca como hace el runtime antes del evento.
    object.__setattr__(estado, "router", router or _router())
    estado.testigo = testigo
    return estado


def _eventos(accion: str, entidad: str = "") -> list[dict]:
    return [
        e for e in logs_store.ultimos()
        if e["accion"] == accion and (not entidad or e["entidad"] == entidad)
    ]


def _visitante_no_crea_ficha() -> Caso:
    c = Caso("Un visitante no crea ficha al abrir")
    antes = set(store.leer()["dispositivos"])
    estado = _estado()
    estado.identificar()

    c.cierto("recibe un id efímero", bool(estado._id))
    c.revisar("el id no está persistido", store.dispositivo(estado._id), None)
    c.revisar("se resuelve como pendiente", estado._rol, store.PENDIENTE)
    c.revisar("no inventa un nombre", estado._nombre, "")
    c.revisar("no tiene permiso de entrada",
              permisos.puede(estado._id, permisos.VER), False)
    c.revisar("no cambia la lista de dispositivos",
              set(store.leer()["dispositivos"]), antes)

    intentos = _eventos("INTENTO_ACCESO", estado._id)
    c.revisar("queda un intento", len(intentos), 1)
    detalle = intentos[0]["detalle"] if intentos else ""
    c.cierto("ignora cabeceras de un origen no confiable", "IP 10.0.0.2" in detalle)
    c.cierto("resume navegador y sistema", "Chrome 126 en Windows" in detalle)
    c.cierto("guarda idioma y ruta útil",
             "idioma es-ES,es;q=0.9" in detalle and "vista=logs" in detalle)
    c.cierto("explica que faltaba la cookie", "motivo sin cookie" in detalle)
    prohibidos = (
        "CODIGO-SECRETO", "TOKEN-SECRETO", "REFERER-SECRETO",
        "COOKIE-QUE-NUNCA-DEBE-GUARDARSE",
    )
    c.revisar("no guarda cookies, invitaciones ni tokens",
              any(secreto in detalle for secreto in prohibidos), False)

    # La cookie firmada del visitante se reconoce dentro del proceso, pero la
    # ventana evita que cada recarga añada otra fila.
    estado.identificar()
    c.revisar("dos entradas seguidas dejan una sola fila",
              len(_eventos("INTENTO_ACCESO", estado._id)), 1)
    c.revisar("la ventana es exactamente de 30 minutos",
              _VENTANA_INTENTO, 30 * 60)

    # Simula que la ventana ya pasó sin dormir media hora.
    clave = f"acceso-app:{estado._id}"
    logs_store._antispam[clave] = time.monotonic() - 1
    estado.identificar()
    c.revisar("al caducar la ventana vuelve a registrar",
              len(_eventos("INTENTO_ACCESO", estado._id)), 2)

    _olvidar_visitante(estado._id)
    logs_store._antispam.pop(clave, None)
    return c


def _ip_de_proxy_confiable() -> Caso:
    c = Caso("La IP real solo confía en el VPS")
    c.revisar(
        "una conexión directa ignora X-Forwarded-For",
        _ip_real(_router("192.0.2.20", "198.51.100.9, 203.0.113.7")),
        "192.0.2.20",
    )
    c.revisar(
        "el VPS toma el último valor reenviado",
        _ip_real(_router("100.98.98.10", "198.51.100.9, 203.0.113.7")),
        "203.0.113.7",
    )
    c.revisar(
        "el VPS sin cabecera conserva la IP directa",
        _ip_real(_router("100.98.98.10", "")),
        "100.98.98.10",
    )
    return c


def _limites_de_entrada() -> Caso:
    c = Caso("Los intentos anónimos tienen límites globales acotados")
    _LIMITES_INTENTOS.vaciar()
    antes = len(_eventos("INTENTO_ACCESO"))
    visitantes = []
    for _ in range(_MAX_INTENTOS_IP + 3):
        estado = _estado(router=_router("192.0.2.44"))
        estado.identificar()
        visitantes.append(estado._id)
    despues = len(_eventos("INTENTO_ACCESO"))
    c.revisar("una IP no supera su cuota por minuto",
              despues - antes, _MAX_INTENTOS_IP)
    c.cierto("el contador mantiene memoria acotada",
             len(_LIMITES_INTENTOS._datos) <= _LIMITES_INTENTOS._max_claves)
    for visitante in visitantes:
        _olvidar_visitante(visitante)
        logs_store._antispam.pop(f"acceso-app:{visitante}", None)
    _LIMITES_INTENTOS.vaciar()
    admitidos = [
        _admitir_intento(f"198.51.100.{numero}")
        for numero in range(_MAX_INTENTOS_TOTAL)
    ]
    c.cierto("el cupo total admite justo su límite", all(admitidos))
    c.revisar("el cupo total corta la IP siguiente",
              _admitir_intento("203.0.113.250"), False)
    _LIMITES_INTENTOS.vaciar()
    return c


def _limites_de_solicitud() -> Caso:
    c = Caso("Las solicitudes y avisos de acceso están acotados")
    _LIMITES_SOLICITUDES.vaciar()
    _LIMITES_PUSH_ACCESO.vaciar()
    estado = _estado(router=_router("192.0.2.55"))
    estado.identificar()
    visitante = estado._id
    estado.nombre_acceso = "Marta"
    estado.nota_acceso = "Móvil nuevo"
    antes = len(_eventos("SOLICITUD_ACCESO", visitante))
    for numero in range(_MAX_SOLICITUDES_VISITANTE + 2):
        estado.nota_acceso = f"Móvil nuevo {numero}"
        estado.enviar_nota_acceso()
    c.revisar(
        "un visitante no puede inundar solicitudes",
        len(_eventos("SOLICITUD_ACCESO", visitante)) - antes,
        _MAX_SOLICITUDES_VISITANTE,
    )
    _LIMITES_SOLICITUDES.vaciar()
    admitidas_ip = [
        _admitir_solicitud("192.0.2.60", f"visitante-{numero}")
        for numero in range(_MAX_SOLICITUDES_IP)
    ]
    c.cierto("una IP admite solicitudes de visitantes distintos hasta el cupo",
             all(admitidas_ip))
    c.revisar("la IP corta aunque el visitante sea nuevo",
              _admitir_solicitud("192.0.2.60", "visitante-extra"), False)
    store.eliminar(visitante)

    creados = []
    faltan = max(0, _MAX_PENDIENTES - store.contar_pendientes())
    for numero in range(faltan):
        identificador = sessions.nuevo_id()
        store.alta(identificador, nombre=f"Pendiente {numero}", rol=store.PENDIENTE)
        creados.append(identificador)
    lleno = _estado(router=_router("192.0.2.56"))
    lleno.identificar()
    lleno.nombre_acceso = "Otra persona"
    lleno.nota_acceso = "Teléfono nuevo"
    lleno.enviar_nota_acceso()
    c.revisar("el tope impide crear la ficha pendiente 21",
              store.dispositivo(lleno._id), None)
    for identificador in creados:
        store.eliminar(identificador)
    _olvidar_visitante(lleno._id)
    logs_store._antispam.pop(f"acceso-app:{lleno._id}", None)

    c.cierto("el contador de push nunca supera su ventana",
             all(_LIMITES_PUSH_ACCESO.admitir(
                 (("total-prueba", _MAX_PUSH_ACCESO),), 600, ahora=0)
                 for _ in range(_MAX_PUSH_ACCESO)))
    c.revisar("el siguiente push se rechaza",
              _LIMITES_PUSH_ACCESO.admitir(
                  (("total-prueba", _MAX_PUSH_ACCESO),), 600, ahora=0), False)
    _LIMITES_SOLICITUDES.vaciar()
    _LIMITES_PUSH_ACCESO.vaciar()
    return c


def _cookie_de_ficha_borrada() -> Caso:
    c = Caso("Una ficha borrada no resucita por su cookie")
    borrado = sessions.nuevo_id()
    store.alta(borrado, nombre="Borrado", rol=store.FAMILIA)
    cookie = sessions.emitir(borrado)
    store.eliminar(borrado)

    estado = _estado(cookie)
    estado.identificar()
    c.cierto("recibe otro id", estado._id != borrado)
    c.revisar("la ficha antigua sigue borrada", store.dispositivo(borrado), None)
    c.revisar("el nuevo visitante tampoco tiene ficha",
              store.dispositivo(estado._id), None)
    intentos = _eventos("INTENTO_ACCESO", estado._id)
    c.cierto("el registro explica la ficha borrada",
             bool(intentos) and "cookie de una ficha borrada" in intentos[0]["detalle"])

    _olvidar_visitante(estado._id)
    logs_store._antispam.pop(f"acceso-app:{estado._id}", None)
    return c


def _solicitud_crea_ficha() -> Caso:
    c = Caso("La ficha nace al enviar nombre y motivo")
    estado = _estado()
    estado.identificar()
    visitante = estado._id

    estado.nombre_acceso = "   "
    estado.nota_acceso = ""
    estado.enviar_nota_acceso()
    c.revisar("sin los dos campos no crea nada",
              store.dispositivo(visitante), None)

    estado.vincular_push("https://push.example/visitante", "Marta")
    c.revisar("vincular push nuevo tampoco adelanta el alta",
              store.dispositivo(visitante), None)

    estado.nombre_acceso = "  Marta  "
    estado.nota_acceso = "  Móvil nuevo de casa  "
    estado.enviar_nota_acceso()
    ficha = store.dispositivo(visitante) or {}
    c.revisar("guarda el nombre recortado", ficha.get("nombre"), "Marta")
    c.revisar("guarda el motivo recortado", ficha.get("nota_acceso"),
              "Móvil nuevo de casa")
    c.revisar("nace sin permisos", ficha.get("rol"), store.PENDIENTE)
    c.revisar("conserva el endpoint recibido antes del alta", ficha.get("endpoint"),
              "https://push.example/visitante")

    solicitudes = _eventos("SOLICITUD_ACCESO", visitante)
    c.revisar("queda una solicitud enlazada al visitante", len(solicitudes), 1)
    detalle = solicitudes[0]["detalle"] if solicitudes else ""
    c.cierto("la solicitud trae motivo, IP y navegador",
             "Móvil nuevo de casa" in detalle
             and "IP 10.0.0.2" in detalle
             and "Chrome 126 en Windows" in detalle)
    c.revisar("la solicitud usa la familia propia",
              solicitudes[0]["categoria"] if solicitudes else "", logs.ACCESO_APP)

    store.eliminar(visitante)
    logs_store._antispam.pop(f"acceso-app:{visitante}", None)
    return c


def _push_e_invitacion_siguen_funcionando() -> Caso:
    c = Caso("Push conocido e invitación conservan sus altas")
    conocido = sessions.nuevo_id()
    endpoint = "https://push.example/conocido"
    store.alta(conocido, nombre="Tablet casa", rol=store.FAMILIA,
               endpoint=endpoint)
    estado = _estado()
    estado.identificar()
    efimero = estado._id
    estado.vincular_push(endpoint, "Tablet casa")
    c.revisar("el endpoint conocido adopta su ficha", estado._id, conocido)
    c.revisar("el visitante anterior no deja basura",
              store.dispositivo(efimero), None)
    store.eliminar(conocido)

    invitacion = store.crear_invitacion(1, "Admin de prueba")
    invitado = _estado()
    invitado.identificar()
    id_invitado = invitado._id
    invitado._canjear(invitacion, "Visita")
    ficha = store.dispositivo(id_invitado) or {}
    c.revisar("la invitación crea la ficha al dar acceso",
              ficha.get("rol"), store.INVITADO)
    c.revisar("la invitación conserva el nombre", ficha.get("nombre"), "Visita")

    store.revocar_invitacion(invitacion)
    store.eliminar(id_invitado)
    _olvidar_visitante(efimero)
    logs_store._antispam.pop(f"acceso-app:{efimero}", None)
    logs_store._antispam.pop(f"acceso-app:{id_invitado}", None)
    return c


def _invitaciones_no_viajan_al_cliente() -> Caso:
    c = Caso("Los códigos de invitación permanecen privados")
    codigo = store.crear_invitacion(1, "Admin de prueba", nota="Prueba privada")
    estado = AuthAdminState(_reflex_internal_init=True)
    estado._recargar()
    vars_publicas = {
        *AuthAdminState.base_vars,
        *AuthState.base_vars,
    }
    c.revisar("ninguna var base pública guarda códigos de invitación",
              any("codigo" in nombre or "invitacion_pendiente" in nombre
                  for nombre in vars_publicas), False)
    c.revisar("la lista pública no contiene el campo secreto",
              any("codigo" in invitacion for invitacion in estado.invitaciones), False)
    c.revisar("el valor secreto no aparece en la lista pública",
              codigo in repr(estado.invitaciones), False)
    c.cierto("el servidor conserva el código en una var privada",
             codigo in estado._codigos_invitacion.values())
    referencia = next(
        referencia for referencia, secreto in estado._codigos_invitacion.items()
        if secreto == codigo
    )
    store.revocar_invitacion(estado._codigos_invitacion[referencia])

    class _CargaFalsa:
        def __init__(self, permiso):
            self.permiso = permiso
            self.recargas = 0
            self.vaciados = 0

        async def _puede_cargar_ajustes(self):
            return self.permiso

        def _recargar(self):
            self.recargas += 1

        def _vaciar(self):
            self.vaciados += 1

    sin_permiso = _CargaFalsa(False)
    con_permiso = _CargaFalsa(True)

    class _CopiaFalsa(_CargaFalsa):
        _codigos_invitacion = {"ref-segura": codigo}

    copia = _CopiaFalsa(True)
    bucle = asyncio.new_event_loop()
    try:
        bucle.run_until_complete(AuthAdminState.on_load.fn(sin_permiso))
        bucle.run_until_complete(AuthAdminState.on_load.fn(con_permiso))
        evento_copia = bucle.run_until_complete(
            AuthAdminState.copiar_enlace.fn(copia, "ref-segura"))
    finally:
        bucle.close()
    c.revisar("sin AJUSTES vacía y no carga las listas",
              (sin_permiso.vaciados, sin_permiso.recargas), (1, 0))
    c.revisar("con AJUSTES carga las listas",
              (con_permiso.vaciados, con_permiso.recargas), (0, 1))
    c.cierto("el evento autorizado arma el enlace solo al pulsarlo",
             codigo in repr(evento_copia)
             and "window.location.origin" in repr(evento_copia))
    return c


def _recarga_al_recibir_acceso() -> Caso:
    c = Caso("Dar acceso recarga una sesión que entró cerrada")

    class _EstadoVigilado:
        _id = "visitante-prueba"
        _rol = store.PENDIENTE

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        # Lo que la vigilancia compara para el rol kiosco (tablet de habitación)
        _kiosco_estancia = ""
        _kiosco_camaras = False

        def _redireccion_kiosco(self):
            return ""

        def _ve(self, capacidad):
            return permisos.puede_rol(self._rol, capacidad)

        def _refrescar(self):
            self._rol = store.FAMILIA

    async def guardia_falsa(_estado):
        return object()

    async def hilo_falso(funcion, *args):
        return funcion(*args)

    guardia_original = sesiones_panel.guardia
    rol_original = store.rol_de
    hilo_original = auth_state_module.asyncio.to_thread
    sesiones_panel.guardia = guardia_falsa
    store.rol_de = lambda _identificador: store.FAMILIA
    auth_state_module.asyncio.to_thread = hilo_falso
    bucle = asyncio.new_event_loop()
    generador = AuthState.vigilar_acceso.fn(_EstadoVigilado())
    try:
        evento = bucle.run_until_complete(anext(generador))
        c.cierto("emite window.location.reload al pasar a VER",
                 "window.location.reload()" in repr(evento))
        bucle.run_until_complete(generador.aclose())
    finally:
        bucle.close()
        sesiones_panel.guardia = guardia_original
        store.rol_de = rol_original
        auth_state_module.asyncio.to_thread = hilo_original
    return c


def ejecutar() -> list[Caso]:
    aviso_original = AuthState._avisar_de_desconocido
    emitir_original = logs.n8n.emitir

    # No se contacta con móviles ni workflows durante la suite. Se mantiene la
    # marca que consume el banner para comprobar el mismo flujo de persistencia.
    AuthState._avisar_de_desconocido = (
        lambda self, _nombre, _nota="": store.actualizar(
            self._id, pide_acceso=True)
    )
    logs.n8n.emitir = lambda **_kwargs: None
    try:
        return [
            _visitante_no_crea_ficha(),
            _ip_de_proxy_confiable(),
            _limites_de_entrada(),
            _cookie_de_ficha_borrada(),
            _solicitud_crea_ficha(),
            _limites_de_solicitud(),
            _push_e_invitacion_siguen_funcionando(),
            _invitaciones_no_viajan_al_cliente(),
            _recarga_al_recibir_acceso(),
        ]
    finally:
        AuthState._avisar_de_desconocido = aviso_original
        logs.n8n.emitir = emitir_original
