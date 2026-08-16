"""Streams de cámara (go2rtc), control PTZ y modo privacidad (Tuya cloud)."""
import os
import asyncio
import reflex as rx
import aiohttp

from ..devices import registry
from ..infra.state import InfraState
from ..security import audit, logs
from .tuya_client import TuyaClient
from .tuya_local_client import TuyaLocalClient

_MOVE_MAP = {"0": "up", "4": "down", "6": "left", "2": "right", "stop": "stop"}

# go2rtc negocia el modo él solo probando esta lista en orden y cae al
# siguiente si el anterior falla. Antes, en "modo mobile", se metía la URL
# cruda del manifiesto HLS (api/stream.m3u8) directamente como src de un
# <iframe> — un iframe carga documentos HTML, no manifiestos de vídeo, así
# que en navegadores sin HLS nativo (Chrome/Android) salía en blanco, y en
# los que sí lo tienen (Safari/iOS) faltaba el reproductor propio y las
# políticas de autoplay exigían pulsar play a mano. Se mantiene siempre la
# página stream.html (nunca la URL cruda), pero el ORDEN de negociación sí
# cambia según el modo: en PC se prioriza WebRTC (menor latencia); en móvil
# se evita como primera opción porque en redes celulares/VPN falla más a
# menudo el intercambio de candidatos ICE, así que se prioriza MSE/HLS.
_STREAM_MODES_PC = "webrtc,mse,hls,mp4"
_STREAM_MODES_MOBILE = "mse,hls,mp4"


def _tuya_client() -> TuyaClient | None:
    t_id = os.getenv("TUYA_ACCESS_ID")
    t_secret = os.getenv("TUYA_ACCESS_SECRET")
    if not t_id or not t_secret:
        return None
    return TuyaClient(t_id, t_secret)


def _cam_suffix(cam_entity_id: str) -> str:
    """cam_fija -> FIJA, cam_ptz -> PTZ — para leer las variables de entorno
    TUYA_LOCAL_IP_<suffix>/TUYA_LOCAL_KEY_<suffix>/TUYA_DP_*_<suffix>."""
    return cam_entity_id.replace("cam_", "").upper()


def _tuya_local_client(cam_entity_id: str) -> TuyaLocalClient | None:
    """Control LAN directo (tinytuya) — no depende de la suscripción cloud de
    Tuya. Requiere TUYA_LOCAL_IP_<CAM> y TUYA_LOCAL_KEY_<CAM> en el .env
    (se obtienen una vez con `python -m tinytuya wizard`, ver domains/cameras
    /tuya_local_client.py). El device_id ya existe en el registry."""
    suffix = _cam_suffix(cam_entity_id)
    ip = os.getenv(f"TUYA_LOCAL_IP_{suffix}")
    key = os.getenv(f"TUYA_LOCAL_KEY_{suffix}")
    dev_id = getattr(registry.DEVICES.get(cam_entity_id), "tuya_device_id", None)
    if not ip or not key or not dev_id:
        return None
    return TuyaLocalClient(dev_id, ip, key)


class CameraState(rx.State):
    cam_mode: str = "pc"
    show_fija_stream: bool = False
    show_ptz_stream: bool = False
    cam_msg: str = "Vídeo: Listo"

    @rx.var
    def url_fija_stream(self) -> str:
        modes = _STREAM_MODES_MOBILE if self.cam_mode == "mobile" else _STREAM_MODES_PC
        return f"https://cam.noxuscmmd.uk/stream.html?src=fija&mode={modes}"

    @rx.var
    def url_ptz_stream(self) -> str:
        modes = _STREAM_MODES_MOBILE if self.cam_mode == "mobile" else _STREAM_MODES_PC
        return f"https://cam.noxuscmmd.uk/stream.html?src=ptz&mode={modes}"

    def toggle_fija_stream(self):
        self.show_fija_stream = not self.show_fija_stream

    def toggle_ptz_stream(self):
        self.show_ptz_stream = not self.show_ptz_stream

    @rx.event
    async def toggle_cam_mode(self):
        self.cam_mode = "mobile" if self.cam_mode == "pc" else "pc"
        infra = await self.get_state(InfraState)
        infra.status = f"📷 Modo: {self.cam_mode.upper()}"

    async def _log(self, accion: str, detalle: str = "") -> None:
        """Llamar SIEMPRE dentro de un `async with self:` — todo lo de aquí son
        tareas de fondo, y el State de la sesión solo se puede pedir ahí."""
        await audit.registrar(self, logs.CCTV, accion, detalle)

    @staticmethod
    def _nombre_camara(cam_entity_id: str) -> str:
        entidad = registry.DEVICES.get(cam_entity_id)
        return getattr(entidad, "name", None) or cam_entity_id

    async def _set_result(self, cam_msg: str, infra_status: str):
        """Actualiza cam_msg (self) y status (InfraState) en un único bloque
        bloqueado — patrón obligatorio para mutar estado desde background tasks."""
        async with self:
            self.cam_msg = cam_msg
            infra = await self.get_state(InfraState)
            infra.status = infra_status

    # ── Control PTZ: go2rtc local -> Tuya LAN (tinytuya) -> Tuya cloud ────
    @rx.event(background=True)
    async def move_ptz(self, direction: str):
        move = _MOVE_MAP.get(direction, "stop")
        try:
            go2rtc_url = f"http://{os.getenv('IP_RASPBERRY', '100.76.90.7')}:1984/api/ptz"
            async with aiohttp.ClientSession() as s:
                async with s.get(go2rtc_url, params={"move": move}, timeout=2) as r:
                    if r.status == 200:
                        await self._set_result(f"✅ PTZ {move}", f"✅ PTZ {move}")
                        return
        except Exception as e:
            print(f"⚠️ Error en go2rtc: {e}, intentando Tuya local...")

        local = _tuya_local_client("cam_ptz")
        dp_ptz = os.getenv("TUYA_DP_PTZ")
        if local and dp_ptz:
            try:
                await local.send_dps({dp_ptz: direction})
                await self._set_result(f"✅ PTZ {direction} (local)", f"✅ PTZ {direction} (local)")
                return
            except Exception as e:
                print(f"⚠️ Error en Tuya local: {e}, intentando Tuya cloud...")

        client = _tuya_client()
        dev_id = getattr(registry.DEVICES.get("cam_ptz"), "tuya_device_id", None)
        if not client or not dev_id:
            await self._set_result("❌ Faltan credenciales Tuya (local y cloud)", "❌ Faltan credenciales Tuya")
            return

        try:
            result = await client.send_commands(dev_id, [{"code": "ptz_control", "value": direction}])
            if result.get("success"):
                await self._set_result(f"✅ PTZ {direction}", f"✅ PTZ {direction}")
                await asyncio.sleep(0.2)
                await client.send_commands(dev_id, [{"code": "ptz_stop", "value": True}])
            else:
                msg = f"❌ Error: {result.get('msg')}"
                await self._set_result(msg, msg)
        except Exception as e:
            msg = f"❌ Error: {str(e)[:60]}"
            await self._set_result(msg, msg)

    # ── Modo privacidad: Tuya LAN primero, Tuya cloud como fallback ──────
    @rx.event(background=True)
    async def toggle_privacy(self, cam_entity_id: str, enable: bool):
        local = _tuya_local_client(cam_entity_id)
        dp_privacy = os.getenv(f"TUYA_DP_PRIVACY_{_cam_suffix(cam_entity_id)}")
        if local and dp_privacy:
            try:
                await local.send_dps({dp_privacy: enable})
                async with self:
                    infra = await self.get_state(InfraState)
                    infra.status = f"🔒 Privacidad {'ACTIVADA' if enable else 'DESACTIVADA'} (local)"
                    await self._log("CAMARA_PRIVACIDAD_ON" if enable else "CAMARA_PRIVACIDAD_OFF",
                                    f"{self._nombre_camara(cam_entity_id)} (Tuya local)")
                return
            except Exception as e:
                print(f"⚠️ Error en Tuya local: {e}, intentando Tuya cloud...")

        client = _tuya_client()
        device_id = getattr(registry.DEVICES.get(cam_entity_id), "tuya_device_id", None)
        if not client or not device_id:
            async with self:
                infra = await self.get_state(InfraState)
                infra.status = "❌ Faltan credenciales Tuya (local y cloud)"
            return
        try:
            result = await client.set_shadow_properties(device_id, {"basic_private": enable})
            if result.get("success"):
                status = f"🔒 Privacidad {'ACTIVADA' if enable else 'DESACTIVADA'}"
            else:
                status = f"❌ Error: {result.get('msg', 'desconocido')}"
        except Exception as e:
            status = f"❌ Error: {str(e)[:60]}"
        async with self:
            infra = await self.get_state(InfraState)
            infra.status = status
            await self._log("CAMARA_PRIVACIDAD_ON" if enable else "CAMARA_PRIVACIDAD_OFF",
                            f"{self._nombre_camara(cam_entity_id)} (Tuya cloud) — {status}")

    # ── Sirena de la cámara (solo Tuya LAN — no hay equivalente cloud aquí) ──
    @rx.event(background=True)
    async def trigger_siren(self, cam_entity_id: str):
        local = _tuya_local_client(cam_entity_id)
        dp_siren = os.getenv(f"TUYA_DP_SIREN_{_cam_suffix(cam_entity_id)}")
        if not local or not dp_siren:
            await self._set_result(
                "❌ Sirena no configurada (TUYA_LOCAL_IP/KEY/DP_SIREN)",
                "❌ Sirena no configurada",
            )
            return
        try:
            await local.send_dps({dp_siren: True})
            await self._set_result("🔊 Sirena activada", "🔊 Sirena activada")
            async with self:
                await self._log("CAMARA_SIRENA", self._nombre_camara(cam_entity_id))
            await asyncio.sleep(3)
            await local.send_dps({dp_siren: False})
        except Exception as e:
            msg = f"❌ Sirena: {str(e)[:60]}"
            await self._set_result(msg, msg)
