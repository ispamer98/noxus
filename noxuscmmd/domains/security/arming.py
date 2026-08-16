"""
Armar y desarmar SIN sesión — el equivalente de nodes/operations.py para la
alarma. Lo llaman SecurityState/GroupsState (que se quedan con sus Vars) y el
motor de automatizaciones, que puede armar la casa a una hora sin que haya
nadie delante de una pantalla.

No hace falta empujar el cambio a las pestañas abiertas: SecurityState.sync_loop
relee estado_seguridad.json cada 0,5 s y GroupsState.sync_loop relee
grupos_armado.json cada segundo. Escribir en disco ES la forma de avisar a
todo el mundo; las Vars que tocan los manejadores solo se adelantan medio
segundo para que el botón no parezca muerto al pulsarlo.

Ojo con el "usuario": aquí no hay pestaña de la que sacar la identidad push,
así que por defecto se registra como "sistema", que es exactamente lo que
significa según audit.py — algo que ha hecho el panel sin que nadie lo pulse.
"""
import asyncio

from . import abiertos, groups_store, logs, shared_state
from .audit import SISTEMA


class ArmingError(Exception):
    """El grupo al que apunta la orden ya no existe."""


async def _propagar_al_principal(armado: bool) -> None:
    """Puente con Grupos: el armado general y el grupo marcado como PRINCIPAL
    son la misma cosa vista desde dos pantallas, así que mover uno mueve el
    otro. Se hace como cambio de configuración, no como evento, para que no se
    duplique la línea del registro."""
    principal = await asyncio.to_thread(groups_store.ensure_principal_group)
    await asyncio.to_thread(groups_store.set_group_armed, principal["id"], armado)


def _registrar_general(armado: bool, usuario: str) -> None:
    # Al armar se apunta qué se queda abierto en ese momento; al desarmar no
    # hay nada que apuntar. Mismo formato de texto que el resto para que
    # log_row lo reconozca y muestre su desplegable "ⓘ".
    detalle = abiertos.detalle_armado(abiertos.abiertos_del_principal()) if armado else ""
    logs.registrar(logs.ALARMA, "ARMADO" if armado else "DESARMADO", usuario, detalle)


async def set_system_armed(armado: bool, usuario: str = SISTEMA) -> bool:
    """Deja el sistema armado o desarmado, tanto da cómo estuviera."""
    await asyncio.to_thread(shared_state.set_sistema_armado, armado)
    await _propagar_al_principal(armado)
    _registrar_general(armado, usuario)
    return armado


async def toggle_system_armed(usuario: str = SISTEMA) -> bool:
    """Conmuta el armado general. Usa shared_state.toggle_sistema_armado en vez
    de leer-y-escribir por separado para que el cambio siga siendo una sola
    operación bajo el cerrojo del fichero."""
    nuevo = await asyncio.to_thread(shared_state.toggle_sistema_armado)
    await _propagar_al_principal(nuevo)
    _registrar_general(nuevo, usuario)
    return nuevo


async def set_group_armed(group_id: str, armado: bool, usuario: str = SISTEMA) -> dict:
    """Arma o desarma UN grupo. Devuelve la ficha del grupo (tal como estaba
    antes del cambio), que es de donde salen el nombre y la marca de principal
    para el mensaje y el registro."""
    grupos = await asyncio.to_thread(groups_store.read_all)
    group = next((g for g in grupos if g["id"] == group_id), None)
    if group is None:
        raise ArmingError(f"El grupo {group_id} ya no existe")

    await asyncio.to_thread(groups_store.set_group_armed, group_id, armado)
    if group["is_principal"]:
        await asyncio.to_thread(shared_state.set_sistema_armado, armado)

    etiqueta = "TOTAL" if group["is_principal"] else group["name"]
    # El nombre de cada miembro abierto lo resuelve abiertos.py leyendo del
    # disco: el que guarda el grupo es una copia del que tenía el sensor al
    # meterlo, así que renombrarlo dejaba el registro nombrando algo que ya no
    # se llamaba así.
    detalle = abiertos.detalle_armado(abiertos.abiertos_de_grupo(group)) if armado else ""
    logs.registrar(logs.GRUPOS, "ARMADO_GRUPO" if armado else "DESARMADO_GRUPO",
                   usuario, detalle, grupo=etiqueta)
    return group


async def toggle_group_armed(group_id: str, usuario: str = SISTEMA) -> tuple[dict, bool]:
    """Conmuta un grupo. Devuelve (ficha del grupo, estado nuevo)."""
    grupos = await asyncio.to_thread(groups_store.read_all)
    group = next((g for g in grupos if g["id"] == group_id), None)
    if group is None:
        raise ArmingError(f"El grupo {group_id} ya no existe")
    nuevo = not group["armed"]
    return await set_group_armed(group_id, nuevo, usuario), nuevo
