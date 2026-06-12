import asyncio
from .ssh_manager import SSHManager


class Sensors:
    @staticmethod
    async def get_cpu_temp_async() -> float:
        """Temperatura de la RPi VPN vía SSH (asíncrono)."""
        try:
            temp_str = await SSHManager.execute_async(
                "cat /sys/class/thermal/thermal_zone0/temp", timeout=2
            )
            if temp_str and not temp_str.startswith("ERROR"):
                return int(temp_str) / 1000.0
        except Exception:
            pass
        return 0.0