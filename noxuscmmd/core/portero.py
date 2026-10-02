"""El portero de eventos: filtra en el SERVIDOR lo que un navegador puede pedir.

POR QUÉ EXISTE. En Reflex cualquier manejador de eventos se puede invocar desde
el navegador aunque ningún botón lo pinte: basta mandar su nombre por el
websocket. Comprobar el permiso dentro de cada manejador (permisos.denegar) es
lo correcto, pero es una regla que se olvida: una revisión de seguridad (2026-09-25)
encontró manejadores sin ninguna comprobación —la paleta de comandos, cortar el
pulso de una puerta, la consola SSH de los equipos— que una tablet de habitación,
o hasta un visitante sin acceso, podía lanzar contra cualquier aparato de la casa.

En vez de tapar solo esos, el portero es un punto ÚNICO por el que pasa cada evento
que llega del navegador (middleware de Reflex), y aplica tres reglas:

1. Una tablet de habitación (rol `kiosco`) solo puede lanzar una lista corta y
   cerrada de eventos (PERMITIDOS_KIOSCO). Todo lo demás se rechaza, exista o no
   una comprobación dentro del manejador. Lo que sí permite (luces, puertas,
   mandos, botones de equipos) ya comprueba además que el control sea de SU
   habitación (permisos.denegar_entidad). Armar y desarmar es de toda la casa.
2. Quien no tiene acceso al panel solo puede identificarse y pedirlo
   (PERMITIDOS_SIN_ACCESO).
3. Una lista de manejadores delicados (comandos SSH, GPIO, deshacer…) exige su
   capacidad a todos los demás roles, con la misma regla del resto del panel
   (AuthState._ve).

Los eventos internos de Reflex (hidratar, on_load_internal…) pasan siempre. Los de
fondo que lanza el propio servidor (core/entrada.py) no pasan por aquí: no vienen
del navegador.

La decisión (`decidir`) es una función pura para poder probarla sin Reflex.
"""
import time

from reflex.middleware import Middleware
from reflex.state import StateUpdate

_TABLAS: dict | None = None
_AVISADOS: dict[tuple[str, str], float] = {}


def _handlers(estado, sin: tuple[str, ...] = ("setvar",)) -> set[str]:
    base = estado.get_full_name()
    return {f"{base}.{h}" for h in estado.event_handlers if h not in sin}


def _uno(estado, *nombres: str) -> set[str]:
    base = estado.get_full_name()
    return {f"{base}.{n}" for n in nombres}


def tablas() -> dict:
    """Las listas, construidas la primera vez que hacen falta (los states ya
    existen entonces) y con los nombres completos que usa Reflex en cada evento."""
    global _TABLAS
    if _TABLAS is not None:
        return _TABLAS
    from ..domains.auth import permisos
    from ..domains.auth.state import AuthState
    from ..domains.infra.deshacer import DeshacerState
    from ..domains.infra.pruebas_state import PruebasState
    from ..domains.infra.state import InfraState
    from ..domains.electro.state import ElectroState
    from ..domains.devices.registry_state import RegistryState
    from ..domains.automations.state import AutomationsState
    from ..domains.nodes.estancias_state import EstanciasState
    from ..domains.nodes.host_actions_state import HostActionsState
    from ..domains.nodes.kiosco_state import KioscoState
    from ..domains.nodes.state import NodesState
    from ..domains.notifications.alertas_state import AlertasState
    from ..domains.notifications.state import PushState
    from ..domains.security.arming_state import ArmingState
    from ..ui.dashboard.state import DashboardState

    # AuthState y PushState conservan `setvar`: son las pantallas de pedir acceso
    # y vincular el aparato, que ya funcionaban así antes del portero.
    sin_acceso = (
        _handlers(AuthState, ()) | _handlers(PushState, ())
        | _uno(DashboardState, "entrar") | _uno(KioscoState, "entrar")
    )
    # Mandar avisos no es «identificarse»: PushState entero está abierto a quien
    # no tiene acceso, pero esto sale a los móviles de toda la casa.
    sin_acceso -= _uno(PushState, "lanzar_alerta_global_con_subscripcion")
    kiosco = (
        sin_acceso | _handlers(KioscoState) | _handlers(AlertasState)
        | _uno(NodesState, "toggle_light", "open_door", "set_door_hold",
               "send_ir_button", "send_ir_button_combined")
        | _uno(ElectroState, "electro_cmd")
        | _uno(HostActionsState, "accion_rapida", "encender_wol", "run_button")
        # Armar y desarmar la casa, con su aviso de «esto está abierto» y la
        # cuenta atrás de salida. Solo ArmingState: tocar grupos sigue fuera.
        | _handlers(ArmingState)
    )
    camaras_kiosco: set[str] = set()

    requiere: dict[str, str] = {}
    for h in ("ejecutar_comando_personalizado", "set_custom_command"):
        requiere.update({n: permisos.AJUSTES for n in _uno(InfraState, h)})
    for h in ("run_accion_extra", "accion_apagar", "accion_reiniciar", "accion_gpio",
              "wake_pc", "rdp_pc", "rdp_portatil", "rdp_raspberry"):
        requiere.update({n: permisos.EQUIPOS for n in _uno(InfraState, h)})
    requiere.update({n: permisos.CAMARAS for n in _uno(InfraState, "tomar_foto_raspberry")})
    requiere.update({n: permisos.AVISAR
                     for n in _uno(PushState, "lanzar_alerta_global_con_subscripcion")})
    for h in ("apuntar", "deshacer"):
        requiere.update({n: permisos.AJUSTES for n in _uno(DeshacerState, h)})
    requiere.update({n: permisos.AJUSTES for n in _handlers(PruebasState)})
    requiere.update({n: permisos.AJUSTES for n in _handlers(EstanciasState)})
    # Edición sin comprobación propia en el manejador (la UI ya la esconde tras
    # AuthState.puede_ajustes, pero esconder no es un permiso): recolocar el
    # plano, tocar los botones de un mando IR/RF y ocultar o aislar entidades.
    requiere.update({n: permisos.AJUSTES for n in _uno(
        NodesState, "save_floor_positions", "set_floor_pos",
        "save_ir_button_positions", "learn_into_button", "submit_learn_ir_button")})
    requiere.update({n: permisos.AJUSTES for n in _uno(
        RegistryState, "hide_entity", "unhide_entity", "toggle_isolated")})
    # Sirena de la tablet (la tablet misma se salta `requiere`: ver decidir) y
    # copiar reglas de automatización, que persisten sin comprobar al llamarlas.
    requiere.update({n: permisos.AJUSTES for n in _uno(
        KioscoState, "alternar_sirena", "elegir_sonido", "elegir_volumen")})
    requiere.update({n: permisos.AJUSTES for n in _uno(AutomationsState, "duplicate_rule")})
    requiere.update({n: permisos.PUERTAS
                     for n in _uno(NodesState, "cut_door_pulse", "set_door_hold")})

    _TABLAS = {"sin_acceso": sin_acceso, "kiosco": kiosco,
               "camaras_kiosco": camaras_kiosco, "requiere": requiere}
    return _TABLAS


def es_interno(nombre: str) -> bool:
    """Eventos de Reflex mismo: `<raíz>.hydrate` o de un estado interno."""
    partes = nombre.split(".")
    return len(partes) <= 2 or partes[1].startswith("reflex___")


def decidir(nombre: str, rol: str, ve, camaras_kiosco: bool, tabla: dict) -> bool:
    """¿Puede una sesión con este rol lanzar este evento?

    `ve(capacidad)` es AuthState._ve: lo que la interfaz enseña a esa sesión.
    """
    from ..domains.auth import permisos, store

    if es_interno(nombre):
        return True
    if rol == store.KIOSCO:
        if nombre in tabla["kiosco"]:
            return True
        return bool(camaras_kiosco and nombre in tabla["camaras_kiosco"])
    if not ve(permisos.VER):
        return nombre in tabla["sin_acceso"]
    capacidad = tabla["requiere"].get(nombre)
    return capacidad is None or bool(ve(capacidad))


def _avisar(rol: str, nombre: str) -> None:
    """Deja rastro del rechazo sin que un visitante pueda inundar el log."""
    ahora = time.time()
    clave = (rol, nombre)
    if len(_AVISADOS) > 300:
        _AVISADOS.clear()
    if ahora - _AVISADOS.get(clave, 0) > 60:
        _AVISADOS[clave] = ahora
        print(f"🛑 Portero: evento rechazado ({rol or 'sin rol'}) → {nombre.rsplit('.', 1)[-1]}")


class PorteroDeEventos(Middleware):
    async def preprocess(self, app, state, event):
        nombre = event.name or ""
        if es_interno(nombre):
            return None
        from ..domains.auth.state import AuthState

        try:
            auth = await state.get_state(AuthState)
            rol = auth._rol
            permitido = decidir(nombre, rol, auth._ve,
                                bool(getattr(auth, "_kiosco_camaras", False)), tablas())
        except Exception as e:
            # Sin saber quién es la sesión no se deja pasar nada que no sea
            # entrar o pedir acceso.
            print(f"⚠️ Portero: no se pudo decidir {nombre.rsplit('.', 1)[-1]}: {e}")
            rol = ""
            try:
                permitido = nombre in tablas()["sin_acceso"]
            except Exception:
                permitido = False
        if permitido:
            return None
        _avisar(rol, nombre)
        return StateUpdate(final=True)
