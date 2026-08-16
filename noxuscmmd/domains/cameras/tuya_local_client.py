"""
Control LOCAL (LAN) de dispositivos Tuya via tinytuya — no depende de la
suscripción "IoT Core" del cloud de Tuya (openapi.tuyaeu.com), que es la que
caduca a los 6 meses. Solo necesita, por dispositivo: IP local, device_id y
local_key (se sacan una vez con `python -m tinytuya wizard`, ver README de
esta función más abajo).

tinytuya habla en DPs (data points) numéricos, no en los "code" de texto que
usa la API cloud (ptz_control, basic_private...) — cada modelo de cámara
mapea sus funciones a índices DP distintos, así que los índices son
configurables por variable de entorno en vez de estar fijos en el código.
"""
import asyncio
import tinytuya


class TuyaLocalClient:
    def __init__(self, device_id: str, ip: str, local_key: str, version: float = 3.3):
        self.device_id = device_id
        self.ip = ip
        self.local_key = local_key
        self.version = version

    def _device(self) -> "tinytuya.Device":
        d = tinytuya.Device(self.device_id, self.ip, self.local_key, version=self.version)
        d.set_socketTimeout(3)
        return d

    def _send_dps_sync(self, dps: dict) -> dict:
        d = self._device()
        try:
            return d.set_multiple_values(dps, nowait=False)
        finally:
            d.close()

    def _status_sync(self) -> dict:
        d = self._device()
        try:
            return d.status()
        finally:
            d.close()

    async def send_dps(self, dps: dict) -> dict:
        """dps = {"1": True, "2": 5} — índice DP (como string) -> valor."""
        return await asyncio.to_thread(self._send_dps_sync, dps)

    async def status(self) -> dict:
        """Útil para descubrir qué DP cambia al mover algo desde la app Tuya
        (compara el resultado antes/después de tocar un control)."""
        return await asyncio.to_thread(self._status_sync)
