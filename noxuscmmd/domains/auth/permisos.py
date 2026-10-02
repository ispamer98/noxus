"""Qué puede hacer cada rol, y la comprobación que usan los manejadores.

Lo importante de este módulo: **esconder un botón no es un permiso**. Cada
evento de un State viaja por el websocket y puede invocarlo cualquier navegador
conectado, esté o no el botón pintado en su pantalla. Por eso la comprobación
de verdad va aquí dentro, llamada desde el propio manejador, y lo de la
interfaz (ui/) es solo para no enseñar lo que no se va a poder usar.
"""
import reflex as rx

from . import store

# ── Capacidades ──────────────────────────────────────────────────────────
VER = "ver"            # entrar al panel
LUCES = "luces"        # encender y apagar luces
PUERTAS = "puertas"    # abrir accesos
ARMAR = "armar"        # armar y desarmar, y tocar los grupos
EQUIPOS = "equipos"    # encender/apagar ordenadores, mandos
MANDOS = "mandos"      # pulsar mandos IR/RF o por red
CAMARAS = "camaras"    # VER imagen: mural, CCTV, marcadores de cámara del plano
AVISAR = "avisar"      # mandar un aviso a los móviles de la casa
AJUSTES = "ajustes"    # configuración, dispositivos, invitaciones

## Qué puede cada rol. Cuatro niveles y una frase para cada uno:
#
#   admin     todo, incluida cualquier edición o configuración.
#   familia   actuar sobre TODO (luces, puertas, armar, equipos) pero NO editar
#             nada: ni dar de alta, ni cambiar fichas, ni tocar ajustes. Es la
#             diferencia entre usar la casa y reconfigurarla.
#   invitado  las cosas «lógicas»: luces, mandos, encender y apagar equipos. NO
#             abre puertas, NO arma ni desarma, NO VE LAS CÁMARAS y NO puede
#             mandar avisos: un aviso sale con la cara del panel a los móviles
#             de la familia, así que quien no vive en la casa no lo manda. Lo de las
#             cámaras es lo que menos se ve venir y lo más importante: sin ello,
#             un invitado que entra en el Mural tiene imagen del interior de la
#             casa aunque no pueda tocar ningún botón. Mirar ya es acceso.
#   pendiente nada, ni entrar. Sin VER no se le carga ni la página (ver
#             ui/pages/dashboard.py).
#   bloqueado igual que pendiente, pero dicho a propósito: es el «no» de un
#             administrador, no un aparato que espera respuesta, así que deja de
#             salir en la lista de los que piden acceso.
_POR_ROL = {
    store.ADMIN: {VER, LUCES, PUERTAS, ARMAR, EQUIPOS, MANDOS, CAMARAS, AVISAR, AJUSTES},
    store.FAMILIA: {VER, LUCES, PUERTAS, ARMAR, EQUIPOS, MANDOS, CAMARAS, AVISAR},
    store.INVITADO: {VER, LUCES, EQUIPOS, MANDOS},
    # La tablet de pared arma y desarma (2026-09-29): está en casa, a mano, y
    # es donde se arma al salir. Solo el armado: los grupos no los edita
    # (core/portero.py le deja lanzar únicamente los eventos de ArmingState).
    store.KIOSCO: {VER, LUCES, PUERTAS, ARMAR, EQUIPOS, MANDOS},
    store.PENDIENTE: set(),
    store.BLOQUEADO: set(),
}

# Lo que se le dice a quien no llega. Sin jerga y sin detalles de más: si
# alguien está probando puertas, tampoco hace falta explicarle el mapa.
_NEGATIVA = {
    ARMAR: "Este dispositivo no puede armar ni desarmar la casa.",
    PUERTAS: "Este dispositivo no puede abrir accesos.",
    EQUIPOS: "Este dispositivo no puede encender ni apagar equipos.",
    MANDOS: "Este dispositivo no puede usar mandos.",
    AJUSTES: "Solo un administrador puede cambiar la configuración.",
    LUCES: "Este dispositivo no puede tocar las luces.",
    CAMARAS: "Este dispositivo no tiene acceso a las cámaras.",
    AVISAR: "Este dispositivo no puede mandar avisos a los móviles de la casa.",
    VER: "Este dispositivo todavía no tiene acceso al panel.",
}


def capacidades(rol: str) -> set[str]:
    return _POR_ROL.get(rol, set())


def puede_rol(rol: str, capacidad: str) -> bool:
    return capacidad in capacidades(rol)


def puede(id_dispositivo: str, capacidad: str) -> bool:
    """La pregunta completa: mira el rol vigente del aparato, ya con su
    caducidad contada."""
    rol = store.rol_de(id_dispositivo)
    if rol == store.KIOSCO:
        # Una ficha a medio configurar no abre ni el kiosco. Cámaras es una
        # concesión separada y explícita porque muestra el interior de casa.
        if not store.estancia_kiosco(id_dispositivo):
            return False
        if capacidad == CAMARAS:
            return store.kiosco_puede_camaras(id_dispositivo)
    return puede_rol(rol, capacidad)


def entidad_permitida(id_dispositivo: str, referencia: str) -> bool:
    """Acota las acciones de una tablet a los miembros de su estancia."""
    if store.rol_de(id_dispositivo) != store.KIOSCO:
        return True
    from ..nodes import store as nodes_store

    estancia = store.estancia_kiosco(id_dispositivo)
    return bool(estancia and nodes_store.referencia_en_estancia(
        estancia, referencia))


def motivo(capacidad: str) -> str:
    return _NEGATIVA.get(capacidad, "Este dispositivo no puede hacer eso.")


def _quien_lo_pidio() -> str:
    """Qué manejador pidió el permiso, para que el registro lo diga.

    Sin esto, la entrada era «intentó ajustes siendo Familia» y no había forma
    de saber QUÉ había intentado: pasó de verdad —una persona de la familia
    recibió un «acceso no autorizado» que no entendía, y averiguar de dónde
    salía costó leer todos los manejadores que piden ajustes—. Con el nombre
    delante se lee solo.

    Nunca levanta: esto solo adorna un registro y no puede tumbar la
    comprobación de permisos, que es lo que gobierna las cerraduras.
    """
    import sys
    try:
        marco = sys._getframe(2)          # 0 esta función, 1 denegar, 2 quien llama
        funcion = marco.f_code.co_name
        duenno = marco.f_locals.get("self")
        clase = type(duenno).__name__ if duenno is not None else ""
        return f" · en {clase}.{funcion}" if clase else f" · en {funcion}"
    except Exception:
        return ""


async def denegar(state, capacidad: str):
    """Comprobación para usar al principio de un manejador crítico.

    Devuelve None si puede seguir, o un aviso listo para devolver si no. Los
    manejadores quedan así:

        if (no := await permisos.denegar(self, permisos.ARMAR)):
            return no

    Cada intento denegado queda en el registro: si alguien se dedica a llamar
    eventos a mano, se ve.
    """
    import reflex as rx
    from .state import AuthState
    from ..security import audit, logs

    try:
        auth = await state.get_state(AuthState)
    except Exception:
        # Sin poder resolver quién es, no se deja pasar. Fallar hacia el lado
        # cerrado: esto gobierna cerraduras.
        return rx.toast.error(motivo(capacidad))

    if auth._tiene(capacidad):
        return None

    quien = auth.nombre_dispositivo or audit.DESCONOCIDO
    su_rol = store.NOMBRES_DE_ROL.get(auth.rol_actual, auth.rol_actual)
    donde = _quien_lo_pidio()

    # Rodaje: se apunta lo que se habría impedido, pero se deja pasar. Sirve
    # para ver durante unos días quién haría qué antes de cerrar la puerta, y
    # para que encender los permisos no deje a nadie tirado sin avisar.
    if not store.estricto():
        logs.registrar(
            logs.ACCESOS, "ACCESO_DENEGADO", quien,
            f"«{capacidad}» siendo {su_rol}{donde} — PERMITIDO: los permisos aún "
            "no están en vigor",
        )
        return None

    logs.registrar(
        logs.ACCESOS, "ACCESO_DENEGADO", quien,
        f"intentó «{capacidad}» siendo {su_rol}{donde}",
    )
    return rx.toast.error(motivo(capacidad))


async def denegar_entidad(state, capacidad: str, referencia: str):
    """Permiso de capacidad más el límite físico de una tablet de estancia."""
    if (no := await denegar(state, capacidad)):
        return no
    from .state import AuthState

    try:
        auth = await state.get_state(AuthState)
        permitido = entidad_permitida(auth._id, referencia)
    except Exception:
        permitido = False
    if permitido:
        return None
    return rx.toast.error("Este control no pertenece a esta habitación.")
