"""
Modelo genérico de entidades de la casa.

Cada objeto físico (relé, sensor, host, cámara...) es una instancia de una de
estas dataclasses. Añadir hardware nuevo es instanciar la clase que le
corresponda en registry.py — nunca hace falta tocar el State de Reflex.
"""
from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class GPIOSpec:
    """Un pin GPIO y qué host lo ejecuta (la Raspberry, la Pi Zero, etc.)."""
    host: str   # id de un HostEntity en el registry (quién tiene el pin físico)
    pin: str


@dataclass(frozen=True)
class MQTTSpec:
    topic: str


@dataclass(frozen=True)
class SSHSpec:
    host: str
    user: str
    os: Literal["linux", "windows"] = "linux"


@dataclass(frozen=True)
class Accion:
    """Una acción extra que aparece en el panel de control de un host (RDP, WOL...)."""
    nombre: str
    handler_name: str  # nombre del event handler en InfraState, resuelto en runtime


@dataclass(frozen=True)
class Entity:
    id: str
    name: str


@dataclass(frozen=True)
class HostEntity(Entity):
    """Un ordenador/servidor controlable por SSH: apagar, reiniciar, comando custom."""
    ssh: SSHSpec
    mac: str | None = None            # para Wake-on-LAN
    ping_retries: int = 1
    acciones_extra: list[Accion] = field(default_factory=list)
    icon: str | None = None           # None = icono por defecto según el id (ver _STATIC_HOST_ICON)


@dataclass(frozen=True)
class RelayEntity(Entity):
    """Un relé genérico (ventilador, cerradura eléctrica, luz...)."""
    gpio: GPIOSpec


@dataclass(frozen=True)
class BinarySensorEntity(Entity):
    """Sensor todo/nada: magnético de puerta, tamper, PIR..."""
    kind: Literal["door", "tamper", "pir", "generic"] = "generic"
    mqtt: MQTTSpec | None = None
    gpio: GPIOSpec | None = None
    # No hay campo "armable": ningún sensor tiene armado propio. Se arma
    # exclusivamente por pertenecer a un grupo armado (ver
    # ../security/groups_state.py), sin excepciones.
    lock_relay: str | None = None  # id de un RelayEntity que cierra/abre esta puerta
    node: str | None = None        # id de HostEntity al que está cableado (raspberry/pi_zero)
    floor_top: str | None = None   # posición en % sobre room.png (plano de planta) — None = no se muestra
    floor_left: str | None = None
    floor_icon: str | None = None  # None = icono por defecto según kind
    floor_subtle: bool = False     # marcador pequeño y atenuado en el plano
    floor_color: str | None = None # color en reposo del marcador ("" = por defecto)
    floor_color_on: str | None = None  # color cuando está activo (abierto/disparado)


@dataclass(frozen=True)
class CameraEntity(Entity):
    """Cámara con stream local (go2rtc) y control opcional en la nube (Tuya)."""
    stream_src: str                 # ej. "fija" / "ptz", usado en la URL de go2rtc
    tuya_device_id: str | None = None
    has_ptz: bool = False
    icon: str | None = None         # None = icono por defecto pasado al construir la tarjeta
    floor_top: str | None = None    # posición en % sobre room.png (plano de planta) — None = no se muestra
    floor_left: str | None = None
    floor_icon: str | None = None   # None = icono por defecto (mismo que `icon`)
    floor_subtle: bool = False      # marcador pequeño y atenuado en el plano
    floor_color: str | None = None  # color en reposo del marcador ("" = por defecto)
    floor_color_on: str | None = None  # color cuando está activo (encendida/abierta)


@dataclass(frozen=True)
class CoverEntity(Entity):
    """Persiana/toldo eléctrico. Preparado para cuando se conecte; no usado aún."""
    relay_up: str | None = None     # id de RelayEntity
    relay_down: str | None = None   # id de RelayEntity
    position_sensor: str | None = None  # id de BinarySensorEntity, si lo hay


@dataclass(frozen=True)
class ClimateEntity(Entity):
    """Calefacción/aire acondicionado. Preparado para cuando se conecte; no usado aún."""
    relay: str | None = None        # id de RelayEntity que activa el equipo
    temp_sensor_host: str | None = None  # id de HostEntity/GPIO de donde se lee la temp


@dataclass(frozen=True)
class CardReaderEntity(Entity):
    """Lector de tarjetas/RFID. Preparado para cuando se conecte; no usado aún."""
    mqtt: MQTTSpec
    unlock_relay: str | None = None
