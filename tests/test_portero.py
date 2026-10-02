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
from noxuscmmd.domains.devices.registry_state import RegistryState
from noxuscmmd.domains.nodes.state import NodesState
from noxuscmmd.domains.notifications import push
from noxuscmmd.domains.notifications.state import PushState
from noxuscmmd.domains.electro.state import ElectroState
from noxuscmmd.domains.security.arming_state import ArmingState
from noxuscmmd.domains.security.groups_state import GroupsState
from noxuscmmd.ui.dashboard.state import DashboardState


def _n(estado, handler: str) -> str:
    return f"{estado.get_full_name()}.{handler}"


def _puede(rol: str, evento: str, camaras: bool = False) -> bool:
    def ve(cap):
        return permisos.puede_rol(rol, cap)
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
                    (_n(PushState, "lanzar_alerta_global_con_subscripcion"),
                     "mandar una alerta a toda la casa"),
                    (_n(NodesState, "setvar"), "escribir una variable")):
        c.cierto(f"NO puede {que}", not _puede(store.PENDIENTE, ev))
    alerta = _n(PushState, "lanzar_alerta_global_con_subscripcion")
    c.cierto("un invitado no manda alertas a la casa", not _puede(store.INVITADO, alerta))
    c.cierto("la familia sí", _puede(store.FAMILIA, alerta))
    return c


def _avisos_solo_con_acceso() -> Caso:
    """Darse de alta en push no da derecho a recibir los avisos de la casa."""
    c = Caso("Los avisos push solo llegan a aparatos con acceso")
    original = store.leer
    ficha = lambda rol, ep: {"rol": rol, "endpoint": ep, "nombre": rol}
    store.leer = lambda: {"dispositivos": {
        "a": ficha(store.ADMIN, "ep-admin"),
        "i": ficha(store.INVITADO, "ep-invitado"),
        "p": ficha(store.PENDIENTE, "ep-pendiente"),
        "b": ficha(store.BLOQUEADO, "ep-bloqueado"),
    }, "invitaciones": {}}
    try:
        vivos = push._endpoints_con_acceso()
    finally:
        store.leer = original
    c.cierto("el administrador recibe", "ep-admin" in vivos)
    c.cierto("el invitado recibe", "ep-invitado" in vivos)
    c.cierto("el pendiente NO recibe", "ep-pendiente" not in vivos)
    c.cierto("el bloqueado NO recibe", "ep-bloqueado" not in vivos)
    c.cierto("un endpoint sin ficha NO recibe", "ep-desconocido" not in vivos)
    return c


def _roles_normales() -> Caso:
    c = Caso("El resto de roles siguen con sus permisos de siempre")
    cmd = _n(InfraState, "ejecutar_comando_personalizado")
    c.cierto("un administrador puede lanzar comandos", _puede(store.ADMIN, cmd))
    c.cierto("un familiar no (son ajustes)", not _puede(store.FAMILIA, cmd))
    c.cierto("un familiar sí enciende luces", _puede(store.FAMILIA, _n(NodesState, "toggle_light")))
    for ev, que in ((_n(NodesState, "save_floor_positions"), "recolocar el plano"),
                    (_n(NodesState, "submit_learn_ir_button"), "añadir un botón IR"),
                    (_n(RegistryState, "hide_entity"), "ocultar una entidad")):
        c.cierto(f"un familiar NO puede {que}", not _puede(store.FAMILIA, ev))
        c.cierto(f"un administrador sí puede {que}", _puede(store.ADMIN, ev))
    c.cierto("los eventos internos de Reflex pasan siempre",
             _puede(store.PENDIENTE, "reflex___state____state.hydrate")
             and _puede(store.KIOSCO,
                        "reflex___state____state.reflex___state____on_load_internal_state.on_load_internal"))
    return c


def _cobertura() -> Caso:
    """Ningún manejador nuevo queda abierto por olvido: o comprueba el permiso
    él mismo, o tiene regla en el portero, o se ha revisado a mano y está en
    tests/portero_revisados.txt."""
    import inspect
    from pathlib import Path

    import noxuscmmd.noxuscmmd  # noqa: F401 — registra todos los State
    from reflex.state import State

    c = Caso("Todo manejador del navegador tiene permiso o está revisado")
    revisados = {l.strip() for l in
                 (Path(__file__).parent / "portero_revisados.txt").read_text().splitlines()
                 if l.strip() and not l.startswith("#")}
    tabla = portero.tablas()["requiere"]

    def recorrer(estado):
        yield estado
        for hijo in estado.get_substates():
            yield from recorrer(hijo)

    sueltos = []
    for st in recorrer(State):
        if not st.__module__.startswith("noxuscmmd"):
            continue
        for nombre, h in st.event_handlers.items():
            if nombre == "setvar" or f"{st.get_full_name()}.{nombre}" in tabla:
                continue
            try:
                fuente = inspect.getsource(h.fn)
            except (OSError, TypeError):
                fuente = ""
            if any(k in fuente for k in ("denegar", "_tiene(", "puede(")):
                continue
            if f"{st.__name__}.{nombre}" not in revisados:
                sueltos.append(f"{st.__name__}.{nombre}")
    c.cierto("sin manejadores nuevos sin permiso (añade denegar o regla en el portero): "
             + ", ".join(sueltos[:8]), not sueltos)
    return c


def ejecutar() -> list[Caso]:
    return [_tablet(), _sin_acceso(), _roles_normales(), _avisos_solo_con_acceso(),
            _cobertura()]
