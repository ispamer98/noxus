"""
Utilidades de red de bajo nivel que no pertenecen a ningún dominio concreto:
hacer ping a una IP (para saber si un equipo está en línea) y mandar un paquete
mágico de Wake-on-LAN (para encenderlo). Lo usan tanto domains/nodes/
operations.py (el "Encender PC" del catálogo de comandos) como cualquier otro
sitio que necesite preguntar "¿está vivo esto?" sin más contexto.
"""
import asyncio
import platform
import re
from wakeonlan import send_magic_packet


class NetUtils:
    @staticmethod
    async def tcp(host: str, puerto: int, retries: int = 1) -> bool:
        """Conectar a un puerto TCP con 1,5 s de margen; cierra sin enviar nada."""
        for _ in range(max(1, retries)):
            try:
                _, escritor = await asyncio.wait_for(
                    asyncio.open_connection(host, puerto), timeout=1.5)
                escritor.close()
                return True
            except Exception:
                pass
        return False

    @staticmethod
    async def ping(host: str, retries: int = 1) -> bool:
        """Ping rápido: timeout 0.8s, un solo intento por defecto."""
        if not host or host == "0.0.0.0":
            return False
        # «ip:puerto» = comprobar que ese puerto acepta conexión, en vez de ping.
        # Existe por los altavoces Echo: ignoran el ping (ICMP) pero tienen
        # abiertos sus puertos de control (55443…), que es lo que dice si están
        # conectados a la red.
        con_puerto = re.fullmatch(r"([\w.\-]+):(\d{1,5})", host)
        if con_puerto:
            return await NetUtils.tcp(con_puerto.group(1), int(con_puerto.group(2)), retries)
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