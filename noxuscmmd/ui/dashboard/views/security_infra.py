"""
Vista "Seguridad": idéntica a la vista clásica (/clasica) — mismos
componentes (header_view, device_list_view, device_controls_view), mismo
contenedor centrado. No se repiten aquí camera_dialogs()/photo_dialog(): ya
están montados una única vez a nivel de dashboard_page (ver ui/pages/
dashboard.py) y se abren igual desde esta pestaña porque comparten el mismo
estado (CameraState/InfraState) — duplicarlos aquí crearía diálogos por
duplicado.

DESCONECTADA de la navegación (ver la reorganización de sidebar.py): esta
pantalla no aporta nada que "Vista clásica" (el enlace de abajo del todo del
menú) no dé ya — es literalmente el mismo contenido. Mantenerla como pestaña
aparte era una de las doce filas que sobraban. El componente se queda aquí
por si algún día se quiere reaprovechar; nada la importa ahora mismo.
"""
import reflex as rx

from ...views.header import header_view
from ...views.device_list import device_list_view
from ...views.device_controls import device_controls_view


def security_infra_view() -> rx.Component:
    return rx.center(
        rx.vstack(
            header_view(),
            device_list_view(),
            device_controls_view(),
            spacing="6",
            width="100%",
            max_width="450px",
        ),
        width="100%",
    )
