"""
Atajo para que cualquier State registre una acción atribuyéndosela al
dispositivo desde el que se hizo.

Existe para que en los manejadores no haya que repetir en cada uno el
`get_state(PushState)` y el "si no hay nombre, pon sistema". Eso importa
porque los sitios que registran son decenas: cuando el ritual es de tres
líneas, se acaba olvidando en la mitad, y un registro con agujeros es peor
que no tenerlo — te hace creer que algo no pasó.

Quién es "el dispositivo" sale de la suscripción push de esa pestaña (el
nombre que se puso al registrarla: "iPhone Ana", "Mac Bea"...). Una pestaña
sin notificaciones registradas no tiene nombre, y entonces la acción queda como
"desconocido" — no como "sistema", que se reserva para lo que dispara el propio
panel sin que nadie pulse nada (un sensor por MQTT, una ronda de ping).
"""
from . import logs

DESCONOCIDO = "desconocido"
SISTEMA = "sistema"


async def usuario_de(state) -> str:
    """Nombre del dispositivo que está haciendo la acción."""
    # Import diferido: notifications/state.py importa infra/state.py, que a su
    # vez acaba en nodes — traerlo arriba cierra el círculo al importar.
    from ..notifications.state import PushState
    try:
        push = await state.get_state(PushState)
    except Exception:
        return DESCONOCIDO
    return push.current_user.strip() or DESCONOCIDO


async def registrar(state, categoria: str, accion: str, detalle: str = "",
                    grupo: str = "", entidad: str = "") -> None:
    """Registra una acción de usuario. `state` es el State que la atiende."""
    logs.registrar(categoria, accion, await usuario_de(state), detalle, grupo, entidad)


def registrar_sistema(categoria: str, accion: str, detalle: str = "",
                      grupo: str = "", entidad: str = "") -> int:
    """Registra algo que no ha pulsado nadie: rondas de ping, eventos MQTT,
    automatismos. Sin State porque no hay sesión detrás.

    DEVUELVE EL ID del evento, que es lo que permite colgarle algo después —el
    fotograma de la cámara, sin ir más lejos—. Estuvo devolviendo None y por eso
    la detección de movimiento registraba el evento pero se quedaba sin foto:
    quien la guardaba comprobaba antes que el id fuera un número."""
    return logs.registrar(categoria, accion, SISTEMA, detalle, grupo, entidad)
