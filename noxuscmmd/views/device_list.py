import reflex as rx, os
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

def device_list_view():
    return rx.vstack(
        alarma_control_view(),
        rx.hstack(
            rx.icon("activity", size=20, color="#38bdf8"),
            rx.heading("INFRAESTRUCTURA", size="3", letter_spacing="0.05em"),
            rx.spacer(),
            rx.button(
                rx.icon("bell", size=20),
                on_click=rx.call_script(
                    f"""
                    (async function() {{
                        try {{
                            // 1. Pedir nombre personalizado - SI ES CANCELAR, SALIR
                            let nombre = window.prompt("Nombre para este dispositivo (ej: Mi iPhone, PC Oficina):", "");
                            if (nombre === null) {{
                                return "USER_CANCEL";
                            }}
                            nombre = nombre.trim();
                            if (nombre === "") {{
                                alert("El nombre no puede estar vacío. Cancelado.");
                                return "USER_CANCEL";
                            }}
                            
                            // 2. Registrar Service Worker (con reintento)
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
                            
                            // 3. Suscribir a push
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
                            
                            // 4. Devolver suscripción + nombre
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
                size="3",
                cursor="pointer",
            ),
            align="center",
            width="100%",
            px="2",
            pt="2",
        ),
        rx.card(
            rx.vstack(
                status_row("Raspberry", "100.76.90.7", State.raspberry_online, "server", on_rdp=State.rdp_raspberry),
                status_row("iPhone", "100.76.51.34", State.iphone_online, "smartphone"),
                status_row("PC", "100.113.223.72", State.pc_online, "monitor", on_rdp=State.rdp_pc),
                status_row("Portátil", "100.77.201.80", State.portatil_online, "laptop", on_rdp=State.rdp_portatil),
                status_row("Pi Zero", "100.97.93.109", State.pi_zero_online, "microchip"),
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