"""
Acciones puntuales por dispositivo que no encajan en el modelo genérico
(lanzar un script local, Wake-on-LAN, sacar una foto por SFTP...).
"""
import os
import paramiko
from datetime import datetime
from ...core.connectivity import NetUtils
from . import registry, gpio_bus

_KEY_PATH = os.path.expanduser("~/.ssh/id_ed25519")


def pc_wol():
    NetUtils.send_wol(registry.DEVICES["pc"].mac)


# El escritorio remoto ya no vive aquí: estas tres funciones lanzaban un
# cliente RDP en el propio servidor con unos scripts que ya no existen. Ahora
# se genera un .rdp y se descarga en el navegador de quien pulsa el botón —
# ver domains/nodes/rdp.py.


async def gpio_17_test():
    """Test de ventilador: ON 5 segundos."""
    await gpio_bus.pulse_relay(registry.get_relay("ventilador"), seconds=5.0)


async def pizero_tomar_foto() -> bytes:
    """Devuelve los bytes de una foto capturada por la Pi Zero (SFTP)."""
    pi_zero = registry.DEVICES["pi_zero"].ssh
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(pi_zero.host, username=pi_zero.user, key_filename=_KEY_PATH, timeout=5)
    carpeta = "/home/zero/Desktop/Snapshoots"
    nombre = datetime.now().strftime("%d-%m-%Y_%H%M%S") + ".jpg"
    ruta = f"{carpeta}/{nombre}"
    _, stdout, _ = ssh.exec_command(f"rpicam-still -o {ruta} -t 800 && echo OK")
    stdout.channel.recv_exit_status()
    sftp = ssh.open_sftp()
    with sftp.file(ruta, "rb") as f:
        data = f.read()
    sftp.close()
    ssh.close()
    return data
