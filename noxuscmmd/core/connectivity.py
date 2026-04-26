import asyncio
import platform
from wakeonlan import send_magic_packet

class NetUtils:
    @staticmethod
    async def ping(host: str, retries: int = 1) -> bool:
        param = "-n" if platform.system().lower() == "windows" else "-c"
        timeout = "-w" if platform.system().lower() == "windows" else "-W"
        for _ in range(retries):
            proc = await asyncio.create_subprocess_exec(
                "ping", param, "1", timeout, "1", host,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
            )
            await proc.wait()
            if proc.returncode == 0: return True
        return False

    @staticmethod
    def send_wol(mac: str):
        send_magic_packet(mac)