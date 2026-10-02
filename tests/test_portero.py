"""El portero de eventos: qué puede lanzar cada tipo de sesión.

Prueba la decisión pura (core/portero.decidir) con los nombres reales de los
eventos de Reflex; no arranca la aplicación ni toca nada de la casa.
"""
from tests.comun import Caso

from noxuscmmd.core import portero
from noxuscmmd.domains.auth import permisos, store
from noxuscmmd.domains.auth.state import AuthState
from noxuscmmd.domains.devices.paleta_state import PaletaState
from noxuscmmd.domains.infra.state import InfraState
from noxuscmmd.domains.nodes.host_actions_state import HostActionsState
from noxuscmmd.domains.nodes.kiosco_state import KioscoState
from noxuscmmd.domains.nodes.state import NodesState
from noxuscmmd.domains.electro.state import ElectroState
from noxuscmmd.domains.security.arming_state import ArmingState
from noxuscmmd.domains.security.groups_state import GroupsState
from noxuscmmd.ui.dashboard.state import DashboardState


def _n(estado, handler: str) -> str:
    return f"{estado.get_full_name()}.{handler}"


def _puede(rol: str, evento: str, camaras: bool = False, bloqueo: bool = True) -> bool:
    def ve(cap):
        return (not bloqueo) or permisos.puede_rol(rol, cap)
    return portero.decidir(evento, rol, ve, camaras, portero.tablas())


def _tablet() -> Caso:
    c = Caso("Una tablet de habitación solo lanza su lista corta")
    for ev, que in ((_n(NodesState, "toggle_light"), "encender una luz"),
                    (_n(NodesState, "open_door"), "abrir una puerta"),
                    (_n(NodesState, "send_ir_button"), "pulsar un mando"),
                    (_n(HostActionsState, "accion_rapida"), "acción rápida de un equipo"),
                    (_n(KioscoState, "abrir_overlay"), "abrir una hoja"),
                    (_n(KioscoState, "entrar"), "entrar en el kiosco"),
                    (_n(ArmingState, "pedir_armar"), "armar o desarmar"),
                    (_n(NodesState, "set_door_hold"), "bloquear o desbloquear su puerta"),
                    (_n(ElectroState, "electro_cmd"), "manejar un electrodoméstico"),
                    (_n(ArmingState, "armar_excluyendo"), "armar dejando fuera lo abierto"),
                    (_n(ArmingState, "cancelar_cuenta"), "cancelar la cuenta de salida")):
        c.cierto(f"puede {que}", _puede(store.KIOSCO, ev))
    for ev, que in ((_n(PaletaState, "ejecutar"), "la paleta de comandos"),
                    (_n(NodesState, "cut_door_pulse"), "cortar el pulso de una puerta"),
                    (_n(HostActionsState, "run_console_command"), "la consola de un equipo"),
                    (_n(InfraState, "ejecutar_comando_personalizado"), "un comando SSH"),
                    (_n(InfraState, "accion_gpio"), "mover un relé"),
                    (_n(NodesState, "setvar"), "escribir una variable a mano"),
                    (_n(DashboardState, "set_view"), "cambiar de vista del panel"),
                    (_n(GroupsState, "toggle_group_armed"), "tocar un grupo de armado"),
                    (_n(GroupsState, "delete_group"), "borrar un grupo")):
        c.cierto(f"NO puede {que}", not _puede(store.KIOSCO, ev))
    c.cierto("ni en rodaje se le abre nada más",
             not _puede(store.KIOSCO, _n(PaletaState, "ejecutar"), bloqueo=False))
    return c


def _sin_acceso() -> Caso:
    c = Caso("Quien no tiene acceso solo puede identificarse y pedirlo")
    c.cierto("puede identificarse", _puede(store.PENDIENTE, _n(AuthState, "identificar")))
    c.cierto("puede pedir acceso", _puede(store.PENDIENTE, _n(AuthState, "enviar_nota_acceso")))
    c.cierto("puede entrar", _puede(store.PENDIENTE, _n(DashboardState, "entrar")))
    for ev, que in ((_n(NodesState, "toggle_light"), "encender una luz"),
                    (_n(InfraState, "accion_apagar"), "apagar un equipo"),
                    (_n(InfraState, "ejecutar_comando_personalizado"), "un comando SSH"),
                    (_n(PaletaState, "ejecutar"), "la paleta"),
                    (_n(NodesState, "setvar"), "escribir una variable")):
        c.cierto(f"NO puede {que}", not _puede(store.PENDIENTE, ev))
    return c


def _roles_normales() -> Caso:
    c = Caso("El resto de roles siguen con sus permisos de siempre")
    cmd = _n(InfraState, "ejecutar_comando_personalizado")
    c.cierto("un administrador puede lanzar comandos", _puede(store.ADMIN, cmd))
    c.cierto("un familiar no (son ajustes)", not _puede(store.FAMILIA, cmd))
    c.cierto("un familiar sí enciende luces", _puede(store.FAMILIA, _n(NodesState, "toggle_light")))
    c.cierto("los eventos internos de Reflex pasan siempre",
             _puede(store.PENDIENTE, "reflex___state____state.hydrate")
             and _puede(store.KIOSCO,
                        "reflex___state____state.reflex___state____on_load_internal_state.on_load_internal"))
    return c


def ejecutar() -> list[Caso]:
    return [_tablet(), _sin_acceso(), _roles_normales()]
