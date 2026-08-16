"""
Cliente mínimo para la API cloud de Tuya (firma HMAC-SHA256). Antes esta
lógica de firma estaba copiada dos veces dentro de state.py (move_ptz y
toggle_privacy); aquí vive en un solo sitio.
"""
import time
import json
import hmac
import hashlib
import aiohttp


class TuyaClient:
    def __init__(self, access_id: str, access_secret: str, endpoint: str = "https://openapi.tuyaeu.com"):
        self.access_id = access_id
        self.access_secret = access_secret
        self.endpoint = endpoint

    def _sign(self, method: str, path: str, token: str = "", body: str = "") -> tuple[str, str]:
        ts = str(int(time.time() * 1000))
        content_sha = hashlib.sha256(body.encode()).hexdigest()
        string_to_sign = self.access_id + token + ts + f"{method}\n{content_sha}\n\n{path}"
        signature = hmac.new(self.access_secret.encode(), string_to_sign.encode(), hashlib.sha256).hexdigest().upper()
        return signature, ts

    async def _get_token(self, session: aiohttp.ClientSession) -> str:
        path = "/v1.0/token?grant_type=1"
        sign, ts = self._sign("GET", path)
        headers = {"client_id": self.access_id, "sign": sign, "t": ts, "sign_method": "HMAC-SHA256"}
        async with session.get(self.endpoint + path, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as r:
            data = await r.json()
            if not data.get("success"):
                raise RuntimeError(data.get("msg", "Error obteniendo token Tuya"))
            return data["result"]["access_token"]

    async def send_commands(self, device_id: str, commands: list[dict]) -> dict:
        path = f"/v1.0/devices/{device_id}/commands"
        body = json.dumps({"commands": commands})
        async with aiohttp.ClientSession() as s:
            token = await self._get_token(s)
            sign, ts = self._sign("POST", path, token, body)
            headers = {
                "client_id": self.access_id, "access_token": token, "sign": sign, "t": ts,
                "sign_method": "HMAC-SHA256", "Content-Type": "application/json",
            }
            async with s.post(self.endpoint + path, headers=headers, data=body,
                               timeout=aiohttp.ClientTimeout(total=5)) as r:
                return await r.json()

    async def set_shadow_properties(self, device_id: str, properties: dict) -> dict:
        path = f"/v2.0/cloud/thing/{device_id}/shadow/properties/issue"
        body = json.dumps(properties)
        async with aiohttp.ClientSession() as s:
            token = await self._get_token(s)
            sign, ts = self._sign("POST", path, token, body)
            headers = {
                "client_id": self.access_id, "access_token": token, "sign": sign, "t": ts,
                "sign_method": "HMAC-SHA256", "Content-Type": "application/json",
            }
            async with s.post(self.endpoint + path, headers=headers, data=body,
                               timeout=aiohttp.ClientTimeout(total=5)) as r:
                return await r.json()
