"""
Centro de Control (/panel) — banco de pruebas para la futura migración.

Shell tipo NVR profesional (sidebar + topbar + ventanas flotantes
arrastrables) construido encima de los mismos domain states que la vista
clásica (SecurityState, InfraState, PushState). No introduce
lógica de negocio nueva: reutiliza device_list_view, device_controls_view,
photo_dialog y los estados de dominio.
"""
import reflex as rx

from ...domains.electro.state import ElectroState

from ...domains.security.state import SecurityState
from ...domains.security.groups_state import GroupsState
from ...domains.infra.state import InfraState
from ...domains.nodes.state import NodesState
from ...domains.devices.registry_state import RegistryState
from ...domains.nodes.host_actions_state import HostActionsState
from ...domains.access.state import AccessControlState
from ...domains.notifications.alertas_state import AlertasState
from ...domains.security.logs_state import LogsState
from ...domains.automations.state import AutomationsState
from ...domains.cameras.wall_state import VideoWallState
from ...domains.infra.backups_state import BackupsState
from ...domains.auth.admin_state import AuthAdminState
from ...domains.auth.state import AuthState
from ...domains.security.arming_state import ArmingState
from ..components.dialogs import photo_dialog
from ..views.device_list import check_existing_subscription_event
from ..dashboard import theme
from ...domains.notifications.state import PushState
from ..dashboard.sidebar import sidebar, mobile_bottom_nav
from ..dashboard.components.alertas import banner_alertas
from ..dashboard.components.desconocidos import banner_desconocidos
from ..dashboard.components.paleta import paleta_comandos
from ..dashboard.components.pulsacion_larga import pulsacion_larga
from ..dashboard.topbar import topbar
from ..dashboard.state import DashboardState
from ..dashboard.windows import (floating_windows_layer, equipo_windows_layer,
                                 puerta_windows_layer, aparato_windows_layer,
                                 electro_windows_layer)
from ..dashboard.views.overview import overview_view
from ..dashboard.views.settings_hub import settings_hub_view
from ..dashboard.views.cctv import cctv_view
from ..dashboard.views.alarm import alarm_view
from ..dashboard.views.groups import groups_view
from ..dashboard.views.floor_plan import floor_plan_view
from ..dashboard.views.estancias import estancias_view
from ..dashboard.views.pruebas import pruebas_view
from ..dashboard.views.video_wall import video_wall_view
from ..dashboard.views.access import access_view
from ..dashboard.views.lights import lights_view
from ..dashboard.views.ir_remotes import ir_remotes_view, ir_remote_windows_layer
from ..dashboard.views.automations import automations_view
from ..dashboard.views.equipment import equipment_view
from ..dashboard.views.logs import logs_view
from ..dashboard.views.metricas import metricas_view
from ..dashboard.views.instalador import instalador_view
from ..dashboard.views.accesorios import accesorios_view
from ..dashboard.views.movimiento import movimiento_view
from ..dashboard.views.presencia import presencia_view
from ..dashboard.views.voz import voz_view
from ..dashboard.views.system import system_view
from ..dashboard.views.usuarios import usuarios_view
from ..dashboard.views.inventario import inventario_view
from ..dashboard.views.modos import modos_view
from ..dashboard.views.retardos import retardos_view
from ..dashboard.components.armado import cuenta_atras_salida, dialogo_armado

_EFECTOS_SCRIPT = """
(function(){
    if (window.__nxEfectosInit) return;
    window.__nxEfectosInit = true;
    // Efecto «coche»: al pulsar su icono en el plano, los intermitentes
    // parpadean sobre la imagen al son del botón y los faros de cruce se quedan
    // encendidos 7 s. Los puntos (en % del plano) vienen del propio elemento
    // (efecto_puntos, por plano) en data-nx-puntos. Solo visual: la orden al
    // coche la manda el clic normal del marcador.
    var FAROS_MS = 7000, DESTELLOS = 3, ON_MS = 380, OFF_MS = 260;
    function luz(padre, x, y, estilo){
        var d = document.createElement('div');
        d.className = 'nx-efecto-luz';
        d.style.cssText = 'position:absolute;left:' + x + '%;top:' + y + '%;' +
            'transform:translate(-50%,-50%);pointer-events:none;z-index:9;' +
            'border-radius:50%;opacity:0;transition:opacity .12s ease;' +
            // «screen» suma luz a la foto en vez de pintar un círculo encima:
            // parece que la luz sale del propio coche.
            'mix-blend-mode:screen;' + estilo;
        padre.appendChild(d);
        return d;
    }
    document.addEventListener('click', function(e){
        var m = e.target.closest && e.target.closest('.nx-plan-marker[data-nx-efecto="coche"]');
        if (!m) return;
        var c = m.closest('.nx-plan-container');
        if (!c || c.classList.contains('nx-plan-editing')) return;
        var p = {};
        try { p = JSON.parse(m.getAttribute('data-nx-puntos') || '{}'); } catch (err) {}
        var padre = m.parentElement;
        padre.querySelectorAll('.nx-efecto-luz').forEach(function(x){ x.remove(); });
        var intermit = (p.intermitentes || []).map(function(q){
            return luz(padre, q[0], q[1], 'width:34px;height:34px;background:radial-gradient(circle,' +
                'rgba(255,236,190,.95) 0%,rgba(255,170,30,.75) 14%,rgba(255,140,0,.35) 38%,' +
                'rgba(255,120,0,0) 70%);filter:blur(3px);');
        });
        var faros = (p.faros || []).map(function(q){
            return luz(padre, q[0], q[1], 'width:44px;height:44px;background:radial-gradient(circle,' +
                'rgba(255,255,255,.95) 0%,rgba(236,244,255,.7) 16%,rgba(210,230,255,.3) 42%,' +
                'rgba(210,230,255,0) 72%);filter:blur(3px);transition:opacity .35s ease;');
        });
        // El haz de cruce: un abanico suave hacia delante de los faros.
        var haz = null;
        if ((p.faros || []).length === 2) {
            var fx = (p.faros[0][0] + p.faros[1][0]) / 2, fy = Math.max(p.faros[0][1], p.faros[1][1]);
            var ancho = Math.abs(p.faros[1][0] - p.faros[0][0]) * 1.9;
            haz = luz(padre, fx, fy + 6, 'width:' + ancho + '%;height:14%;border-radius:40% 40% 50% 50%;' +
                'background:radial-gradient(ellipse at 50% 0%,rgba(235,244,255,.42) 0%,' +
                'rgba(220,235,255,.16) 45%,rgba(220,235,255,0) 72%);filter:blur(6px);' +
                'transition:opacity .45s ease;');
        }
        requestAnimationFrame(function(){
            faros.concat(haz ? [haz] : []).forEach(function(f){ f.style.opacity = '1'; });
        });
        // Destellos: intermitentes y el propio botón a la vez.
        var i = 0, sombra = m.style.boxShadow;
        (function destello(){
            if (i >= DESTELLOS) { m.style.boxShadow = sombra; intermit.forEach(function(x){ x.remove(); }); return; }
            intermit.forEach(function(x){ x.style.opacity = '1'; });
            m.style.boxShadow = '0 0 22px 8px rgba(255,170,0,.85)';
            setTimeout(function(){
                intermit.forEach(function(x){ x.style.opacity = '0'; });
                m.style.boxShadow = sombra;
                i++; setTimeout(destello, OFF_MS);
            }, ON_MS);
        })();
        setTimeout(function(){
            faros.concat(haz ? [haz] : []).forEach(function(f){ f.style.opacity = '0'; });
            setTimeout(function(){ faros.concat(haz ? [haz] : []).forEach(function(f){ f.remove(); }); }, 500);
        }, FAROS_MS);
    }, false);
})();
"""


_TERMINAL_SCRIPT = """
(function(){
    if (window.__nxTerminal) return;
    // Ventana tipo terminal con el registro de noxus-panel. Es JavaScript
    // puro a propósito: mientras el servicio se reinicia no hay backend que
    // pinte nada, y así la ventana sigue ahí contando hasta que vuelve.
    var win = null, pre = null, estado = null, timer = null, caidaDesde = 0, ultimo = '';
    function guardar(v){ try { sessionStorage.setItem('nxTerminal', v ? '1' : ''); } catch (e) {} }
    function crear(){
        win = document.createElement('div');
        win.className = 'nx-terminal';
        win.style.cssText = 'position:fixed;right:12px;bottom:12px;z-index:9999;' +
            'width:min(560px,calc(100vw - 24px));height:min(46vh,420px);display:flex;' +
            'flex-direction:column;background:#05080d;border:1px solid #1f2a37;border-radius:12px;' +
            'box-shadow:0 18px 50px rgba(0,0,0,.55);overflow:hidden;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;';
        var cab = document.createElement('div');
        cab.style.cssText = 'display:flex;align-items:center;gap:8px;padding:7px 10px;background:#0b1119;' +
            'border-bottom:1px solid #1f2a37;color:#9fb3c8;font-size:12px;';
        estado = document.createElement('span');
        estado.style.cssText = 'width:8px;height:8px;border-radius:50%;background:#64748b;flex:none;';
        var titulo = document.createElement('span');
        titulo.textContent = 'noxus-panel — despliegue';
        titulo.style.flex = '1';
        var cerrar = document.createElement('button');
        cerrar.textContent = '✕';
        cerrar.title = 'Cerrar';
        cerrar.style.cssText = 'background:none;border:0;color:#9fb3c8;cursor:pointer;font-size:14px;';
        cerrar.onclick = function(){ api.toggle(false); };
        cab.appendChild(estado); cab.appendChild(titulo); cab.appendChild(cerrar);
        pre = document.createElement('pre');
        pre.style.cssText = 'margin:0;padding:10px 12px;flex:1;overflow:auto;color:#b5f5c8;' +
            'font-size:11.5px;line-height:1.45;white-space:pre-wrap;word-break:break-word;';
        win.appendChild(cab); win.appendChild(pre);
        document.body.appendChild(win);
    }
    function pintar(texto, vivo){
        var abajo = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 30;
        pre.textContent = texto;
        estado.style.background = vivo ? '#22c55e' : '#f59e0b';
        if (abajo) pre.scrollTop = pre.scrollHeight;
    }
    function preguntar(){
        fetch('/despliegue/log', {credentials: 'same-origin', cache: 'no-store'})
            .then(function(r){
                if (r.status === 401 || r.status === 403) throw new Error('permiso');
                if (!r.ok) throw new Error('caido');
                return r.text();
            })
            .then(function(t){ caidaDesde = 0; ultimo = t; pintar(t, true); })
            .catch(function(e){
                if (e.message === 'permiso') { pintar('Este aparato no tiene «Ver despliegue» activado.', false); return; }
                if (!caidaDesde) caidaDesde = Date.now();
                var s = Math.round((Date.now() - caidaDesde) / 1000);
                pintar(ultimo + '\\n⏳ Reiniciando noxus-panel… ' + s + ' s (el servicio no contesta todavía)', false);
            });
    }
    var api = {
        toggle: function(forzar){
            var abrir = (typeof forzar === 'boolean') ? forzar : !(win && win.style.display !== 'none');
            if (abrir) {
                if (!win) crear();
                win.style.display = 'flex';
                preguntar();
                if (!timer) timer = setInterval(preguntar, 2000);
            } else if (win) {
                win.style.display = 'none';
                clearInterval(timer); timer = null;
            }
            guardar(abrir);
        }
    };
    window.__nxTerminal = api;
    // Si estaba abierta antes de recargar (p. ej. tras un reinicio), vuelve.
    try { if (sessionStorage.getItem('nxTerminal')) api.toggle(true); } catch (e) {}
})();
"""


_BOCADILLOS_SCRIPT = """
(function(){
    if (window.__nxBocadillosInit) return;
    window.__nxBocadillosInit = true;
    // ── Cerrar al tocar fuera ────────────────────────────────────────────
    // Solo las ventanas marcadas con data-nx-dismiss (el mando abierto desde
    // el plano). Se hace pulsando su propia aspa en vez de con un evento
    // nuevo: así el cierre pasa por el mismo sitio que el botón de cerrar y
    // no hay dos caminos que mantener.
    document.addEventListener('pointerdown', function(e){
        if (!e.target.closest) return;
        // Los diálogos y desplegables de Radix se dibujan FUERA de la
        // ventana (en un portal al final del body): sin esta excepción,
        // abrir cualquiera de ellos contaría como "tocar fuera" y cerraría
        // el mando por debajo.
        if (e.target.closest('[role="dialog"], [role="alertdialog"], [data-radix-popper-content-wrapper]')) return;
        // Tampoco cuenta pulsar el marcador del plano que lo acaba de abrir.
        if (e.target.closest('.nx-plan-marker')) return;
        var dentro = e.target.closest('.nx-window');
        document.querySelectorAll('.nx-window[data-nx-dismiss="1"]').forEach(function(win){
            if (win !== dentro) {
                var aspa = win.querySelector('.nx-window-close');
                if (aspa) aspa.click();
            }
        });
    }, true);

    // ── Bocadillos del plano: justo encima del icono pulsado ────────────
    // Se apunta dónde está el marcador al tocarlo, y cuando aparece la
    // ventanita que abre (las de data-nx-dismiss), se coloca centrada sobre
    // él. Si no cabe encima, debajo; y siempre dentro de la pantalla.
    var ancla = null;
    document.addEventListener('pointerdown', function(e){
        var m = e.target.closest && e.target.closest('.nx-plan-marker');
        if (m) ancla = {r: m.getBoundingClientRect(), t: Date.now()};
    }, true);
    function colocar(win){
        if (!ancla || Date.now() - ancla.t > 4000 || win.dataset.nxAnclada) return;
        win.dataset.nxAnclada = '1';
        requestAnimationFrame(function(){
            var r = ancla.r, w = win.offsetWidth, h = win.offsetHeight, m = 8;
            var vw = window.innerWidth, vh = window.innerHeight;
            var left = Math.min(Math.max(r.left + r.width / 2 - w / 2, m), vw - w - m);
            var top = r.top - h - 10;
            if (top < m) top = Math.min(r.bottom + 10, vh - h - m);
            win.style.left = Math.max(left, m) + 'px';
            win.style.top = Math.max(top, m) + 'px';
            win.style.right = 'auto';
            win.style.bottom = 'auto';
            win.style.transform = 'none';
        });
    }
    new MutationObserver(function(){
        document.querySelectorAll('.nx-window[data-nx-dismiss="1"]:not([data-nx-anclada])')
            .forEach(colocar);
    }).observe(document.body, {childList: true, subtree: true});

})();
"""


_DRAG_AND_CLOCK_SCRIPT = """
(function(){
    if (window.__nxDashInit) return;
    window.__nxDashInit = true;
    window.__nxZ = 200;

    document.addEventListener('pointerdown', function(e){
        var closeBtn = e.target.closest('.nx-window-close');
        var win = e.target.closest('.nx-window');
        if (win) {
            window.__nxZ += 1;
            win.style.zIndex = window.__nxZ;
        }
        if (closeBtn) return;
        if (window.innerWidth < 768) return;
        var handle = e.target.closest('.nx-window-handle');
        if (!handle || !win) return;

        var rect = win.getBoundingClientRect();
        win.style.left = rect.left + 'px';
        win.style.top = rect.top + 'px';
        win.style.right = 'auto';
        win.style.margin = '0';

        var startX = e.clientX, startY = e.clientY;
        var baseLeft = rect.left, baseTop = rect.top;

        function onMove(ev){
            var dx = ev.clientX - startX, dy = ev.clientY - startY;
            var newLeft = Math.max(4, Math.min(baseLeft + dx, window.innerWidth - 80));
            var newTop = Math.max(4, Math.min(baseTop + dy, window.innerHeight - 40));
            win.style.left = newLeft + 'px';
            win.style.top = newTop + 'px';
        }
        function onUp(){
            document.removeEventListener('pointermove', onMove);
            document.removeEventListener('pointerup', onUp);
        }
        document.addEventListener('pointermove', onMove);
        document.addEventListener('pointerup', onUp);
    });

    function nxTickClock(){
        var el = document.getElementById('nx-clock');
        if (!el) return;
        var now = new Date();
        var d = now.toLocaleDateString('es-ES', {day:'2-digit', month:'2-digit', year:'numeric'});
        var t = now.toLocaleTimeString('es-ES');
        el.textContent = d + '   ' + t;
    }
    nxTickClock();
    setInterval(nxTickClock, 1000);
})();
"""


# La densidad "Pro" aprieta el panel entero desde un solo sitio: se marca la raiz
# con data-densidad="pro" y estas reglas hacen el resto. Es CSS y no props de
# cada componente a proposito — con props habria que tocar las treinta vistas y
# acordarse en cada componente nuevo; asi lo gana todo el panel de golpe, incluso
# lo que se escriba manana.
#
# Se aprieta el espacio y se baja un punto la tipografia, y NO se toca el tamano
# de los objetivos pulsables por debajo de lo razonable: "cabe mas" no puede
# significar "no le aciertas".
_DENSIDAD_CSS = """
[data-densidad="pro"] { font-size: 0.94rem; }
[data-densidad="pro"] .rt-Card,
[data-densidad="pro"] .rx-Stack { gap: 0.4rem; }
[data-densidad="pro"] .rt-Card { padding: 9px 11px; }
[data-densidad="pro"] .rt-BadgeRoot { padding-top: 0; padding-bottom: 0; }
"""

# JavaScript propio del panel (assets/nx.js): conserva la precarga de la
# suscripción y recupera la red Obsidiana con límites específicos para móvil.
_NX_JS = "/nx.js?v=20261002d"


def _sin_permiso() -> rx.Component:
    return rx.vstack(
        rx.icon("lock", size=28, color=theme.MUTED),
        rx.text("Esta pantalla es de configuración", size="3", weight="bold",
                color=theme.TEXT),
        rx.text(
            "Este dispositivo no tiene permiso para verla. Pídeselo a quien "
            "administre el panel.",
            size="1", color=theme.MUTED, style={"line-height": "1.5"},
        ),
        rx.button("Volver al resumen", size="2", variant="soft",
                  on_click=DashboardState.set_view("overview")),
        spacing="3", align="center", padding="48px 16px", width="100%",
    )


def _solo_camaras(vista: rx.Component) -> rx.Component:
    """El Mural y CCTV piden permiso de cámaras.

    Mirar ya es acceso: sin esto, un invitado que abre el Mural no puede tocar
    ningún botón pero ve el interior de la casa en directo, que es justo lo que
    hay que impedir. Y se comprueba aquí y no solo en el menú porque a estas
    pantallas se llega escribiendo ?vista=video_wall en la barra de direcciones.

    La comprobación se hace aquí porque ver el vídeo ya es acceso."""
    return rx.cond(AuthState.puede_camaras, vista, _sin_permiso_camaras())


def _sin_permiso_camaras() -> rx.Component:
    return rx.vstack(
        rx.icon("video-off", size=28, color=theme.MUTED),
        rx.text("No tienes acceso a las cámaras", size="3", weight="bold",
                color=theme.TEXT),
        rx.text(
            "Este dispositivo no puede ver la imagen de las cámaras de la casa. "
            "Pídeselo a quien administre el panel.",
            size="1", color=theme.MUTED, style={"line-height": "1.5"},
        ),
        rx.button("Volver al resumen", size="2", variant="soft",
                  on_click=DashboardState.set_view("overview")),
        spacing="3", align="center", padding="48px 16px", width="100%",
    )


def _solo_ajustes(vista: rx.Component) -> rx.Component:
    """Las pantallas de configuración enseñan el mapa de la casa —qué sensores
    hay, en qué pin, con qué IP— y eso no es para cualquiera. Se puede llegar a
    ellas escribiendo ?vista=... en la barra de direcciones, así que la
    comprobación va aquí y no solo en el menú.

    Es solo lo que se VE: lo que se puede tocar lo deciden los manejadores."""
    return rx.cond(AuthState.puede_ajustes, vista, _sin_permiso())


def _content() -> rx.Component:
    return rx.match(
        DashboardState.active_view,
        ("overview", overview_view()),
        ("alarm", alarm_view()),
        ("groups", groups_view()),
        ("floor_plan", floor_plan_view()),
        ("video_wall", _solo_camaras(video_wall_view())),
        ("cctv", _solo_camaras(cctv_view())),
        ("access", access_view()),
        ("lights", lights_view()),
        ("ir_remotes", ir_remotes_view()),
        ("automations", automations_view()),
        ("equipment", equipment_view()),
        ("settings_hub", _solo_ajustes(settings_hub_view())),
        ("system", _solo_ajustes(system_view())),
        ("usuarios", _solo_ajustes(usuarios_view())),
        ("inventario", _solo_ajustes(inventario_view())),
        ("modos", _solo_ajustes(modos_view())),
        ("retardos", _solo_ajustes(retardos_view())),
        ("logs", logs_view()),
        # No va envuelta en _solo_ajustes: no es configuración, es una pantalla
        # de consulta como Registros.
        ("metricas", metricas_view()),
        ("voz", _solo_ajustes(voz_view())),
        ("instalador", _solo_ajustes(instalador_view())),
        ("presencia", _solo_ajustes(presencia_view())),
        ("accesorios", _solo_ajustes(accesorios_view())),
        ("movimiento", _solo_ajustes(movimiento_view())),
        ("pruebas", _solo_ajustes(pruebas_view())),
        ("estancias", _solo_ajustes(estancias_view())),
        overview_view(),
    )


def _aviso_vincular() -> rx.Component:
    """Aviso flotante cuando este accesorio no está vinculado a las
    notificaciones.

    Hace falta porque el navegador solo concede el permiso de notificaciones
    justo después de un toque: al entrar se intenta vincular solo, pero si el
    permiso no estaba ya dado no hay forma de pedirlo sin que alguien pulse.
    Este es ese botón. Y no es solo por los avisos: sin vincular, todo lo que
    se haga desde aquí se apunta en los registros como "desconocido".

    Va por encima de la barra inferior del móvil para no taparla."""
    return rx.cond(
        PushState.falta_vincular,
        rx.hstack(
            rx.icon("bell-off", size=18, color=theme.WARNING, flex_shrink="0"),
            rx.vstack(
                rx.text("Este dispositivo no está vinculado", size="2",
                        weight="bold", color=theme.TEXT),
                rx.text("Sin vincular no recibe avisos y sus acciones salen sin nombre.",
                        size="1", color=theme.MUTED),
                spacing="0", align="start", min_width="0",
            ),
            rx.spacer(),
            rx.button("Vincular", on_click=PushState.suscribir, size="2",
                      color_scheme="orange", flex_shrink="0"),
            rx.icon("x", size=16, color=theme.MUTED, cursor="pointer",
                    on_click=PushState.descartar_aviso_vincular, flex_shrink="0"),
            align="center", spacing="3",
            class_name="nx-floating-notice nx-link-notice",
        ),
    )


def _comprobando() -> rx.Component:
    """Lo que se ve el instante que tarda en resolverse quién es este navegador.

    Existe para no tener que elegir entre dos parpadeos malos: enseñar el panel
    a quien puede no tener acceso, o enseñar «sin acceso» a quien sí lo tiene.
    Desde que la entrada va en un solo evento (DashboardState.entrar) dura lo
    que tarda ese viaje, y al terminar el panel sale entero y ya se puede tocar."""
    return rx.el.div(
        rx.el.div(
            rx.el.img(src="/noxus-marca.svg", alt="", width="64", height="64"),
            rx.el.div("Comprobando el acceso…", class_name="nx-boot-texto"),
            class_name="nx-boot-marca",
        ),
        class_name="nx-boot",
        role="status",
    )


def _registro_invitado() -> rx.Component:
    """El alta de quien llega con un enlace de invitacion.

    Se le pide el nombre antes de dejarle pasar, y no es burocracia: ese nombre
    es el que queda escrito en el registro junto a cada cosa que haga. Sin el,
    todo lo que toque un invitado se apunta como «Invitado», que con dos
    invitados en casa no distingue a nadie.

    Darse un nombre NO hace el acceso permanente: la caducidad la puso quien
    creo la invitacion, y cuando pasa la hora el acceso se cae solo (ver
    auth/store.rol_de)."""
    return rx.center(
        rx.vstack(
            rx.icon("user-plus", size=32, color=theme.ACCENT),
            rx.text("Te han invitado", size="4", weight="bold", color=theme.TEXT),
            rx.text(
                "Escribe tu nombre para entrar. Tu acceso dura lo que dure la "
                "invitacion y se retira solo al terminar.",
                size="2", color=theme.MUTED, text_align="center",
                max_width="380px",
            ),
            rx.input(
                value=AuthState.nombre_invitado,
                on_change=AuthState.set_nombre_invitado,
                placeholder="Tu nombre",
                size="3", width="100%", max_length=30,
                # Enter entra: es un formulario de un solo campo.
                on_key_down=lambda k: rx.cond(
                    k == "Enter", AuthState.registrarse, rx.noop()),
            ),
            rx.button("Entrar", on_click=AuthState.registrarse, size="3",
                      width="100%"),
            spacing="3", align="center", width="min(360px, 90vw)",
        ),
        height="100vh", width="100%", padding="24px",
    )


def _sin_acceso() -> rx.Component:
    """La puerta cerrada. Un dispositivo sin permiso de entrada NO ve el panel:
    ni el plano, ni el estado de la alarma, ni los nombres de los equipos.

    Se dice qué hacer y nada más. Sin detalles del sistema: a quien está
    probando a ver qué hay tampoco hace falta contarle nada."""
    return rx.center(
        rx.vstack(
            rx.icon("shield-off", size=34, color=theme.MUTED),
            rx.text("Este dispositivo no tiene acceso", size="4", weight="bold",
                    color=theme.TEXT),
            rx.text("Di quién eres y por qué quieres entrar: le llegará el "
                    "aviso a un administrador para que decida.",
                    size="2", color=theme.MUTED, text_align="center",
                    max_width="420px"),
            # Nombre y mensaje son lo que ve el administrador en Ajustes y en
            # el propio aviso que le llega — sin esto no tiene forma de saber
            # cuál de la lista es este accesorio ni por qué está pidiendo
            # entrar. El nombre precarga el que ya tuviera (de la suscripción
            # push, si la tiene); si no tiene ninguno, no se inventa nada.
            rx.vstack(
                rx.input(
                    value=AuthState.nombre_acceso,
                    on_change=AuthState.set_nombre_acceso,
                    placeholder="Tu nombre",
                    size="3", width="100%", max_length=40,
                ),
                rx.input(
                    value=AuthState.nota_acceso,
                    on_change=AuthState.set_nota_acceso,
                    placeholder="Por qué quieres entrar",
                    size="3", width="100%", max_length=200,
                    on_key_down=lambda k: rx.cond(
                        k == "Enter", AuthState.enviar_nota_acceso, rx.noop()),
                ),
                rx.button("Pedir acceso", on_click=AuthState.enviar_nota_acceso,
                          size="2", width="100%", variant="soft"),
                spacing="2", width="min(360px, 90vw)", padding_top="6px",
            ),
            spacing="3", align="center",
        ),
        height="100vh", width="100%", padding="24px",
    )


def _panel() -> rx.Component:
    # La carcasa es un contenedor FIJO a toda la pantalla (.nx-shell en
    # assets/nx.css) y lo único que se desplaza es el contenido (.nx-scroll).
    # Antes se desplazaba la página entera y la barra de arriba era sticky: en
    # el iPhone, al tirar hacia abajo estando arriba del todo, el rebote
    # elástico se la llevaba hasta media pantalla. Ahora la barra está fuera de
    # lo que rebota y no se mueve.
    return rx.fragment(
        rx.script(_DRAG_AND_CLOCK_SCRIPT),
        rx.script(_BOCADILLOS_SCRIPT),
        rx.script(_TERMINAL_SCRIPT),
        rx.script(_EFECTOS_SCRIPT),
        rx.el.div(
            sidebar(),
            rx.el.div(
                topbar(),
                rx.el.main(
                    rx.el.div(
                        _content(),
                        # key: al cambiar de pestaña React monta la vista de
                        # nuevo y entra con un fundido cortísimo (nx.css): lo
                        # justo para que el cambio se note sin hacer esperar.
                        key=DashboardState.active_view,
                        class_name="nx-stage",
                        # nx.js decide por vista dónde vibra al pulsar.
                        custom_attrs={"data-vista": DashboardState.active_view},
                    ),
                    class_name="nx-scroll",
                ),
                class_name="nx-main",
            ),
            class_name="nx-shell",
        ),
        # Una sola pila evita que los avisos propios se tapen entre sí. Está al
        # nivel de la página para verse se pulse el armado desde donde se pulse.
        rx.el.aside(
            banner_alertas(),
            banner_desconocidos(),
            dialogo_armado(),
            cuenta_atras_salida(),
            _aviso_vincular(),
            class_name="nx-floating-notices",
            aria_label="Avisos del panel",
        ),
        mobile_bottom_nav(),
        photo_dialog(
            InfraState.dialog_foto_abierto,
            InfraState.toggle_dialog,
            InfraState.last_rpi_photo,
        ),
        floating_windows_layer(),
        ir_remote_windows_layer(),
        equipo_windows_layer(),
        puerta_windows_layer(),
        aparato_windows_layer(),
        electro_windows_layer(),
        paleta_comandos(),
        pulsacion_larga(),
    )


# Lo que hay que hacer al ENTRAR en el panel. DashboardState.entrar consume
# esta lista desde el servidor y es el unico `on_load` de la pagina (ver
# noxuscmmd.py). Sigue siendo `on_load`, y no `on_mount`, porque Reflex lo
# reenvia en CADA (re)conexion del websocket: una pestana que vuelve de segundo
# plano —el movil, sin ir mas lejos— recupera sus bucles de refresco sola. Con
# on_mount solo corrian al montar el componente: tras una reconexion la pantalla
# se quedaba viva pero sorda y habia que cerrar la aplicacion y abrirla.
#
# Que se repitan no duplica nada: cada bucle de sesion releva al anterior en
# vez de sumarse a el (ver core/sesiones.py), y los de proceso siguen con su
# propio flag _STARTED.
EVENTOS_DE_IDENTIFICACION = [
    # El PRIMERO de todos: hasta que no se sabe qué dispositivo es
    # este, no se sabe qué puede hacer ni qué se le debe enseñar.
    AuthState.identificar,
    AuthState.canjear_de_la_url,
    # Vigila en vivo si a este accesorio le cambian el acceso: quitarle el
    # permiso tiene que echarlo en el momento, no al recargar.
    AuthState.vigilar_acceso,
]

EVENTOS_DE_ENTRADA = [
    *EVENTOS_DE_IDENTIFICACION,
    # Para que el aviso de «dispositivo desconocido» tenga datos en
    # cualquier vista, no solo dentro de Ajustes → Dispositivos.
    AuthAdminState.on_load,
    SecurityState.on_load,
    InfraState.on_load,
    RegistryState.on_load,
    NodesState.on_load,
    ElectroState.on_load,
    GroupsState.on_load,
    HostActionsState.on_load,
    AccessControlState.on_load,
    LogsState.on_load,
    AlertasState.on_load,
    AutomationsState.on_load,
    VideoWallState.on_load,
    BackupsState.on_load,
    check_existing_subscription_event(),
    # El último a propósito: abre la vista que pida ?vista= en la URL y
    # tiene que poder pisar el "overview" de partida. Es lo que hace que
    # los atajos del icono de la aplicación (manifest.json → shortcuts)
    # lleguen a donde dicen.
    DashboardState.aplicar_url,
    # Engancharse a una cuenta atras de salida que ya estuviera corriendo.
    ArmingState.recuperar_cuenta,
]


def dashboard_page() -> rx.Component:
    return rx.box(
        # LA PUERTA. Sin permiso de entrada no se monta el panel: no es que se
        # esconda con CSS, es que no se pinta. Lo que no está en la página no se
        # puede sacar con las herramientas del navegador.
        #
        # Ojo con lo que esto NO es: seguridad de verdad son las comprobaciones
        # de dentro de cada manejador (auth/permisos.py), porque los eventos
        # viajan por el websocket y se pueden invocar sin pasar por ningún botón.
        # Esto es para que quien no tiene acceso no vea el estado de la casa.
        rx.el.style(_DENSIDAD_CSS),
        rx.script(src=_NX_JS),
        # El color de acento de ESTE accesorio. rx.theme envuelve el panel, asi que
        # botones, insignias, interruptores y campos se pintan con el color que
        # cada uno haya elegido en su ficha (ver auth/store.preferencias).
        #
        # Lo que NO cambia son los colores propios del panel (theme.ACCENT y
        # compania), que estan escritos como literales en los componentes: el
        # acento manda en el cromo de Radix, no en el rojo de una alarma ni en el
        # verde de un sensor cerrado, que tienen que significar siempre lo mismo.
        rx.theme(
            rx.cond(
                AuthState.comprobando,
                _comprobando(),
                # El alta del invitado va ANTES de la puerta cerrada: quien llega
            # con un enlace todavia no tiene acceso, asi que sin esto veria
            # «no tienes acceso» con la invitacion en la mano.
            rx.cond(
                AuthState.registrando,
                _registro_invitado(),
                rx.cond(AuthState.tiene_acceso, _panel(), _sin_acceso()),
            ),
            ),
            appearance="dark",
            accent_color=AuthState.acento,
        ),
        min_height="100vh",
        width="100%",
        background="transparent",
        # data-nx-armado tiñe el ambiente entero (aurora, filo de la barra, titulares) de rojo con la
        # casa armada: se ve de un vistazo desde la otra punta de la habitacion (assets/nx.css).
        custom_attrs={"data-densidad": AuthState.densidad,
                      "data-nx-armado": rx.cond(
                          AuthState.tiene_acceso,
                          SecurityState.sistema_armado,
                          False,
                      )},
    )
