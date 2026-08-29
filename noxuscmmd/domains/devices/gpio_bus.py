"""
Control genérico de relés/GPIO. Cualquier RelayEntity se enciende/apaga aquí
sin importar qué host físico tenga el pin (Raspberry, Pi Zero, futuro...).
"""
import asyncio
from . import registry
from . import ssh_bus
from .models import RelayEntity, SSHSpec


def _host_spec(relay: RelayEntity):
    host_entity = registry.hosts()[relay.gpio.host]
    return host_entity.ssh


async def set_pin(ssh: SSHSpec, pin: str, on: bool, timeout: int = 2) -> None:
    """Igual que set_relay pero sobre un host+pin sueltos, sin pasar por un
    RelayEntity del registry — lo usa domains/nodes para relés dados de alta
    en caliente sobre la Raspberry/Pi Zero."""
    val = "dh" if on else "dl"
    salida = await ssh_bus.ssh_execute(
        ssh, f"raspi-gpio set {pin} op {val}", timeout=timeout)
    if salida.lstrip().upper().startswith("ERROR:"):
        raise RuntimeError(salida)


async def read_pin(ssh: SSHSpec, pin: str, timeout: int = 2) -> str:
    """Lectura cruda del estado de un pin (salida de raspi-gpio tal cual) —
    para el botón "leer pin" del panel de acciones de un host."""
    salida = await ssh_bus.ssh_execute(
        ssh, f"raspi-gpio get {pin}", timeout=timeout)
    if salida.lstrip().upper().startswith("ERROR:"):
        raise RuntimeError(salida)
    return salida


async def set_relay(relay: RelayEntity, on: bool, timeout: int = 2) -> None:
    await set_pin(_host_spec(relay), relay.gpio.pin, on, timeout=timeout)


async def pulse_relay(relay: RelayEntity, seconds: float = 5.0) -> None:
    """Enciende, espera y apaga — usado hoy por el test del ventilador."""
    await set_relay(relay, True, timeout=3)
    await asyncio.sleep(seconds)
    await set_relay(relay, False, timeout=3)
