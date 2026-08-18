"""Qué puede hacer cada rol, y la comprobación que usan los manejadores.

Lo importante de este módulo: **esconder un botón no es un permiso**. Cada
evento de un State viaja por el websocket y puede invocarlo cualquier navegador
conectado, esté o no el botón pintado en su pantalla. Por eso la comprobación
de verdad va aquí dentro, llamada desde el propio manejador, y lo de la
interfaz (ui/) es solo para no enseñar lo que no se va a poder usar.
"""
from . import store

# ── Capacidades ──────────────────────────────────────────────────────────
VER = "ver"            # entrar al panel
LUCES = "luces"        # encender y apagar luces
PUERTAS = "puertas"    # abrir accesos
ARMAR = "armar"        # armar y desarmar, y tocar los grupos
EQUIPOS = "equipos"    # encender/apagar ordenadores, mandos
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
    store.ADMIN: {VER, LUCES, PUERTAS, ARMAR, EQUIPOS, CAMARAS, AVISAR, AJUSTES},
    store.FAMILIA: {VER, LUCES, PUERTAS, ARMAR, EQUIPOS, CAMARAS, AVISAR},
    store.INVITADO: {VER, LUCES, EQUIPOS},
    store.PENDIENTE: set(),
    store.BLOQUEADO: set(),
}

# Lo que se le dice a quien no llega. Sin jerga y sin detalles de más: si
# alguien está probando puertas, tampoco hace falta explicarle el mapa.
_NEGATIVA = {
    ARMAR: "Este dispositivo no puede armar ni desarmar la casa.",
    PUERTAS: "Este dispositivo no puede abrir accesos.",
    EQUIPOS: "Este dispositivo no puede encender ni apagar equipos.",
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
    return puede_rol(store.rol_de(id_dispositivo), capacidad)


def motivo(capacidad: str) -> str:
    return _NEGATIVA.get(capacidad, "Este dispositivo no puede hacer eso.")


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
        return rx.toast.error(motivo(capacidad), position="top-center")

    if auth._tiene(capacidad):
        return None

    quien = auth.nombre_dispositivo or audit.DESCONOCIDO
    su_rol = store.NOMBRES_DE_ROL.get(auth.rol_actual, auth.rol_actual)

    # Rodaje: se apunta lo que se habría impedido, pero se deja pasar. Sirve
    # para ver durante unos días quién haría qué antes de cerrar la puerta, y
    # para que encender los permisos no deje a nadie tirado sin avisar.
    if not store.estricto():
        logs.registrar(
            logs.ACCESOS, "ACCESO_DENEGADO", quien,
            f"«{capacidad}» siendo {su_rol} — PERMITIDO: los permisos aún no "
            "están en vigor",
        )
        return None

    logs.registrar(
        logs.ACCESOS, "ACCESO_DENEGADO", quien,
        f"intentó «{capacidad}» siendo {su_rol}",
    )
    return rx.toast.error(motivo(capacidad), position="top-center")
