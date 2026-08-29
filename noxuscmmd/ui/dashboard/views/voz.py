"""
Pantalla «Comandos de voz» (Ajustes): frases atadas a acciones, y la clave que
necesita el atajo del móvil.

Dos bloques y en este orden: primero las frases, que es lo que se viene a hacer
aquí, y debajo la clave, que se saca una vez y no se vuelve a tocar.
"""
import reflex as rx

from ....domains.devices.voz_state import DIAS_CLAVE, VozState
from .. import theme
from ..state import DashboardState
from ..components.actions_menu import confirm_delete_dialog
from ..components.catalog_picker import catalog_picker
from ..components.form_dialog import select_content


_CATEGORIAS_ALEXA = (
    ("SWITCH", "Interruptor"), ("LIGHT", "Luz"), ("TV", "Televisión"),
    ("FAN", "Ventilador"), ("COMPUTER", "Ordenador"),
    ("SMARTPLUG", "Enchufe"), ("OTHER", "Otro"),
)


def _fila(g: rx.Var) -> rx.Component:
    return rx.hstack(
        rx.icon("mic", size=15, color=theme.ACCENT, flex_shrink="0"),
        rx.vstack(
            rx.text('"' + g["frase"].to(str) + '"', size="2", weight="bold",
                    color=theme.TEXT),
            rx.text(g["etiqueta"], size="1", color=theme.MUTED),
            spacing="0", align="start", min_width="0",
        ),
        rx.spacer(),
        # Cambiar la acción sin borrar la frase: lo normal es querer que «buenas
        # noches» haga otra cosa, no dejar de decir «buenas noches».
        rx.select.root(
            rx.select.trigger(placeholder="Cambiar acción", variant="surface"),
            select_content(
                rx.foreach(
                    VozState.catalogo,
                    lambda c: rx.select.item(c["etiqueta"], value=c["id"]),
                ),
            ),
            value=g["comando"],
            on_change=lambda v: VozState.cambiar_accion(g["id"], v),
            size="1",
        ),
        confirm_delete_dialog(
            rx.icon_button(rx.icon("trash-2", size=13), size="1",
                           variant="surface", color_scheme="red",
                           title="Quitar la frase"),
            title="¿Quitar esta frase?", tipo="frase", nombre=g["frase"],
            on_confirm=VozState.borrar(g["id"]),
        ),
        align="center", spacing="3", width="100%", wrap="wrap",
        padding="9px 11px", border_radius="10px",
        background=theme.BG_CARD, border=f"1px solid {theme.BORDER}",
    )


def _fila_atajo(c: rx.Var) -> rx.Component:
    return rx.hstack(
        rx.vstack(
            rx.text(c["etiqueta"], size="1", color=theme.TEXT),
            rx.text(c["id"], size="1", color=theme.MUTED,
                    style={"font-family": theme.FONT_MONO}),
            spacing="0", align="start", min_width="0",
        ),
        rx.spacer(),
        rx.button(rx.icon("copy", size=13), "Copiar id", size="1",
                  variant="surface", flex_shrink="0",
                  on_click=rx.set_clipboard(c["id"])),
        align="center", spacing="2", width="100%", wrap="wrap",
        padding="7px 4px", border_bottom=f"1px solid {theme.BORDER}",
    )


def _paso(n: int, *contenido) -> rx.Component:
    return rx.hstack(
        rx.box(
            rx.text(str(n), size="1", weight="bold", color=theme.ACCENT),
            min_width="21px", height="21px", border_radius="6px",
            background=theme.BG_WINDOW, align_items="center", justify_content="center",
            display="flex", flex_shrink="0",
        ),
        rx.text(*contenido, size="1", color=theme.TEXT, style={"line-height": "1.6"}),
        spacing="2", align="start", width="100%",
        padding="8px 0", border_bottom=f"1px solid {theme.BORDER}",
    )


def _aviso_mini(*contenido) -> rx.Component:
    return rx.box(
        rx.text(*contenido, size="1", color=theme.WARNING, style={"line-height": "1.5"}),
        padding="8px 10px", border_radius="8px", background=theme.BG_WINDOW,
        border=f"1px solid {theme.WARNING}", margin="6px 0", width="100%",
    )


def _tab_plantilla() -> rx.Component:
    return rx.vstack(
        rx.text(
            "El primero, «enciende el ordenador», completo. Los demás salen de "
            "duplicar este y cambiar solo dos datos — ver pestaña Comandos.",
            size="1", color=theme.MUTED,
        ),
        _paso(1, "Abre ", rx.text.strong("Atajos"), " → ",
              rx.text.strong("Mis atajos"), " → toca ", rx.text.strong("+"),
              " para crear uno nuevo."),
        _paso(2, "Añadir acción → busca «contenido de url» → ",
              rx.text.strong("Obtener contenido de URL"), "."),
        _paso(3, "URL: ", rx.code("https://panel.noxuscmmd.uk/api/voz", size="1"),
              rx.button(rx.icon("copy", size=11), size="1", variant="ghost",
                        margin_left="4px",
                        on_click=rx.set_clipboard("https://panel.noxuscmmd.uk/api/voz"))),
        _paso(4, "Despliega la acción (▾) → ", rx.text.strong("Método"), ": ",
              rx.code("POST", size="1"), "."),
        _paso(5, rx.text.strong("Cabeceras"), " → añadir. Nombre: ",
              rx.code("X-Noxus-Clave", size="1"), " · Valor: tu clave (arriba en "
              "esta misma pantalla)."),
        _aviso_mini(rx.text.strong("Ojo con el orden — "), "nombre a la "
                    "izquierda, valor a la derecha. Al revés es el fallo más "
                    "típico."),
        _paso(6, rx.text.strong("Cuerpo de la solicitud"), " → tipo ",
              rx.code("JSON", size="1"), " → añadir campo. Nombre: ",
              rx.code("comando", size="1"), " · Valor: ",
              rx.code("wol:pc", size="1"), "."),
        _paso(7, "Añadir acción → «diccionario» → ",
              rx.text.strong("Obtener valor de diccionario"), ". Clave: ",
              rx.code("mensaje", size="1"), "."),
        _paso(8, "Añadir acción → «hablar» → ", rx.text.strong("Hablar texto"),
              " → elige el valor que acabas de sacar del diccionario."),
        _paso(9, "Nombra el atajo (arriba) como quieras — es solo para "
              "identificarlo, no lo vas a decir."),
        _paso(10, "ⓘ (o ···) → ", rx.text.strong("Añadir a Siri"), " → graba, "
              "sin nombre delante: «enciende el ordenador»."),
        _paso(11, rx.text.strong("Prueba: "), "«Oye Siri, enciende el "
              "ordenador» — directo, en una sola frase."),
        spacing="1", width="100%",
    )


def _tab_comandos() -> rx.Component:
    return rx.vstack(
        rx.text(
            "Duplica el atajo de arriba y cambia solo: el valor de «comando» "
            "en el cuerpo, y la frase grabada en Siri. La lista se actualiza "
            "sola según añadas cosas al panel.",
            size="1", color=theme.MUTED,
        ),
        rx.input(
            rx.input.slot(rx.icon("search", size=14)),
            placeholder="Buscar: ventilador, ordenador, netflix…",
            value=VozState.atajo_busqueda,
            on_change=VozState.set_atajo_busqueda,
            size="2", width="100%",
        ),
        rx.scroll_area(
            rx.vstack(
                rx.foreach(VozState.catalogo_filtrado, _fila_atajo),
                spacing="0", width="100%",
            ),
            style={"height": "260px"}, type="auto",
        ),
        spacing="2", width="100%",
    )


def _tab_avisos() -> rx.Component:
    return rx.vstack(
        _aviso_mini(rx.text.strong("La tele solo tiene un botón para "
                    "encender y apagar — "), "si dices «apaga la tele» y ya "
                    "estaba apagada, la enciende (y al revés). Igual que le "
                    "pasa a Alexa con este mismo mando."),
        _aviso_mini(rx.text.strong("Netflix/Prime/Disney+/Rakuten pueden "
                    "tardar ~8 s de más "), "la primera vez que la tele está "
                    "apagada: el panel la enciende sola antes de abrir la app."),
        _aviso_mini(rx.text.strong("Un archivo .shortcut descargado no se "
                    "puede importar — "), "iOS exige que venga firmado por "
                    "Apple; por eso cada atajo se monta a mano, aunque sea "
                    "rápido con «Duplicar»."),
        spacing="2", width="100%",
    )


def _generador_atajos() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.icon_button(rx.icon("circle-help", size=14), size="1",
                           variant="soft", title="Cómo montar un atajo de Siri"),
        ),
        rx.dialog.content(
            rx.dialog.title(
                rx.hstack(rx.icon("mic", size=18, color=theme.ACCENT),
                          "Atajos de Siri para la casa", spacing="2", align="center"),
            ),
            rx.box(
                rx.tabs.root(
                    rx.tabs.list(
                        rx.tabs.trigger("Cómo montarlo", value="plantilla"),
                        rx.tabs.trigger("Comandos", value="comandos"),
                        rx.tabs.trigger("Avisos", value="avisos"),
                    ),
                    rx.box(rx.tabs.content(_tab_plantilla(), value="plantilla"),
                           padding_top="12px"),
                    rx.box(rx.tabs.content(_tab_comandos(), value="comandos"),
                           padding_top="12px"),
                    rx.box(rx.tabs.content(_tab_avisos(), value="avisos"),
                           padding_top="12px"),
                    default_value="plantilla", width="100%",
                ),
                max_height="70vh", overflow_y="auto", width="100%",
                padding_right="4px",
            ),
            style={"max-width": "540px"},
        ),
    )


def _clave() -> rx.Component:
    return rx.vstack(
        rx.text("CLAVE PARA EL ATAJO", size="1", color=theme.MUTED,
                letter_spacing="0.08em", weight="bold"),
        rx.text(
            f"La necesita un Atajo de Siri o un cliente de la API local. Vale {DIAS_CLAVE} "
            "días y hereda los permisos de ESTE dispositivo: la clave de un "
            "invitado enciende luces y no abre la puerta.",
            size="1", color=theme.MUTED,
        ),
        # Las claves anteriores eran, literalmente, una sesión del panel: quien
        # la viera entraba como este dispositivo. Ya no, pero las viejas siguen
        # ahí fuera y hay que rehacerlas a mano — nadie se entera si no se dice.
        rx.text(
            "Si generaste una clave antes de hoy, vuelve a generarla: las de "
            "antes servían además para entrar al panel, y esta ya no.",
            size="1", color=theme.WARNING,
        ),
        rx.cond(
            VozState.hay_clave,
            rx.vstack(
                rx.box(
                    rx.text(VozState.clave, size="1",
                            style={"font-family": theme.FONT_MONO,
                                   "word-break": "break-all"},
                            color=theme.TEXT),
                    padding="10px", border_radius="8px", width="100%",
                    background=theme.BG_WINDOW,
                    border=f"1px solid {theme.BORDER_STRONG}",
                ),
                rx.hstack(
                    rx.button(rx.icon("copy", size=14), "Copiar",
                              on_click=rx.set_clipboard(VozState.clave),
                              size="2"),
                    rx.button("Ocultar", on_click=VozState.olvidar_clave,
                              size="2", variant="surface"),
                    spacing="2",
                ),
                rx.text(
                    "Cópiala ahora: no se guarda en ningún sitio y al ocultarla "
                    "no se puede volver a ver. Si la pierdes, generas otra.",
                    size="1", color=theme.WARNING,
                ),
                spacing="2", width="100%",
            ),
            rx.button(rx.icon("key-round", size=14), "Generar una clave",
                      on_click=VozState.generar_clave, size="2",
                      variant="surface"),
        ),
        rx.divider(border_color=theme.BORDER),
        rx.text("CÓMO SE MONTA EL ATAJO", size="1", color=theme.MUTED,
                letter_spacing="0.08em", weight="bold"),
        # El ejemplo va en texto plano y no en una captura: un atajo se monta
        # una vez y lo que hace falta es poder copiar los cuatro datos.
        rx.box(
            rx.text(
                "En Atajos (iPhone): «Obtener contenido de una URL»\n"
                "  URL:      https://panel.noxuscmmd.uk/api/voz\n"
                "  Método:   POST\n"
                "  Cabecera: X-Noxus-Clave = la clave de arriba\n"
                "  Cuerpo (JSON):  texto = [Texto dictado]\n\n"
                "Luego «Obtener valor de mensaje del diccionario» y «Decir»,\n"
                "para que Siri lea la respuesta en voz alta.",
                size="1", color=theme.MUTED,
                style={"font-family": theme.FONT_MONO, "white-space": "pre-wrap",
                       "line-height": "1.6"},
            ),
            padding="10px", border_radius="8px", width="100%",
            background=theme.BG_CARD, border=f"1px solid {theme.BORDER}",
        ),
        rx.hstack(
            rx.text("¿No quieres montarlo campo a campo?", size="1",
                    color=theme.MUTED),
            _generador_atajos(),
            spacing="2", align="center",
        ),
        spacing="2", width="100%",
    )


def _alexa_cloud() -> rx.Component:
    return rx.vstack(
        rx.text("ALEXA CLOUD", size="1", color=theme.MUTED,
                letter_spacing="0.08em", weight="bold"),
        rx.text(
            "Configuración técnica del enlace ya realizado. Las credenciales no "
            "se muestran ni se guardan en el navegador.",
            size="1", color=theme.MUTED,
        ),
        rx.cond(
            VozState.alexa_eventos_configurados,
            rx.text("Eventos de Alexa configurados.", size="1", color=theme.SUCCESS),
            rx.vstack(
                rx.input(placeholder="Alexa Client ID", value=VozState.alexa_event_client_id,
                         on_change=VozState.set_alexa_event_client_id, size="2", width="100%"),
                rx.input(placeholder="Alexa Client Secret", type="password",
                         value=VozState.alexa_event_client_secret,
                         on_change=VozState.set_alexa_event_client_secret,
                         size="2", width="100%"),
                rx.button("Guardar credenciales de Alexa", size="2",
                          on_click=VozState.guardar_alexa_eventos),
                spacing="2", width="100%",
            ),
        ),
        rx.divider(border_color=theme.BORDER),
        rx.text("ENLACE INICIAL", size="1", color=theme.MUTED,
                letter_spacing="0.08em", weight="bold"),
        rx.text(
            "Solo se usa si Alexa te lo pide al habilitar Noxus por primera vez. "
            "Caduca en cinco minutos y deja de servir al usarlo.",
            size="1", color=theme.MUTED,
        ),
        rx.cond(
            VozState.hay_codigo_alexa,
            rx.hstack(
                rx.box(rx.text(VozState.alexa_codigo_enlace, size="2", weight="bold",
                               style={"font-family": theme.FONT_MONO}),
                       padding="8px 10px", border_radius="8px", background=theme.BG_WINDOW,
                       border=f"1px solid {theme.BORDER_STRONG}"),
                rx.button(rx.icon("copy", size=14), "Copiar", size="2",
                          on_click=rx.set_clipboard(VozState.alexa_codigo_enlace)),
                rx.button("Ocultar", size="2", variant="surface",
                          on_click=VozState.ocultar_codigo_alexa),
                spacing="2", wrap="wrap",
            ),
            rx.button("Generar código de enlace", size="2", variant="surface",
                      on_click=VozState.generar_codigo_alexa),
        ),
        rx.hstack(
            rx.cond(VozState.alexa_ultimo_estado != "",
                    rx.text(VozState.alexa_ultimo_estado, size="1", color=theme.MUTED),
                    rx.text("Aún no hay ningún intento de enlace registrado.", size="1",
                            color=theme.MUTED)),
            rx.button("Consultar estado", size="1", variant="surface",
                      on_click=VozState.refrescar_alexa_cloud),
            spacing="2", width="100%", align="center", wrap="wrap",
        ),
        spacing="2", width="100%",
    )


def _selector_accion(frase, etiqueta, slot: str,
                     frase_alternativa=None) -> rx.Component:
    titulo = (
        rx.text("Al decir «", frase, "» o «", frase_alternativa,
                "», Noxus ejecutará:", size="1", color=theme.MUTED,
                weight="bold")
        if frase_alternativa is not None else
        rx.text("Al decir «", frase, "», Noxus ejecutará:", size="1",
                color=theme.MUTED, weight="bold")
    )
    return rx.vstack(
        titulo,
        rx.hstack(
            rx.button(
                rx.icon("list-plus", size=14),
                rx.cond(etiqueta != "", etiqueta, "Elegir una acción del panel"),
                on_click=VozState.abrir_picker_alexa(slot),
                size="2", variant="surface", flex="1", justify_content="flex-start",
                white_space="normal", height="auto", min_height="34px",
            ),
            rx.button(
                rx.icon("workflow", size=14), "Nueva secuencia",
                on_click=DashboardState.iniciar_secuencia_alexa(slot),
                size="2", variant="soft", color_scheme="blue",
                flex_shrink="0", title="Combinar varias acciones en orden",
            ),
            spacing="2", width="100%", align="stretch", wrap="wrap",
        ),
        spacing="1", width="100%", align="start",
    )


def _alexa_editor() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.hstack(rx.icon("audio-lines", size=18, color=theme.ACCENT),
                          "Publicar en Alexa", spacing="2", align="center"),
            ),
            rx.vstack(
                rx.text(
                    "Alexa Smart Home fija los verbos «enciende», «activa», "
                    "«apaga» y «desactiva». Aquí eliges solo el nombre y qué "
                    "ejecutará cada orden.",
                    size="1", color=theme.MUTED,
                ),
                rx.vstack(
                    rx.text("Nombre en Alexa (sin verbos)",
                            size="1", color=theme.MUTED, weight="bold"),
                    rx.input(
                        value=VozState.alexa_nombre,
                        on_change=VozState.set_alexa_nombre,
                        placeholder="Habitación, Netflix, TV del salón...",
                        width="100%", auto_complete=False,
                    ),
                    rx.cond(
                        VozState.alexa_accion_es_desactivar,
                        rx.text(
                            "Para decir «Alexa, apaga Habitación» o «Alexa, "
                            "desactiva Todo Noxus», escribe solo «Habitación» o "
                            "«Todo Noxus».", size="1", color=theme.MUTED,
                        ),
                        rx.cond(
                            VozState.alexa_es_accion,
                            rx.text(
                                "Para decir «Alexa, enciende Netflix» o «Alexa, "
                                "activa Netflix», escribe solo «Netflix».",
                                size="1", color=theme.MUTED,
                            ),
                            rx.text(
                                "Ejemplo: para decir «Alexa, apaga Habitación», "
                                "escribe solo «Habitación».",
                                size="1", color=theme.MUTED,
                            ),
                        ),
                    ),
                    rx.cond(
                        (VozState.alexa_nombre_power_con_verbo |
                         VozState.alexa_nombre_accion_con_verbo),
                        rx.hstack(
                            rx.icon("triangle-alert", size=16,
                                    color=theme.WARNING, flex_shrink="0"),
                            rx.cond(
                                VozState.alexa_accion_es_desactivar,
                                rx.text(
                                    "Quita el verbo del nombre: Alexa ya añade "
                                    "«apaga» o «desactiva». Usa solo «Habitación» "
                                    "o «Todo Noxus».",
                                    size="1", color=theme.WARNING,
                                ),
                                rx.text(
                                    "Quita el verbo del nombre. Alexa ya lo "
                                    "añade al invocar el elemento.",
                                    size="1", color=theme.WARNING,
                                ),
                            ),
                            spacing="2", align="start", width="100%",
                            padding="9px 10px", border_radius="9px",
                            background=theme.alpha(theme.WARNING, 0.08),
                            border=f"1px solid {theme.alpha(theme.WARNING, 0.3)}",
                        ),
                    ),
                    spacing="1", width="100%", align="start",
                ),
                rx.vstack(
                    rx.text("Órdenes exactas que aceptará Alexa", size="1",
                            color=theme.MUTED, weight="bold"),
                    rx.select.root(
                        rx.select.trigger(width="100%"),
                        select_content(
                            rx.select.item("Dispositivo: «enciende» y «apaga»",
                                           value="power"),
                            rx.select.item("Acción: «activar» o «desactivar»",
                                           value="action"),
                        ),
                        value=VozState.alexa_comportamiento,
                        on_change=VozState.set_alexa_comportamiento,
                    ),
                    rx.cond(
                        VozState.alexa_es_accion,
                        rx.vstack(
                            rx.text("Frase: «",
                                    VozState.alexa_frase_accion_principal, "»",
                                    size="1", color=theme.ACCENT),
                            rx.text("También: «",
                                    VozState.alexa_frase_accion_alternativa, "»",
                                    size="1", color=theme.ACCENT),
                            spacing="0", align="start",
                        ),
                        rx.vstack(
                            rx.text("Frase ON: «", VozState.alexa_frase_encender,
                                    "»", size="1", color=theme.ACCENT),
                            rx.text("Frase OFF: «", VozState.alexa_frase_apagar,
                                    "»", size="1", color=theme.ACCENT),
                            spacing="0", align="start",
                        ),
                    ),
                    spacing="1", width="100%", align="start",
                ),
                rx.cond(
                    VozState.alexa_es_accion,
                    rx.vstack(
                        rx.vstack(
                            rx.text("Orden estándar de Alexa", size="1",
                                    color=theme.MUTED, weight="bold"),
                            rx.select.root(
                                rx.select.trigger(width="100%"),
                                select_content(
                                    rx.select.item(
                                        "Activar: «enciende/activa <nombre>»",
                                        value="activate"),
                                    rx.select.item(
                                        "Desactivar: «apaga/desactiva <nombre>»",
                                        value="deactivate"),
                                ),
                                value=VozState.alexa_scene_operation,
                                on_change=VozState.set_alexa_scene_operation,
                            ),
                            spacing="1", width="100%", align="start",
                        ),
                        _selector_accion(
                            VozState.alexa_frase_accion_principal,
                            VozState.alexa_action_label, "action",
                            VozState.alexa_frase_accion_alternativa),
                        rx.hstack(
                            rx.vstack(
                                rx.text("Veces", size="1", color=theme.MUTED),
                                rx.input(type="number", min="1", max="50",
                                         value=VozState.alexa_repeticiones,
                                         on_change=VozState.set_alexa_repeticiones,
                                         width="90px"),
                                spacing="1", align="start"),
                            rx.vstack(
                                rx.text("Pausa entre pulsos (s)", size="1",
                                        color=theme.MUTED),
                                rx.input(type="number", min="0", max="60", step="0.1",
                                         value=VozState.alexa_pausa,
                                         on_change=VozState.set_alexa_pausa,
                                         width="120px"),
                                spacing="1", align="start"),
                            spacing="4", align="start", wrap="wrap",
                        ),
                        rx.text(
                            "Es una orden estándar de Alexa, no una frase libre. "
                            "Elige activar para Netflix, Home o volumen; elige "
                            "desactivar para secuencias como apagar Habitación "
                            "o Todo Noxus.",
                            size="1", color=theme.MUTED,
                        ),
                        spacing="3", width="100%", align="start",
                    ),
                    rx.vstack(
                        rx.vstack(
                            rx.text("Tipo que mostrará Alexa", size="1",
                                    color=theme.MUTED, weight="bold"),
                            rx.select.root(
                                rx.select.trigger(width="100%"),
                                select_content(*[
                                    rx.select.item(etiqueta, value=valor)
                                    for valor, etiqueta in _CATEGORIAS_ALEXA
                                ]),
                                value=VozState.alexa_categoria,
                                on_change=VozState.set_alexa_categoria,
                            ),
                            spacing="1", width="100%", align="start",
                        ),
                        _selector_accion(VozState.alexa_frase_encender,
                                         VozState.alexa_on_label, "on"),
                        _selector_accion(VozState.alexa_frase_apagar,
                                         VozState.alexa_off_label, "off"),
                        rx.text(
                            "Para «Alexa, apaga Habitación», el nombre debe ser "
                            "«Habitación» y la secuencia que apaga los elementos "
                            "debe estar en la orden APAGAR.",
                            size="1", color=theme.ACCENT,
                        ),
                        rx.text(
                            "Si el aparato usa una sola tecla para alternar, elige "
                            "la misma acción en ambos campos. Alexa no podrá conocer "
                            "su estado físico: Noxus mantendrá un estado estimado y "
                            "solo enviará el pulso cuando tenga que cambiarlo.",
                            size="1", color=theme.WARNING,
                        ),
                        spacing="3", width="100%", align="start",
                    ),
                ),
                rx.text(
                    "No se publica una frase libre: Alexa conserva esos verbos "
                    "predefinidos y Noxus asigna la acción de cada orden.",
                    size="1", color=theme.MUTED,
                ),
                rx.hstack(
                    rx.spacer(),
                    rx.button("Cancelar", variant="surface",
                              on_click=VozState.cerrar_editor_alexa),
                    rx.button(rx.icon("cloud-upload", size=14), "Guardar y publicar",
                              on_click=VozState.guardar_elemento_alexa),
                    spacing="2", width="100%", wrap="wrap",
                ),
                spacing="3", width="100%", align="start",
            ),
            max_width="580px",
        ),
        open=VozState.editor_alexa_abierto,
        on_open_change=VozState.alexa_editor_open_change,
    )


def _tarjeta_alexa(item: rx.Var) -> rx.Component:
    return rx.hstack(
        rx.box(
            rx.cond(item["tipo"] == "Acción",
                    rx.icon("zap", size=17, color=theme.ACCENT),
                    rx.icon("power", size=17, color=theme.ACCENT)),
            padding="9px", border_radius="10px",
            background=theme.alpha(theme.ACCENT, 0.12),
        ),
        rx.vstack(
            rx.hstack(
                rx.text(item["nombre"], size="2", weight="bold", color=theme.TEXT),
                rx.badge(item["tipo"], variant="soft", size="1"),
                rx.cond(item["rota"], rx.badge("Revisar", color_scheme="red",
                                                variant="soft", size="1")),
                spacing="2", align="center", wrap="wrap",
            ),
            rx.text(item["detalle"], size="1", color=theme.MUTED),
            rx.text(item["frase"], size="1", color=theme.ACCENT,
                    style={"font-family": theme.FONT_MONO}),
            spacing="1", align="start", min_width="0",
        ),
        rx.spacer(),
        rx.button(rx.icon("pencil", size=13), size="1", variant="surface",
                  on_click=VozState.editar_alexa(item["id"]), title="Editar"),
        confirm_delete_dialog(
            rx.button(rx.icon("trash-2", size=13), size="1", variant="surface",
                      color_scheme="red"),
            title="¿Eliminarlo también de Alexa?", tipo="elemento",
            nombre=item["nombre"],
            on_confirm=VozState.borrar_elemento_alexa(item["id"], item["nombre"]),
        ),
        align="center", spacing="3", width="100%", wrap="wrap",
        padding="12px", border_radius="12px",
        background=theme.BG_CARD, border=f"1px solid {theme.BORDER}",
    )


def _catalogo_alexa() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.vstack(
                rx.heading("Integración con Alexa", size="5", color=theme.TEXT),
                rx.text(
                    "Crea aquí exactamente lo que Alexa verá. Altas, cambios y "
                    "bajas se sincronizan automáticamente; no hay que volver a "
                    "abrir la app de Alexa.",
                    size="1", color=theme.MUTED,
                ),
                spacing="1", align="start",
            ),
            rx.spacer(),
            rx.button(rx.icon("plus", size=14), "Crear elemento para Alexa",
                      on_click=VozState.nuevo_alexa, size="2"),
            align="center", spacing="3", width="100%", wrap="wrap",
        ),
        rx.cond(
            VozState.alexa_error != "",
            rx.hstack(
                rx.icon("triangle-alert", size=16, color=theme.DANGER),
                rx.text(VozState.alexa_error, size="1", color=theme.DANGER),
                spacing="2", align="center", padding="10px 12px", width="100%",
                border=f"1px solid {theme.alpha(theme.DANGER, 0.35)}",
                border_radius="10px",
            ),
        ),
        rx.cond(
            VozState.hay_elementos_alexa,
            rx.vstack(rx.foreach(VozState.alexa_elementos, _tarjeta_alexa),
                      spacing="2", width="100%"),
            rx.box(
                rx.text(
                    "Aún no has publicado nada. Los dispositivos que aparecieron "
                    "automáticamente antes se retirarán de Alexa al reiniciar el "
                    "panel; desde ahora solo aparecerá lo que crees aquí.",
                    size="1", color=theme.MUTED,
                ),
                padding="16px", width="100%", border_radius="10px",
                background=theme.BG_CARD, border=f"1px solid {theme.BORDER}",
            ),
        ),
        _alexa_editor(),
        catalog_picker(
            is_open=VozState.picker_alexa_abierto,
            title=VozState.alexa_picker_title,
            sections=VozState.alexa_picker_sections,
            query=VozState.alexa_picker_query,
            on_query=VozState.set_alexa_picker_query,
            on_pick=VozState.elegir_accion_alexa,
            on_close=VozState.cerrar_picker_alexa,
            on_open_change=VozState.picker_alexa_open_change,
            icon="list-plus",
            empty_text="No hay ninguna acción compatible con esa búsqueda.",
        ),
        spacing="4", width="100%", align="start",
    )


def _desplegable(titulo: str, descripcion: str, icono: str,
                 contenido: rx.Component) -> rx.Component:
    """Bloque secundario nativo, cerrado por defecto y sin estado extra."""
    return rx.el.details(
        rx.el.summary(
            rx.hstack(
                rx.icon(icono, size=16, color=theme.MUTED, flex_shrink="0"),
                rx.vstack(
                    rx.text(titulo, size="2", weight="bold", color=theme.TEXT),
                    rx.text(descripcion, size="1", color=theme.MUTED),
                    spacing="0", align="start",
                ),
                spacing="3", align="center", width="100%",
            ),
            cursor="pointer", padding="12px 14px",
        ),
        rx.box(contenido, padding="4px 14px 14px"),
        width="100%", border=f"1px solid {theme.BORDER}",
        border_radius="12px", background=theme.BG_CARD,
    )


def _voz_local() -> rx.Component:
    return rx.vstack(
        rx.vstack(
            rx.heading("Frases exactas", size="4", color=theme.TEXT),
            rx.text(
                "Asocia una frase libre, como «buenas noches», a una acción. "
                "Solo la usan Siri y los clientes que llaman a /api/voz; no "
                "crea ni modifica dispositivos en Alexa oficial.",
                size="1", color=theme.MUTED,
            ),
            spacing="1", align="start",
        ),
        rx.hstack(
            rx.input(value=VozState.nueva_frase,
                     on_change=VozState.set_nueva_frase,
                     placeholder="Lo que vas a decir: buenas noches",
                     size="2", flex="1", min_width="180px"),
            rx.select.root(
                rx.select.trigger(placeholder="Qué tiene que hacer", width="100%"),
                select_content(
                    rx.foreach(
                        VozState.catalogo,
                        lambda c: rx.select.item(c["etiqueta"], value=c["id"]),
                    ),
                ),
                value=VozState.nuevo_comando,
                on_change=VozState.set_nuevo_comando,
                size="2",
            ),
            rx.button(rx.icon("plus", size=14), "Añadir",
                      on_click=VozState.anadir, size="2", flex_shrink="0"),
            spacing="2", width="100%", wrap="wrap",
        ),
        rx.cond(
            VozState.hay_guardados,
            rx.vstack(rx.foreach(VozState.guardados, _fila),
                      spacing="2", width="100%"),
            rx.box(
                rx.text("No hay frases locales configuradas. Alexa oficial "
                        "seguirá funcionando con normalidad.",
                        size="1", color=theme.MUTED),
                padding="18px 0",
            ),
        ),
        rx.divider(border_color=theme.BORDER),
        _clave(),
        spacing="4", width="100%", align="start",
    )


def voz_view() -> rx.Component:
    return rx.vstack(
        _catalogo_alexa(),
        _desplegable(
            "Configuración avanzada de Alexa",
            "Credenciales, diagnóstico y nuevo código de enlace.",
            "settings-2", _alexa_cloud(),
        ),
        _desplegable(
            "Siri y control local (opcional)",
            "Atajos y frases de /api/voz; no afecta a Alexa oficial.",
            "mic", _voz_local(),
        ),
        spacing="4", width="100%", max_width="860px", align="start",
        padding_bottom="6",
        on_mount=VozState.on_load,
    )
