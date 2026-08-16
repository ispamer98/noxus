"""
Vista "Automatizaciones": reglas del tipo CUÁNDO … Y SI … ENTONCES ….

Dos pantallas en una pestaña. La LISTA enseña cada regla con su resumen
escrito en cristiano —generado desde el propio JSON de la regla, así que no
puede mentir sobre lo que hace— y el EDITOR ocupa la pestaña entera en vez de
meterse en un diálogo: son tres bloques con listas dentro, y en una ventanita
modal no cabe sin quedar apretado, sobre todo en el móvil.

Los ajustes de cada paso (hora, días, grados, repeticiones) se pintan
GENÉRICAMENTE a partir de lo que declara su especificación en
domains/automations/. Por eso una acción nueva aparece con sus campos sin
tocar nada de este archivo.
"""
import reflex as rx

from ....domains.automations.state import (
    ACCIONES, CONDICIONES, DISPARADORES, AutomationsState,
)
from .. import theme
from ..components.actions_menu import actions_menu, confirm_delete
from ..components.catalog_picker import catalog_picker
from ..components.form_dialog import (
    dialog_footer, field, form_dialog_content, select_content, styled_input,
)

_DIAS = [(0, "L"), (1, "M"), (2, "X"), (3, "J"), (4, "V"), (5, "S"), (6, "D")]


# ══════════════════════════════════════════════════════════════════════════
# LISTA
# ══════════════════════════════════════════════════════════════════════════
def _estado_ultima(regla: rx.Var) -> rx.Component:
    return rx.hstack(
        rx.icon("history", size=12, color=theme.MUTED),
        rx.text(regla["last_run_text"], size="1", color=theme.MUTED),
        rx.cond(
            regla["last_result"] != "",
            rx.badge(
                rx.match(
                    regla["last_result"],
                    ("ok", "correcto"), ("parcial", "con fallos"), ("error", "falló"),
                    regla["last_result"],
                ),
                variant="soft", size="1",
                color_scheme=rx.match(
                    regla["last_result"],
                    ("ok", "green"), ("parcial", "amber"), ("error", "red"), "gray",
                ),
            ),
        ),
        spacing="2",
        align="center",
        wrap="wrap",
    )


def _rule_card(regla: rx.Var) -> rx.Component:
    activa = regla["enabled"]
    return rx.vstack(
        rx.hstack(
            rx.box(
                rx.icon(regla["icon"].to(str), size=20,
                        color=rx.cond(activa, theme.ACCENT, theme.MUTED)),
                padding="10px",
                border_radius="10px",
                background=rx.cond(activa, theme.alpha(theme.ACCENT, 0.16),
                                   theme.alpha(theme.MUTED, 0.08)),
                flex_shrink="0",
            ),
            rx.vstack(
                rx.text(regla["name"], size="3", weight="bold", color=theme.TEXT),
                # El resumen es lo que de verdad se lee de un vistazo: qué la
                # dispara, qué exige y qué hace.
                rx.text(regla["summary"], size="1", color=theme.MUTED,
                        style={"line-height": "1.5"}),
                spacing="1",
                align="start",
                width="100%",
            ),
            rx.spacer(),
            rx.switch(
                checked=activa,
                on_change=AutomationsState.toggle_rule(regla["id"]),
                color_scheme="blue",
            ),
            actions_menu(
                on_edit=AutomationsState.edit_rule(regla["id"]),
                on_remove=AutomationsState.delete_rule(regla["id"]),
                remove_confirm_title="¿Eliminar automatización?",
                remove_confirm_description=confirm_delete("la automatización", regla["name"]),
                extra_items=[
                    ("play", "Ejecutar ahora", AutomationsState.run_now(regla["id"])),
                    ("copy", "Duplicar", AutomationsState.duplicate_rule(regla["id"])),
                ],
            ),
            spacing="3",
            align="start",
            width="100%",
        ),
        # Motivo por el que se apagó sola (cortafuegos, o apunta a algo
        # borrado). Va en la propia tarjeta porque si no, una regla desactivada
        # parece simplemente desactivada y nadie sabe por qué dejó de funcionar.
        rx.cond(
            regla["disabled_reason"] != "",
            rx.hstack(
                rx.icon("triangle-alert", size=13, color=theme.WARNING, flex_shrink="0"),
                rx.text(regla["disabled_reason"], size="1", color=theme.WARNING),
                spacing="2",
                align="center",
                width="100%",
                padding="8px 10px",
                border_radius="8px",
                background=theme.alpha(theme.WARNING, 0.10),
            ),
        ),
        rx.cond(
            regla["last_error"] != "",
            rx.text(regla["last_error"], size="1", color=theme.DANGER,
                    font_family=theme.FONT_MONO),
        ),
        _estado_ultima(regla),
        spacing="3",
        width="100%",
        align="start",
        background=theme.BG_CARD,
        border=f"1px solid {rx.cond(activa, theme.BORDER, theme.BORDER)}",
        border_radius="12px",
        padding="14px",
        opacity=rx.cond(activa, "1", "0.72"),
    )


def _add_folder_dialog() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.trigger(
            rx.button(rx.icon("folder-plus", size=14), "Carpeta", size="2",
                      variant="surface", color_scheme="gray"),
        ),
        form_dialog_content(
            icon="folder-plus",
            title="Nueva carpeta",
            form=rx.form.root(
                rx.vstack(
                    field("Nombre", styled_input(name="name", placeholder="Rutinas de noche"),
                          hint="Solo sirve para organizar la lista; no afecta a cómo se ejecutan."),
                    dialog_footer(confirm_label="Crear"),
                    spacing="3",
                    width="100%",
                ),
                on_submit=AutomationsState.submit_add_folder,
                reset_on_submit=True,
            ),
        ),
    )


def _folder_section(carpeta: rx.Var) -> rx.Component:
    reglas = AutomationsState.rules_by_folder[carpeta["id"].to(str)].to(list[dict])
    return rx.cond(
        reglas.length() > 0,
        rx.vstack(
            rx.hstack(
                rx.icon("folder", size=14, color=theme.MUTED),
                rx.text(carpeta["name"], size="1", weight="bold", color=theme.MUTED,
                        letter_spacing="0.08em", text_transform="uppercase"),
                rx.spacer(),
                rx.icon("trash-2", size=13, color=theme.MUTED, cursor="pointer",
                        on_click=AutomationsState.delete_folder(carpeta["id"]),
                        title="Borrar la carpeta (las reglas se quedan sueltas)"),
                align="center",
                spacing="2",
                width="100%",
            ),
            rx.foreach(reglas, _rule_card),
            spacing="3",
            width="100%",
            align="start",
        ),
    )


def _lista() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.vstack(
                rx.heading("Auto", size="5", color=theme.TEXT),
                rx.text("Si pasa esto, haz esto otro. Las listas se actualizan solas "
                        "conforme das de alta equipos, luces o mandos.",
                        size="1", color=theme.MUTED),
                spacing="1",
                align="start",
            ),
            rx.spacer(),
            _add_folder_dialog(),
            rx.button(rx.icon("plus", size=14), "Nueva automatización",
                      on_click=AutomationsState.new_rule,
                      size="2", color_scheme="blue"),
            spacing="2",
            align="center",
            width="100%",
            wrap="wrap",
        ),
        rx.cond(
            AutomationsState.status != "",
            rx.text(AutomationsState.status, size="1", color=theme.MUTED),
        ),
        rx.cond(
            AutomationsState.hay_reglas,
            rx.vstack(
                rx.foreach(AutomationsState.folders, _folder_section),
                rx.cond(
                    AutomationsState.rules_sin_carpeta.length() > 0,
                    rx.vstack(
                        rx.cond(
                            AutomationsState.folders.length() > 0,
                            rx.text("SIN CARPETA", size="1", weight="bold", color=theme.MUTED,
                                    letter_spacing="0.08em"),
                        ),
                        rx.foreach(AutomationsState.rules_sin_carpeta, _rule_card),
                        spacing="3",
                        width="100%",
                        align="start",
                    ),
                ),
                spacing="5",
                width="100%",
                align="start",
            ),
            _vacio(),
        ),
        spacing="4",
        width="100%",
        align="start",
        padding_bottom="6",
    )


def _vacio() -> rx.Component:
    return rx.vstack(
        rx.icon("workflow", size=34, color=theme.MUTED, opacity="0.5"),
        rx.text("Todavía no hay ninguna automatización", size="3", weight="bold",
                color=theme.TEXT),
        rx.text("Por ejemplo: «a las 22:30, si el PC está en línea → apagarlo», o "
                "«si la Raspberry pasa de 70 °C → encender el ventilador y bajar "
                "la velocidad dos veces».",
                size="1", color=theme.MUTED, text_align="center", max_width="460px"),
        rx.button(rx.icon("plus", size=14), "Crear la primera",
                  on_click=AutomationsState.new_rule, size="2", color_scheme="blue",
                  margin_top="2"),
        spacing="2",
        align="center",
        justify="center",
        width="100%",
        padding_y="9",
        border=f"1px dashed {theme.BORDER}",
        border_radius="14px",
    )


# ══════════════════════════════════════════════════════════════════════════
# EDITOR
# ══════════════════════════════════════════════════════════════════════════
def _campo_dias(fila: rx.Var, indice: rx.Var, seccion: str, campo: rx.Var) -> rx.Component:
    elegidos = fila["params"].to(dict[str, str])[campo["name"].to(str)]
    return rx.hstack(
        *[
            rx.box(
                rx.text(letra, size="1", weight="bold"),
                on_click=AutomationsState.toggle_day(seccion, indice, campo["name"], numero),
                cursor="pointer",
                padding="6px 0",
                width="32px",
                text_align="center",
                border_radius="8px",
                border=f"1px solid {theme.BORDER}",
                color=rx.cond(elegidos.contains(str(numero)), theme.BG_APP, theme.MUTED),
                background=rx.cond(elegidos.contains(str(numero)), theme.ACCENT, "transparent"),
            )
            for numero, letra in _DIAS
        ],
        spacing="1",
        wrap="wrap",
    )


def _campo(fila: rx.Var, indice: rx.Var, seccion: str, campo: rx.Var) -> rx.Component:
    """Un ajuste, pintado según lo que declare su `kind`. Es lo que hace que
    añadir un disparador o una acción nueva no obligue a tocar esta vista."""
    valor = fila["params"].to(dict[str, str])[campo["name"].to(str)]
    cambiar = lambda v: AutomationsState.set_param(seccion, indice, campo["name"], v)
    return rx.vstack(
        rx.text(campo["label"], size="1", color=theme.MUTED),
        rx.match(
            campo["kind"],
            ("days", _campo_dias(fila, indice, seccion, campo)),
            ("time", rx.input(type="time", value=valor, on_change=cambiar,
                              size="2", width="130px")),
            ("number", rx.input(type="number", value=valor, on_change=cambiar,
                                size="2", width="110px")),
            ("bool", rx.switch(checked=valor == "true", color_scheme="blue",
                               on_change=lambda v: AutomationsState.set_param(
                                   seccion, indice, campo["name"],
                                   rx.cond(v, "true", "false")))),
            ("text", rx.input(value=valor, on_change=cambiar, size="2", width="100%",
                              auto_complete=False)),
            # choice y tristate son el mismo control; solo cambian las opciones.
            rx.select.root(
                rx.select.trigger(width="100%"),
                select_content(
                    rx.foreach(
                        campo["options"].to(list[dict]),
                        lambda o: rx.select.item(o["t"], value=o["v"]),
                    ),
                ),
                value=valor,
                on_change=cambiar,
            ),
        ),
        rx.cond(campo["help"] != "",
                rx.text(campo["help"], size="1", color=theme.MUTED, opacity="0.7")),
        spacing="1",
        align="start",
        min_width="130px",
    )


def _ajustes_accion(fila: rx.Var, indice: rx.Var) -> rx.Component:
    """Repeticiones, pausa y "seguir si falla" — solo de las acciones. Las
    repeticiones son la pieza que permite «pulsa bajar velocidad dos veces»
    sin tener que añadir el mismo paso dos veces."""
    return rx.hstack(
        rx.vstack(
            rx.text("Veces", size="1", color=theme.MUTED),
            rx.input(type="number", min="1", max="50", value=fila["repeat"], size="2",
                     width="72px",
                     on_change=lambda v: AutomationsState.set_action_field(indice, "repeat", v)),
            spacing="1", align="start",
        ),
        rx.cond(
            fila["repeat"] != "1",
            rx.vstack(
                rx.text("Pausa entre ellas (s)", size="1", color=theme.MUTED),
                rx.input(type="number", step="0.1", min="0", value=fila["repeat_pause"],
                         size="2", width="92px",
                         on_change=lambda v: AutomationsState.set_action_field(
                             indice, "repeat_pause", v)),
                spacing="1", align="start",
            ),
        ),
        rx.vstack(
            rx.text("Seguir si falla", size="1", color=theme.MUTED),
            rx.switch(checked=fila["continue_on_error"], color_scheme="blue",
                      on_change=lambda v: AutomationsState.set_action_field(
                          indice, "continue_on_error", v)),
            spacing="1", align="start",
        ),
        spacing="4",
        align="start",
        wrap="wrap",
    )


def _fila(fila: rx.Var, indice: rx.Var, seccion: str) -> rx.Component:
    es_accion = seccion == ACCIONES
    return rx.vstack(
        rx.hstack(
            rx.cond(
                es_accion,
                rx.badge((indice + 1).to_string(), variant="soft", size="1",
                         color_scheme="blue", flex_shrink="0"),
            ),
            rx.text(fila["text"], size="2", color=theme.TEXT, weight="medium"),
            rx.spacer(),
            rx.cond(
                es_accion,
                rx.hstack(
                    rx.icon("chevron-up", size=15, color=theme.MUTED, cursor="pointer",
                            title="Subir",
                            on_click=AutomationsState.move_action(indice, -1)),
                    rx.icon("chevron-down", size=15, color=theme.MUTED, cursor="pointer",
                            title="Bajar",
                            on_click=AutomationsState.move_action(indice, 1)),
                    spacing="1",
                ),
            ),
            rx.icon("x", size=15, color=theme.MUTED, cursor="pointer", title="Quitar",
                    on_click=AutomationsState.remove_row(seccion, indice)),
            spacing="2",
            align="center",
            width="100%",
        ),
        rx.cond(
            fila["fields"].to(list[dict]).length() > 0,
            rx.hstack(
                rx.foreach(fila["fields"].to(list[dict]),
                           lambda c: _campo(fila, indice, seccion, c)),
                spacing="4",
                align="start",
                wrap="wrap",
                width="100%",
            ),
        ),
        rx.cond(es_accion, _ajustes_accion(fila, indice)),
        spacing="3",
        width="100%",
        align="start",
        background=theme.BG_APP,
        border=f"1px solid {theme.BORDER}",
        border_radius="10px",
        padding="12px",
    )


def _bloque(numero: str, titulo: str, ayuda: str, icono: str, filas, seccion: str,
            cabecera_extra=None) -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.box(
                rx.text(numero, size="2", weight="bold", color=theme.ACCENT),
                width="26px", height="26px",
                display="flex", align_items="center", justify_content="center",
                border_radius="50%",
                background=theme.alpha(theme.ACCENT, 0.16),
                border=f"1px solid {theme.alpha(theme.ACCENT, 0.35)}",
                flex_shrink="0",
            ),
            rx.vstack(
                rx.text(titulo, size="3", weight="bold", color=theme.TEXT,
                        letter_spacing="0.04em"),
                rx.text(ayuda, size="1", color=theme.MUTED),
                spacing="0",
                align="start",
            ),
            rx.spacer(),
            *([cabecera_extra] if cabecera_extra is not None else []),
            spacing="3",
            align="center",
            width="100%",
            wrap="wrap",
        ),
        rx.cond(
            filas.to(list[dict]).length() > 0,
            rx.vstack(
                rx.foreach(filas.to(list[dict]), lambda f, i: _fila(f, i, seccion)),
                spacing="2",
                width="100%",
                align="start",
            ),
        ),
        rx.button(
            rx.icon("plus", size=14), "Añadir",
            on_click=AutomationsState.open_picker(seccion),
            size="2", variant="surface", color_scheme="blue",
        ),
        spacing="3",
        width="100%",
        align="start",
        background=theme.BG_CARD,
        border=f"1px solid {theme.BORDER}",
        border_radius="14px",
        padding="16px",
    )


def _selector_match() -> rx.Component:
    return rx.select.root(
        rx.select.trigger(width="150px"),
        select_content(
            rx.select.item("Se cumplen TODAS", value="all"),
            rx.select.item("Basta con UNA", value="any"),
        ),
        value=AutomationsState.draft_match,
        on_change=AutomationsState.set_draft_match,
    )


def _editor() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.icon("arrow-left", size=18, color=theme.MUTED, cursor="pointer",
                    on_click=AutomationsState.cancel_edit, title="Volver sin guardar"),
            rx.heading(AutomationsState.titulo_editor, size="5", color=theme.TEXT),
            rx.spacer(),
            rx.button("Cancelar", on_click=AutomationsState.cancel_edit,
                      size="2", variant="soft", color_scheme="gray"),
            rx.button(rx.icon("save", size=14), "Guardar",
                      on_click=AutomationsState.save_rule, size="2", color_scheme="blue"),
            spacing="3",
            align="center",
            width="100%",
            wrap="wrap",
        ),
        rx.cond(
            AutomationsState.status != "",
            rx.text(AutomationsState.status, size="1", color=theme.WARNING),
        ),

        # Ficha
        rx.hstack(
            rx.vstack(
                rx.text("Nombre", size="1", color=theme.MUTED),
                styled_input(value=AutomationsState.draft_name,
                             on_change=AutomationsState.set_draft_name,
                             placeholder="Apagar el PC de noche", width="100%"),
                spacing="1", align="start", flex="1", min_width="220px",
            ),
            rx.vstack(
                rx.text("Carpeta", size="1", color=theme.MUTED),
                rx.select.root(
                    rx.select.trigger(placeholder="Sin carpeta", width="100%"),
                    select_content(
                        rx.select.item("Sin carpeta", value=""),
                        rx.foreach(AutomationsState.folders,
                                   lambda c: rx.select.item(c["name"], value=c["id"])),
                    ),
                    value=AutomationsState.draft_folder,
                    on_change=AutomationsState.set_draft_folder,
                ),
                spacing="1", align="start", min_width="170px",
            ),
            rx.vstack(
                rx.text("Espera mínima entre disparos (s)", size="1", color=theme.MUTED),
                rx.input(type="number", min="0", value=AutomationsState.draft_cooldown,
                         on_change=AutomationsState.set_draft_cooldown,
                         size="3", width="130px"),
                spacing="1", align="start",
            ),
            spacing="4",
            align="start",
            width="100%",
            wrap="wrap",
        ),

        _bloque("1", "CUÁNDO", "Basta con que ocurra uno. Sin ninguno, la regla solo "
                "se ejecuta a mano.", "zap",
                AutomationsState.draft_triggers, DISPARADORES),
        _bloque("2", "Y SI", "Condiciones que se comprueban en el momento de disparar. "
                "Sin ninguna, siempre pasa.", "filter",
                AutomationsState.draft_conditions, CONDICIONES,
                cabecera_extra=_selector_match()),
        _bloque("3", "ENTONCES", "Se ejecutan en orden, de arriba abajo.", "play",
                AutomationsState.draft_actions, ACCIONES),

        spacing="4",
        width="100%",
        align="start",
        padding_bottom="6",
    )


# ══════════════════════════════════════════════════════════════════════════
def automations_view() -> rx.Component:
    return rx.box(
        rx.cond(AutomationsState.editing, _editor(), _lista()),
        catalog_picker(
            is_open=AutomationsState.picker_for != "",
            title=AutomationsState.picker_title,
            sections=AutomationsState.picker_sections,
            query=AutomationsState.picker_query,
            on_query=AutomationsState.set_picker_query,
            on_pick=AutomationsState.pick,
            on_close=AutomationsState.close_picker,
            on_open_change=AutomationsState.picker_open_change,
        ),
        width="100%",
    )
