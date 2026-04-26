import os
import asyncio
import subprocess
import base64
import json
import paramiko
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import reflex as rx
from pywebpush import webpush, WebPushException
import RPi.GPIO as GPIO

from .core.connectivity import NetUtils
from .core.ssh_manager import SSHManager
from .core.sensors import Sensors
import time



load_dotenv()

VAPID_PRIVATE = os.getenv("VAPID_PRIVATE_KEY")
VAPID_PUBLIC = os.getenv("VAPID_PUBLIC_KEY")
VAPID_EMAIL = os.getenv("VAPID_EMAIL", "mailto:admin@noxuscmmd.uk")

# Variables globales para persistencia total
SISTEMA_ARMADO_GLOBAL = False
PUERTA_ABIERTA_GLOBAL = False
NOTIFICACION_ENVIADA_GLOBAL = False  # <--- Nueva: evita el spam de notificaciones

class State(rx.State):
    raspberry_online: bool = False
    iphone_online: bool = False
    pc_online: bool = False
    portatil_online: bool = False
    pi_zero_online: bool = False
    status: str = "Esperando..."
    temperaturas: list[str] = []
    last_rpi_photo: str = ""
    dialog_foto_abierto: bool = False
    uploaded_files: list[str] = []
    cam_ptz_online: bool = False
    cam_fija_online: bool = False
    cam_msg: str = "Vídeo: Listo"
    
    # Estas variables ahora seguirán al estado Global
    sistema_armado: bool = False
    puerta_abierta: bool = False
    
    iphone_confirmaciones: int = 0  
    rpi_confirmaciones: int = 0
    pc_confirmaciones: int = 0
    portatil_confirmaciones: int = 0
    zero_confirmaciones: int = 0
    ptz_confirmaciones: int = 0
    fija_confirmaciones: int = 0

    is_first_run: bool = True
    alarma_hilo_corriendo: bool = False
    ver_fija: bool = False

    @rx.var
    def url_snapshot_fija(self) -> str:
        # La mayoría de cámaras tienen una URL tipo /snapshot.jpg o /jpg/image.jpg
        # Al añadir el timestamp, obligamos al navegador a refrescar la imagen
        return f"http://192.168.1.52/snapshot.jpg?time={time.time()}"

    def toggle_fija(self):
        self.ver_fija = not self.ver_fija
    @rx.event
    def on_load(self):
        return State.vigilar_puerta_task

    @rx.event
    def conmutar_alarma(self):
        global SISTEMA_ARMADO_GLOBAL
        # Cambiamos el estado en el "cerebro" global del servidor
        SISTEMA_ARMADO_GLOBAL = not SISTEMA_ARMADO_GLOBAL
        # Sincronizamos la UI local inmediatamente
        self.sistema_armado = SISTEMA_ARMADO_GLOBAL
        
        if self.sistema_armado:
            self.status = "🔒 Sistema de Seguridad: ARMADO"
        else:
            self.status = "🔓 Sistema de Seguridad: DESARMADO"

    @rx.event(background=True)
    async def vigilar_puerta_task(self):
        global SISTEMA_ARMADO_GLOBAL, PUERTA_ABIERTA_GLOBAL, NOTIFICACION_ENVIADA_GLOBAL
        
        # Evitar que se creen múltiples bucles si hay varias pestañas abiertas
        async with self:
            if self.alarma_hilo_corriendo:
                return 
            self.alarma_hilo_corriendo = True

        # Configuración inicial del GPIO
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(18, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        except: 
            pass

        while True:
            # 1. Lectura física del sensor
            lectura_fisica = GPIO.input(18) == GPIO.HIGH
            PUERTA_ABIERTA_GLOBAL = lectura_fisica

            # 2. Lógica de Notificación Inteligente
            if SISTEMA_ARMADO_GLOBAL and PUERTA_ABIERTA_GLOBAL:
                if not NOTIFICACION_ENVIADA_GLOBAL:
                    # DISPARO ÚNICO: Aquí puedes poner "todos" o el nombre de un usuario
                    self.enviar_notificacion(
                        "🚨 ALERTA: INTRUSIÓN", 
                        "La puerta ha sido abierta con el sistema ARMADO.",
                        destino="todos" 
                    )
                    NOTIFICACION_ENVIADA_GLOBAL = True 
            
            # 3. Resetear el aviso cuando la puerta se cierra
            if not PUERTA_ABIERTA_GLOBAL:
                NOTIFICACION_ENVIADA_GLOBAL = False

            # 4. Sincronizar la interfaz visual de la sesión actual
            async with self:
                self.sistema_armado = SISTEMA_ARMADO_GLOBAL
                self.puerta_abierta = PUERTA_ABIERTA_GLOBAL

            await asyncio.sleep(0.5)
    
    @rx.event
    def lanzar_alerta_global(self):
        self.enviar_notificacion("🆘 ALERTA MANUAL", "Se ha activado el botón de pánico desde el panel de control.")
        self.status = "🆘 Alerta Global Enviada"

    @rx.event
    def guardar_subscripcion(self, js_result: str):
        # Cancelación del usuario
        if js_result == "USER_CANCEL":
            self.status = "Registro cancelado"
            return  # No hacemos nada

        if not js_result or "ERROR" in js_result or js_result == "PERMISO_DENEGADO":
            self.status = f"❌ Push: {js_result}"
            return rx.window_alert(f"Error en notificaciones: {js_result}")

        try:
            data = json.loads(js_result)
            sub_dict = data.get("subscription")
            nombre_usuario = data.get("nombre", "").strip()

            # Rechazar si el nombre sigue vacío después del trim
            if not nombre_usuario:
                self.status = "❌ Nombre inválido o vacío"
                return rx.window_alert("Debe proporcionar un nombre para el dispositivo.")

            archivo = "suscriptores.json"
            subs = []
            existe_endpoint = False
            existe_nombre = False
            endpoint_duplicado = None

            # Cargar suscriptores existentes
            if os.path.exists(archivo):
                with open(archivo, "r") as f:
                    try:
                        subs = json.loads(f.read())
                    except:
                        subs = []

            # Verificar duplicados
            for s in subs:
                if s.get("endpoint") == sub_dict.get("endpoint"):
                    existe_endpoint = True
                    endpoint_duplicado = s
                    break
                if s.get("nombre_usuario") == nombre_usuario:
                    existe_nombre = True

            # Si el endpoint ya existe, actualizar el nombre si es diferente
            if existe_endpoint:
                if endpoint_duplicado.get("nombre_usuario") != nombre_usuario:
                    endpoint_duplicado["nombre_usuario"] = nombre_usuario
                    with open(archivo, "w") as f:
                        json.dump(subs, f, indent=4)
                    self.status = f"🔄 Nombre actualizado a '{nombre_usuario}' para este dispositivo"
                    return rx.window_alert(f"✅ Dispositivo actualizado con el nombre '{nombre_usuario}'")
                else:
                    self.status = "ℹ️ Este dispositivo ya está registrado con el mismo nombre"
                    return rx.window_alert("Este dispositivo ya estaba registrado correctamente.")

            # Si el nombre ya existe en otro dispositivo, rechazar
            if existe_nombre:
                self.status = f"❌ El nombre '{nombre_usuario}' ya está en uso por otro dispositivo"
                return rx.window_alert(f"El nombre '{nombre_usuario}' ya está registrado. Por favor, elige otro nombre.")

            # Nuevo dispositivo: agregar
            sub_dict["nombre_usuario"] = nombre_usuario
            subs.append(sub_dict)
            with open(archivo, "w") as f:
                json.dump(subs, f, indent=4)

            self.status = f"🔔 Vinculado como '{nombre_usuario}'"
            return rx.window_alert(f"✅ ¡Dispositivo '{nombre_usuario}' vinculado con éxito!")

        except Exception as e:
            print(f"Error al guardar suscripción: {e}")
            self.status = "❌ Error al vincular"
            return rx.window_alert("Ocurrió un error inesperado al guardar la suscripción.")

    def enviar_notificacion(self, titulo: str, mensaje: str, destino: str = "todos"):
        """Envía notificaciones. destino puede ser 'todos' o el 'nombre_usuario' guardado."""
        archivo = "suscriptores.json"
        if not os.path.exists(archivo):
            return

        try:
            with open(archivo, "r") as f:
                subs = json.loads(f.read())
            
            payload = json.dumps({
                "title": titulo, 
                "body": mensaje,
                "icon": "/icono.png",
                "badge": "/icono.png"
            })

            for sub in subs:
                # FILTRO DE NOMBRE: Si pedimos uno específico y no coincide, saltamos al siguiente
                if destino != "todos" and sub.get("nombre_usuario") != destino:
                    continue

                try:
                    webpush(
                        subscription_info=sub,
                        data=payload,
                        vapid_private_key=VAPID_PRIVATE,
                        vapid_claims={"sub": VAPID_EMAIL},
                        timeout=5
                    )
                    print(f"✅ Notificación enviada a: {sub.get('nombre_usuario', 'Desconocido')}")
                except WebPushException as ex:
                    print(f"❌ Error enviando a {sub.get('nombre_usuario')}: {ex}")
                except Exception as e:
                    print(f"⚠️ Error inesperado: {e}")
                        
        except Exception as e:
            print(f"Error general en el sistema de envío: {e}")
    @rx.event(background=True)
    async def actualizar_estados(self):
        # Mantenemos tu lógica de pings igual
        res = await asyncio.gather(
            NetUtils.ping(os.getenv("IP_RASPBERRY", "0.0.0.0")),
            NetUtils.ping(os.getenv("IP_IPHONE", "0.0.0.0"), 3),
            NetUtils.ping(os.getenv("IP_PC", "0.0.0.0")),
            NetUtils.ping(os.getenv("IP_PORTATIL", "0.0.0.0")),
            NetUtils.ping(os.getenv("IP_PI_ZERO", "0.0.0.0"), 3),
            NetUtils.ping(os.getenv("IP_CAM_PTZ", "0.0.0.0")),
            NetUtils.ping(os.getenv("IP_CAM_FIJA", "0.0.0.0"))
        )
        rpi_r, iphone_r, pc_r, port_r, zero_r, ptz_r, fija_r = res
        async with self:
            equipos = [
                ("Raspberry", rpi_r, "raspberry_online", "rpi_confirmaciones"),
                ("iPhone", iphone_r, "iphone_online", "iphone_confirmaciones"),
                ("PC", pc_r, "pc_online", "pc_confirmaciones"),
                ("Portátil", port_r, "portatil_online", "portatil_confirmaciones"),
                ("Pi Zero", zero_r, "pi_zero_online", "zero_confirmaciones"),
                ("Cámara PTZ", ptz_r, "cam_ptz_online", "ptz_confirmaciones"),
                ("Cámara Fija", fija_r, "cam_fija_online", "fija_confirmaciones"),
            ]
            for nombre, ping_ahora, v_online, v_count in equipos:
                setattr(self, v_online, ping_ahora)
                # Simplificado para evitar más variables de notificación innecesarias
                if not ping_ahora and getattr(self, v_count) == 0:
                     setattr(self, v_count, 1)
                     # Aquí podrías re-añadir la notificación si lo deseas
            self.is_first_run = False

    @rx.var
    def url_fija_embed(self) -> str:
        return f"http://{os.getenv('IP_RASPBERRY', '0.0.0.0')}:1984/webrtc.html?src=fija"

    @rx.var
    def url_ptz_embed(self) -> str:
        return f"http://{os.getenv('IP_RASPBERRY', '0.0.0.0')}:1984/webrtc.html?src=ptz"

    def move_ptz(self, direction: str):
        import requests, time, hmac, hashlib
        t_id, t_secret = os.getenv("TUYA_ACCESS_ID"), os.getenv("TUYA_ACCESS_SECRET")
        dev_id, endpoint = os.getenv("ID_PTZ_TUYA"), "https://openapi.tuyaeu.com"
        def get_sign(method, path, token="", body=""):
            t = str(int(time.time() * 1000))
            content_sha256 = hashlib.sha256(body.encode('utf-8')).hexdigest()
            string_to_sign = f"{method}\n{content_sha256}\n\n{path}"
            sign_payload = t_id + token + t + string_to_sign
            return hmac.new(t_secret.encode('utf-8'), sign_payload.encode('utf-8'), hashlib.sha256).hexdigest().upper(), t
        try:
            t_path = "/v1.0/token?grant_type=1"
            sign, t = get_sign("GET", t_path)
            res_t = requests.get(endpoint + t_path, headers={'client_id': t_id, 'sign': sign, 't': t, 'sign_method': 'HMAC-SHA256'}).json()
            token = res_t.get("result", {}).get("access_token")
            cmd_path = f"/v1.0/devices/{dev_id}/commands"
            body_move = json.dumps({"commands": [{"code": "ptz_control", "value": direction}]})
            sign_m, t_m = get_sign("POST", cmd_path, token, body_move)
            requests.post(endpoint+cmd_path, headers={'client_id':t_id,'access_token':token,'sign':sign_m,'t':t_m,'sign_method':'HMAC-SHA256','Content-Type':'application/json'}, data=body_move)
            time.sleep(0.2)
            body_stop = json.dumps({"commands": [{"code": "ptz_stop", "value": True}]})
            sign_s, t_s = get_sign("POST", cmd_path, token, body_stop)
            requests.post(endpoint+cmd_path, headers={'client_id':t_id,'access_token':token,'sign':sign_s,'t':t_s,'sign_method':'HMAC-SHA256','Content-Type':'application/json'}, data=body_stop)
            self.cam_msg = f"✅ Movimiento {direction}"
        except Exception as e: self.cam_msg = f"❌ Error: {str(e)}"

    def _run_sh(self, name):
        p = f"/home/vpn/{name}.sh"
        if os.path.exists(p):
            subprocess.Popen(["/bin/bash", p])
            self.status = f"Ejecutando {name}..."
        else: self.status = f"Falta {name}.sh"

    def rdp_pc(self): self._run_sh("portatil_to_pc")
    def rdp_portatil(self): self._run_sh("pc_to_portatil")
    def rdp_raspberry(self): self._run_sh("pc_to_raspberry")
    def wake_pc(self): 
        NetUtils.send_wol(os.getenv("PC_MAC"))
        self.status = "WOL Enviado"
    def apagar_pc(self):
        cmd = f'ssh -o StrictHostKeyChecking=no {os.getenv("PC_USER")}@{os.getenv("IP_PC")} "shutdown /s /t 0 /f"'
        subprocess.run(cmd, shell=True)
    def restart_raspberry(self): self._run_sh("restart_raspberry")

    def gpio_17(self):
        if not self.pi_zero_online:
            self.status = "❌ Pi Zero OFFLINE"
            return
        cmd = "raspi-gpio set 17 op dh && sleep 4 && raspi-gpio set 17 op dl"
        res = SSHManager.execute(cmd, os.getenv("IP_PI_ZERO"), os.getenv("ZERO_USER"), os.getenv("ZERO_PASS"))
        self.status = "🚪 GPIO 17 activado"

    @rx.event(background=True)
    async def tomar_foto_raspberry(self):
        async with self:
            if not self.pi_zero_online:
                self.status = "❌ Pi Zero OFFLINE"
                return
            self.status = "📸 Conectando..."
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(os.getenv("IP_PI_ZERO"), username=os.getenv("ZERO_USER"), password=os.getenv("ZERO_PASS"), timeout=5)
            carpeta = "/home/zero/Desktop/Snapshoots"
            fecha_str = datetime.now().strftime("%d-%m-%Y_%H%M%S")
            nombre_foto = f"{fecha_str}.jpg"
            ssh.exec_command(f'rpicam-still -o {carpeta}/{nombre_foto} -t 1000')
            await asyncio.sleep(2)
            sftp = ssh.open_sftp()
            with sftp.file(f"{carpeta}/{nombre_foto}", "rb") as f: foto_bytes = f.read()
            sftp.close()
            ssh.close()
            foto_b64 = base64.b64encode(foto_bytes).decode()
            async with self:
                self.last_rpi_photo = f"data:image/jpeg;base64,{foto_b64}"
                self.dialog_foto_abierto = True
                self.status = "✅ Foto capturada"
        except Exception as e:
            async with self: self.status = f"❌ Error foto: {e}"

    def toggle_dialog(self): self.dialog_foto_abierto = not self.dialog_foto_abierto

    @rx.event(background=True)
    async def medir_temperatura(self):
        async with self: self.temperaturas = []
        for i in range(3):
            t = Sensors.get_cpu_temp()
            async with self: self.temperaturas.append(f"🌡️ {t:.1f} °C")
            await asyncio.sleep(0.5)

    async def handle_upload(self, files: list[rx.UploadFile]):
        upload_dir = Path(os.getenv("UPLOAD_FOLDER", "/home/vpn/archivos"))
        upload_dir.mkdir(parents=True, exist_ok=True)
        for file in files:
            data = await file.read()
            with (upload_dir / file.name).open("wb") as f: f.write(data)
        self.status = f"✅ Subida: {len(files)} archivos"