"""
Contenido de edición genérico para entidades ESTÁTICAS de registry.py (hosts,
sensores, cámaras...) — reutilizado desde actions_menu() en varias pestañas.
Cada campo es un input de texto pre-rellenado con el valor actual; el
entity_id va oculto para que RegistryState sepa qué entidad tocar.

Devuelve solo el `rx.dialog.content(...)` (no el root/trigger): quien lo usa
decide cómo se dispara (ver ui/dashboard/components/actions_menu.py).
"""
import reflex as rx

from ....domains.devices.registry_state import RegistryState
from .. import theme
from .form_dialog import form_dialog_content, field, dialog_footer, styled_input


def edit_entity_dialog(
    *,
    entity_id: str,
    title: str,
    fields: list[tuple[str, str, str]],  # (field_name, label, valor_actual)
    color_scheme: str = "blue",
    icon: str = "pencil",
) -> rx.Component:
    return form_dialog_content(
        icon=icon,
        title=title,
        accent=theme.ACCENT if color_scheme == "blue" else theme.PURPLE,
        form=rx.form.root(
            rx.vstack(
                rx.input(name="entity_id", value=entity_id, type="hidden"),
                *[
                    field(label, styled_input(name=field_name, default_value=valor))
                    for field_name, label, valor in fields
                ],
                dialog_footer(confirm_label="Guardar", color_scheme=color_scheme),
                spacing="3",
                width="100%",
            ),
            on_submit=RegistryState.submit_edit_entity,
        ),
    )
