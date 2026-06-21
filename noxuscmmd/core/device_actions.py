"""
device_actions.py
-----------------
Funciones específicas por equipo.
Todas las acciones SSH, GPIO, RDP, fotos, etc.
Se usan desde los métodos del State para mantener éste limpio.
"""

import os
import asyncio
import subprocess
import paramiko
from datetime import datetime
from dotenv import load_dotenv
from .ssh_manager import SSHManager
from .connectivity import NetUtils

load_dotenv()

# ══════════════════════════════════════════════════════════════════════
# Helpers genéricos SSH
# ══════════════════════════════════════════════════════════════════════

async def ssh_execute(host: str, user: str, command: str, timeout: int = 5) -> str:
    """Ejecuta comando SSH. Si el host es la Raspberry, usa la conexión persistente."""
    if host == os.getenv("IP_RASPBERRY"):
        return await SSHManager.execute_async(command, timeout)
    else:
        return await asyncio.to_thread(ssh_sync, host, user, command, timeout)

def ssh_sync(host: str, user: str, command: str, timeout: int) -> str:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    key_path = os.path.expanduser("~/.ssh/id_ed25519")
    try:
        client.connect(hostname=host, username=user, key_filename=key_path, timeout=timeout)
        _, stdout, stderr = client.exec_command(command, timeout=timeout)
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        client.close()
        if err:
            return f"ERROR: {err}"
        return out
    except Exception as e:
        return f"ERROR: {e}"

# ══════════════════════════════════════════════════════════════════════
# Acciones genéricas por SO
# ══════════════════════════════════════════════════════════════════════

async def accion_apagar(host: str, user: str, os_type: str) -> str:
    if os_type == "windows":
        cmd = "shutdown /s /t 0 /f"
    else:
        cmd = "sudo shutdown -h now"
    return await ssh_execute(host, user, cmd)

async def accion_reiniciar(host: str, user: str, os_type: str) -> str:
    if os_type == "windows":
        cmd = "shutdown /r /t 0 /f"
    else:
        cmd = "sudo reboot"
    return await ssh_execute(host, user, cmd)

async def accion_temperatura(host: str, user: str, os_type: str) -> str:
    if os_type == "linux":
        temp_str = await ssh_execute(host, user,
            "cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo 0")
        try:
            temp = int(temp_str.strip()) / 1000.0
            return f"{temp:.1f} °C"
        except:
            return "No se pudo leer temperatura"
    else:
        # Windows: intentar wmic (poco fiable)
        res = await ssh_execute(host, user,
            'wmic /namespace:\\\\root\\wmi PATH MSAcpi_ThermalZoneTemperature get CurrentTemperature /value 2>nul')
        return res

# ══════════════════════════════════════════════════════════════════════
# Acciones específicas por dispositivo
# ══════════════════════════════════════════════════════════════════════

# --- Raspberry Pi (principal) ---

async def raspberry_gpio_set(pin: str, state: str):
    """Activar/desactivar un pin GPIO (dh/dl)."""
    val = "dh" if state == "on" else "dl"
    cmd = f"raspi-gpio set {pin} op {val}"
    await SSHManager.execute_async(cmd, timeout=2)

async def raspberry_gpio_17_test():
    """Test de ventilador: ON 5 segundos (GPIO17)."""
    await SSHManager.execute_async("raspi-gpio set 17 op dh", timeout=3)
    await asyncio.sleep(5)
    await SSHManager.execute_async("raspi-gpio set 17 op dl", timeout=3)

def raspberry_rdp():
    subprocess.Popen(["/bin/bash", "/home/spamer/pc_to_raspberry.sh"])

# --- PC (Windows) ---

def pc_wol():
    NetUtils.send_wol(os.getenv("PC_MAC"))

def pc_rdp():
    subprocess.Popen(["/bin/bash", "/home/spamer/portatil_to_pc.sh"])

# --- Portátil (Windows) ---

def portatil_rdp():
    subprocess.Popen(["/bin/bash", "/home/spamer/pc_to_portatil.sh"])

# --- Pi Zero ---

async def pizero_tomar_foto():
    """Devuelve bytes de la foto."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(os.getenv("IP_PI_ZERO"), username=os.getenv("ZERO_USER"),
                key_filename=os.path.expanduser("~/.ssh/id_ed25519"), timeout=5)
    carpeta = "/home/zero/Desktop/Snapshoots"
    nombre  = datetime.now().strftime("%d-%m-%Y_%H%M%S") + ".jpg"
    ruta    = f"{carpeta}/{nombre}"
    _, stdout, _ = ssh.exec_command(f"rpicam-still -o {ruta} -t 800 && echo OK")
    stdout.channel.recv_exit_status()
    sftp = ssh.open_sftp()
    with sftp.file(ruta, "rb") as f: data = f.read()
    sftp.close(); ssh.close()
    return data
