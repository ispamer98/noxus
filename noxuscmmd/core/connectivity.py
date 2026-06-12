import asyncio
import platform
from wakeonlan import send_magic_packet


class NetUtils:
    @staticmethod
    async def ping(host: str, retries: int = 1) -> bool:
        """Ping rápido: timeout 0.8s, un solo intento por defecto."""
        if not host or host == "0.0.0.0":
            return False
        param = "-n" if platform.system().lower() == "windows" else "-c"
        w_flag = "-w" if platform.system().lower() == "windows" else "-W"
        # En Linux -W acepta segundos; usamos 1 (mínimo)
        for _ in range(retries):
            try:
                proc = await asyncio.create_subprocess_exec(
                    "ping", param, "1", w_flag, "1", host,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                try:
                    await asyncio.wait_for(proc.wait(), timeout=1.5)
                except asyncio.TimeoutError:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    continue
                if proc.returncode == 0:
                    return True
            except Exception:
                pass
        return False

    @staticmethod
    async def ping_all(hosts: list[tuple[str, int]]) -> list[bool]:
        """Lanza todos los pings en paralelo y devuelve resultados en orden.
        hosts = [(ip, retries), ...]
        """
        tasks = [NetUtils.ping(h, r) for h, r in hosts]
        return list(await asyncio.gather(*tasks, return_exceptions=False))

    @staticmethod
    def send_wol(mac: str):
        if mac:
            send_magic_packet(mac)