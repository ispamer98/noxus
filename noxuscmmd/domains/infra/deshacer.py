"""
Deshacer lo último, desde el propio aviso de que se ha hecho.

EL PROBLEMA QUE RESUELVE: media docena de acciones del panel no dicen nada al
salir bien. Quitas un sensor del plano y el icono desaparece; borras un panel de
métricas y la tarjeta se va. Si te has equivocado —o si no estabas seguro de
haber pulsado— no hay ni confirmación ni marcha atrás, y lo único que queda es
volver a montarlo a mano.

CÓMO, sin resultar invasivo: no hay diálogo de «¿estás seguro?» delante de cada
cosa. Se hace, se avisa, y el aviso lleva un botón de «Deshacer» que dura ocho
segundos. Quien acertó no tiene que confirmar nada; quien se equivocó tiene ocho
segundos para arreglarlo. Los diálogos de confirmación se quedan donde ya
estaban: en los borrados de verdad (un sensor, un grupo), que no se pueden
deshacer solos.

NO SE GUARDA UNA FUNCIÓN, SE GUARDA UN HECHO. El estado guarda qué pasó
({"tipo": ..., "datos": {...}}) y `DeshacerState.deshacer` sabe revertir cada
tipo. Es a propósito: en el estado de Reflex no caben funciones, y aunque
cupieran, guardar «cómo revertir» junto a «qué pasó» hace que un cambio en la
forma de revertir haya que perseguirlo por todos los sitios que apuntan cosas.

Solo se guarda UNO, el último. Una pila de deshacer en un panel de domótica es
prometer más de lo que se puede cumplir: entre medias han podido pasar cinco
cosas más, algunas del propio sistema, y «deshacer» dejaría de significar lo que
la gente espera.
"""
import reflex as rx
from reflex.components.sonner.toast import ToastAction

from ..nodes import store as nodes_store

# Cuánto dura la oportunidad. Ocho segundos son los que se tarda en darse cuenta
# de que se ha pulsado lo que no era.
SEGUNDOS = 8


class DeshacerState(rx.State):
    # Qué fue lo último que se puede deshacer. Privado: lo pinta el propio aviso,
    # el navegador no tiene que saberlo.
    _ultimo: dict = {}

    @rx.event
    def apuntar(self, tipo: str, datos: dict, texto: str):
        """Deja apuntado lo último deshacible y devuelve el aviso con su botón.

        Quien hace la acción llama a esto y devuelve lo que devuelva:

            return DeshacerState.apuntar("plano_quitado", {...}, "Sensor quitado")
        """
        self._ultimo = {"tipo": tipo, "datos": datos}
        return rx.toast(
            texto,
            action=ToastAction(label="Deshacer", on_click=DeshacerState.deshacer),
            duration=SEGUNDOS * 1000,
            close_button=True,
        )

    @rx.event
    def deshacer(self):
        """Revierte lo apuntado. Si ya no hay nada, lo dice en vez de callarse:
        un botón que no hace nada es peor que no tener botón."""
        hecho = dict(self._ultimo or {})
        self._ultimo = {}
        tipo, datos = hecho.get("tipo", ""), hecho.get("datos") or {}
        if not tipo:
            return rx.toast.info("Ya no hay nada que deshacer.",
                                 position="top-center")
        try:
            texto = _REVERSIONES[tipo](datos)
        except KeyError:
            return rx.toast.error("Esto no se puede deshacer.",
                                  position="top-center")
        except Exception as e:
            return rx.toast.error(f"No se pudo deshacer: {e}",
                                  position="top-center")
        return rx.toast.success(texto, position="top-center")


# ── Cómo se revierte cada cosa ───────────────────────────────────────────────
# Cada una devuelve el texto que se le dice a quien lo deshizo. Están aquí y no
# repartidas por los States para que se vea de un tirón TODO lo que el panel
# promete poder deshacer: si algo no está en esta tabla, no se puede deshacer, y
# eso se sabe leyendo veinte líneas.
def _reponer_en_plano(datos: dict) -> str:
    nodes_store.set_floor_position(
        datos["coleccion"], datos["id"], datos["top"], datos["left"],
        datos.get("plano", ""),
    )
    return f"«{datos.get('nombre', 'El elemento')}» vuelve al plano."


def _reponer_panel(datos: dict) -> str:
    ficha = datos["panel"]
    nodes_store.add_panel(ficha["titulo"], ficha["forma"], ficha["medida"],
                          ficha["dias"], ficha["color"])
    return f"Panel «{ficha['titulo']}» recuperado."


def _reponer_camara_de_sensor(datos: dict) -> str:
    nodes_store.set_sensor_camera(datos["id"], datos.get("camara", ""))
    return f"«{datos.get('nombre', 'El elemento')}» vuelve a su cámara anterior."


_REVERSIONES = {
    "plano_quitado": _reponer_en_plano,
    "panel_borrado": _reponer_panel,
    "camara_cambiada": _reponer_camara_de_sensor,
}
