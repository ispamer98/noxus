"""
Despachador SSH genérico: cualquier HostEntity/SSHSpec del registry puede
ejecutar un comando aquí. La Raspberry usa la conexión persistente de
core.ssh_manager (más rápida, ya autenticada); el resto abre una conexión
paramiko puntual.
"""
import os
import asyncio
import paramiko
from ...core.ssh_manager import SSHManager
from .models import SSHSpec

_KEY_PATH = os.path.expanduser("~/.ssh/id_ed25519")


async def ssh_execute(spec: SSHSpec, command: str, timeout: int = 5) -> str:
    if spec.host == os.getenv("IP_RASPBERRY"):
        return await SSHManager.execute_async(command, timeout)
    return await asyncio.to_thread(_ssh_sync, spec.host, spec.user, command, timeout)


def _ssh_sync(host: str, user: str, command: str, timeout: int) -> str:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(hostname=host, username=user, key_filename=_KEY_PATH, timeout=timeout)
        _, stdout, stderr = client.exec_command(command, timeout=timeout)
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        client.close()
        return f"ERROR: {err}" if err else out
    except Exception as e:
        return f"ERROR: {e}"


async def accion_apagar(spec: SSHSpec) -> str:
    cmd = "shutdown /s /t 0 /f" if spec.os == "windows" else "sudo shutdown -h now"
    return await ssh_execute(spec, cmd)


async def accion_reiniciar(spec: SSHSpec) -> str:
    cmd = "shutdown /r /t 0 /f" if spec.os == "windows" else "sudo reboot"
    return await ssh_execute(spec, cmd)


async def accion_temperatura(spec: SSHSpec) -> str:
    if spec.os == "linux":
        temp_str = await ssh_execute(spec, "cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo 0")
        try:
            return f"{int(temp_str.strip()) / 1000.0:.1f} °C"
        except Exception:
            return "No se pudo leer temperatura"
    res = await ssh_execute(
        spec, 'wmic /namespace:\\\\root\\wmi PATH MSAcpi_ThermalZoneTemperature get CurrentTemperature /value 2>nul'
    )
    return res
