import reflex as rx
import os
from ..state import State
from ..components.status_row import status_row

VAPID_PUBLIC = os.getenv("VAPID_PUBLIC_KEY")

def alarma_control_view():
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.icon(
                    rx.cond(State.sistema_armado, "shield-check", "shield-off"),
                    color=rx.cond(State.sistema_armado, "#ff4d4d", "#64748b")
                ),
                rx.heading("SEGURIDAD", size="3", letter_spacing="0.05em"),
                rx.spacer(),
                rx.badge(
                    rx.cond(State.puerta_abierta, "PUERTA ABIERTA", "CERRADA"),
                    color_scheme=rx.cond(State.puerta_abierta, "red", "green"),
                    variant="surface"
                ),
                # ── Botón de alerta (triángulo naranja) ──
                rx.button(
                    rx.icon("triangle-alert", size=18, color="#f97316"),
                    on_click=rx.call_script(
                        f"""
                        (async function() {{
                            // 1. Obtener la suscripción activa del service worker
                            let sub = null;
                            try {{
                                const reg = await navigator.serviceWorker.ready;
                                const pushSub = await reg.pushManager.getSubscription();
                                if (pushSub) {{
                                    sub = {{
                                        endpoint: pushSub.endpoint,
                                        keys: {{
                                            p256dh: btoa(String.fromCharCode.apply(null, new Uint8Array(pushSub.getKey('p256dh')))),
                                            auth: btoa(String.fromCharCode.apply(null, new Uint8Array(pushSub.getKey('auth')))),
                                        }}
                                    }};
                                }}
                            }} catch(e) {{
                                console.warn('No se pudo obtener la suscripción:', e);
                            }}
                            
                            // 2. Llamar al método de Reflex pasando la suscripción (o null)
                            const subscription = sub ? JSON.stringify(sub) : 'null';
                            // Llamar al evento de Reflex
                            // Asumimos que State.lanzar_alerta_global espera un argumento
                            // Usamos el mecanismo de eventos de Reflex
                            return subscription;
                        }})();
                        """,
                        callback=State.lanzar_alerta_global_con_subscripcion  # <--- Nuevo método
                    ),
                    variant="ghost",
                    size="1",
                    title="Enviar alerta a todos",
                ),
                # ── Botón de suscripción push (campana) ──
                rx.button(
                    rx.icon("bell", size=18),
                    on_click=rx.call_script(
                        f"""
                        (async function() {{
                            try {{
                                let nombre = window.prompt("Nombre para este dispositivo (ej: Mi iPhone, PC Oficina):", "");
                                if (nombre === null) {{
                                    return "USER_CANCEL";
                                }}
                                nombre = nombre.trim();
                                if (nombre === "") {{
                                    alert("El nombre no puede estar vacío. Cancelado.");
                                    return "USER_CANCEL";
                                }}
                                
                                let reg;
                                for (let intentos = 0; intentos < 3; intentos++) {{
                                    try {{
                                        reg = await navigator.serviceWorker.register('/sw.js');
                                        await navigator.serviceWorker.ready;
                                        break;
                                    }} catch (e) {{
                                        console.warn("Intento " + (intentos+1) + " fallido", e);
                                        await new Promise(r => setTimeout(r, 500));
                                    }}
                                }}
                                if (!reg) throw new Error("No se pudo registrar el Service Worker");
                                
                                const publicKey = '{VAPID_PUBLIC}';
                                const toUint8 = (b) => {{
                                    const pad = '='.repeat((4 - b.length % 4) % 4);
                                    const b64 = (b + pad).replace(/-/g, '+').replace(/_/g, '/');
                                    const raw = window.atob(b64);
                                    const out = new Uint8Array(raw.length);
                                    for (let i = 0; i < raw.length; ++i) out[i] = raw.charCodeAt(i);
                                    return out;
                                }};
                                
                                const perm = await Notification.requestPermission();
                                if (perm !== 'granted') return "PERMISO_DENEGADO";
                                
                                const sub = await reg.pushManager.subscribe({{
                                    userVisibleOnly: true,
                                    applicationServerKey: toUint8(publicKey)
                                }});
                                
                                return JSON.stringify({{
                                    subscription: sub,
                                    nombre: nombre
                                }});
                            }} catch (err) {{
                                if (err.name === "NotAllowedError") return "PERMISO_BLOQUEADO";
                                return "ERROR_" + err.message;
                            }}
                        }})();
                        """,
                        callback=State.guardar_subscripcion
                    ),
                    variant="ghost",
                    size="1",
                    title="Suscribirse a notificaciones push",
                ),
                width="100%",
                align="center",
            ),
            rx.divider(opacity="0.1"),
            rx.hstack(
                rx.text("Monitoreo de Intrusión", size="2", color="#94a3b8"),
                rx.spacer(),
                rx.button(
                    rx.cond(State.sistema_armado, "DESARMAR", "ARMAR"),
                    on_click=State.conmutar_alarma,
                    color_scheme=rx.cond(State.sistema_armado, "red", "green"),
                    variant=rx.cond(State.sistema_armado, "solid", "surface"),
                    size="2",
                ),
                width="100%",
                align="center",
            ),
            spacing="3",
        ),
        width="100%",
        background="rgba(255, 255, 255, 0.03)",
        backdrop_filter="blur(10px)",
        border=rx.cond(State.sistema_armado, "1px solid rgba(255, 77, 77, 0.3)", "1px solid rgba(255, 255, 255, 0.1)"),
        padding="4",
    )

def cctv_view():
    """Panel CCTV con ambas cámaras (iconos pequeños y etiquetas encima)"""
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.icon("video", size=20, color="#818cf8"),
                rx.heading("CCTV", size="3", letter_spacing="0.05em"),
                rx.spacer(),
                # ── Cámara fija ──
                rx.vstack(
                    rx.text("H.Ppal", size="1", color="gray"),
                    rx.icon("cctv", size=20, color="#38bdf8"),
                    on_click=State.toggle_fija_stream,
                    cursor="pointer",
                    align="center",
                    spacing="0",
                ),
                # ── PTZ ──
                rx.vstack(
                    rx.text("PTZ", size="1", color="gray"),
                    rx.icon("rotate-cw", size=20, color="#a78bfa"),
                    on_click=State.toggle_ptz_stream,
                    cursor="pointer",
                    align="center",
                    spacing="0",
                ),
                width="100%",
                align="center",
            ),
            spacing="3",
        ),
        width="100%",
        background="rgba(255, 255, 255, 0.03)",
        backdrop_filter="blur(10px)",
        border="1px solid rgba(255, 255, 255, 0.1)",
        padding="4",
    )

def device_list_view():
    return rx.vstack(
        alarma_control_view(),
        cctv_view(),
        rx.hstack(
            rx.icon("activity", size=20, color="#38bdf8"),
            rx.heading("INFRAESTRUCTURA", size="3", letter_spacing="0.05em"),
            rx.spacer(),
            # La campana ya está en seguridad, así que quitamos este spacer
            width="100%",
            align="center",
            px="2",
            pt="2",
        ),
        rx.card(
            rx.vstack(
                status_row("Servidor", os.getenv("IP_SERVER", "0.0.0.0"), State.server_online, "network"),
                status_row("PC", os.getenv("IP_PC", "0.0.0.0"), State.pc_online, "monitor", on_rdp=State.rdp_pc),
                status_row("Portátil", os.getenv("IP_PORTATIL", "0.0.0.0"), State.portatil_online, "laptop", on_rdp=State.rdp_portatil),
                status_row("Raspberry", os.getenv("IP_RASPBERRY", "0.0.0.0"), State.raspberry_online, "grape", on_rdp=State.rdp_raspberry),
                status_row("Pi Zero", os.getenv("IP_PI_ZERO", "0.0.0.0"), State.pi_zero_online, "microchip"),
                status_row("iPhone", os.getenv("IP_IPHONE", "0.0.0.0"), State.iphone_online, "smartphone"),
                status_row("Tablet", os.getenv("IP_TABLET", "0.0.0.0"), State.tablet_online, "tablet"),
                spacing="2",
                width="100%",
            ),
            width="100%",
            background="rgba(255, 255, 255, 0.03)",
            backdrop_filter="blur(10px)",
            border="1px solid rgba(255, 255, 255, 0.1)",
            padding="4",
        ),
        width="100%",
        spacing="3",
    )