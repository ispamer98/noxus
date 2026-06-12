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
import time

from .core.connectivity import NetUtils
from .core.ssh_manager import SSHManager
from .core.sensors import Sensors
from .core.shared_state import (
    get_sistema_armado,
    toggle_sistema_armado,
    get_notificacion_enviada,
    set_notificacion_enviada,
    get_puerta_abierta,
    set_puerta_abierta,
)

load_dotenv()

VAPID_PRIVATE = os.getenv("VAPID_PRIVATE_KEY")
VAPID_PUBLIC  = os.getenv("VAPID_PUBLIC_KEY")
VAPID_EMAIL   = os.getenv("VAPID_EMAIL", "mailto:admin@noxuscmmd.uk")

_SSH_STARTED = False
_FAN_STARTED = False


class State(rx.State):
    # ── Dispositivos ──────────────────────────────────────────────────────
    raspberry_online: bool = False
    iphone_online:    bool = False
    pc_online:        bool = False
    portatil_online:  bool = False
    pi_zero_online:   bool = False
    server_online:    bool = False
    tablet_online:    bool = False
    cam_ptz_online:   bool = False
    cam_fija_online:  bool = False

    # ── UI ────────────────────────────────────────────────────────────────
    status:              str       = "Esperando..."
    temperaturas:        list[str] = []
    last_rpi_photo:      str       = ""
    dialog_foto_abierto: bool      = False
    uploaded_files:      list[str] = []
    cam_msg:             str       = "Vídeo: Listo"
    ver_fija:            bool      = False

    # ── Seguridad ─────────────────────────────────────────────────────────
    sistema_armado: bool = False
    puerta_abierta: bool = False

    # ── Control interno por cliente ───────────────────────────────────────
    _sync_running: bool = False

    # ══════════════════════════════════════════════════════════════════════
    # ON_LOAD — ejecutado por CADA cliente al conectar
    # ══════════════════════════════════════════════════════════════════════
    @rx.event
    async def on_load(self):
        global _SSH_STARTED, _FAN_STARTED

        # Mostrar estado correcto desde el primer frame
        self.sistema_armado = await asyncio.to_thread(get_sistema_armado)
        self.puerta_abierta = await asyncio.to_thread(get_puerta_abierta)

        # Workers singleton (solo arrancan una vez por proceso)
        if not _SSH_STARTED:
            _SSH_STARTED = True
            asyncio.create_task(SSHManager.connect_async())
            yield State.keepalive_ssh_task
            yield State.monitor_temperatura_fan

        # Workers por cliente (cada cliente recibe su propio stream de updates)
        yield State.actualizar_estados        # pings inmediatos
        yield State.sincronizar_seguridad_loop  # loop propio de seguridad

    # ══════════════════════════════════════════════════════════════════════
    # LOOP DE SEGURIDAD — uno por cliente, sincroniza desde archivo JSON
    #
    # Flujo cada 1.5 s:
    #   1. Leer puerta vía SSH → guardar en archivo (fuente de verdad)
    #   2. Leer sistema_armado desde archivo
    #   3. Evaluar si hay intrusión → push si procede
    #   4. Actualizar self.sistema_armado y self.puerta_abierta de ESTE cliente
    #
    # Al estar este loop activo en CADA cliente conectado, todos reciben
    # el estado actualizado independientemente de quién hizo el cambio.
    # ══════════════════════════════════════════════════════════════════════
    @rx.event(background=True)
    async def sincronizar_seguridad_loop(self):
        async with self:
            if self._sync_running:
                return
            self._sync_running = True

        while True:
            # 1. Leer GPIO puerta y cachear resultado en archivo
            try:
                lectura = await asyncio.wait_for(
                    SSHManager.execute_async(
                        "raspi-gpio get 18 | grep -c 'level=1'", timeout=2
                    ),
                    timeout=2.5,
                )
                puerta_fisica = lectura.strip() == "1"
            except Exception:
                # Si falla SSH, usar último valor conocido del archivo
                puerta_fisica = await asyncio.to_thread(get_puerta_abierta)

            await asyncio.to_thread(set_puerta_abierta, puerta_fisica)

            # 2. Estado armado desde archivo (escrito por conmutar_alarma)
            armado = await asyncio.to_thread(get_sistema_armado)

            # 3. Lógica de notificación (atómica: solo un cliente enviará)
            if armado and puerta_fisica:
                ya = await asyncio.to_thread(get_notificacion_enviada)
                if not ya:
                    # set_notificacion_enviada antes de enviar para evitar race
                    await asyncio.to_thread(set_notificacion_enviada, True)
                    await asyncio.to_thread(
                        self.enviar_notificacion,
                        "🚨 ALERTA: INTRUSIÓN",
                        "La puerta ha sido abierta con el sistema ARMADO.",
                        "todos",
                    )
            if not puerta_fisica:
                ya = await asyncio.to_thread(get_notificacion_enviada)
                if ya:
                    await asyncio.to_thread(set_notificacion_enviada, False)

            # 4. Actualizar UI de este cliente
            async with self:
                self.sistema_armado = armado
                self.puerta_abierta = puerta_fisica

            await asyncio.sleep(1.5)

    # ══════════════════════════════════════════════════════════════════════
    # SSH keepalive — singleton
    # ══════════════════════════════════════════════════════════════════════
    @rx.event(background=True)
    async def keepalive_ssh_task(self):
        await SSHManager.keep_alive_loop()

    # ══════════════════════════════════════════════════════════════════════
    # Pings paralelos — por cliente
    # ══════════════════════════════════════════════════════════════════════
    @rx.event(background=True)
    async def actualizar_estados(self):
        hosts = [
            (os.getenv("IP_SERVER",    "0.0.0.0"), 1),
            (os.getenv("IP_RASPBERRY", "0.0.0.0"), 1),
            (os.getenv("IP_TABLET",    "0.0.0.0"), 1),
            (os.getenv("IP_IPHONE",    "0.0.0.0"), 2),
            (os.getenv("IP_PC",        "0.0.0.0"), 1),
            (os.getenv("IP_PORTATIL",  "0.0.0.0"), 1),
            (os.getenv("IP_PI_ZERO",   "0.0.0.0"), 2),
            (os.getenv("IP_CAM_PTZ",   "0.0.0.0"), 1),
            (os.getenv("IP_CAM_FIJA",  "0.0.0.0"), 1),
        ]
        results = await NetUtils.ping_all(hosts)
        (server_r, rpi_r, tablet_r, iphone_r,
         pc_r, port_r, zero_r, ptz_r, fija_r) = results
        async with self:
            self.server_online    = server_r
            self.raspberry_online = rpi_r
            self.tablet_online    = tablet_r
            self.iphone_online    = iphone_r
            self.pc_online        = pc_r
            self.portatil_online  = port_r
            self.pi_zero_online   = zero_r
            self.cam_ptz_online   = ptz_r
            self.cam_fija_online  = fija_r

    # ══════════════════════════════════════════════════════════════════════
    # Termostato — singleton
    # ══════════════════════════════════════════════════════════════════════
    @rx.event(background=True)
    async def monitor_temperatura_fan(self):
        while True:
            try:
                temp_str = await SSHManager.execute_async(
                    "cat /sys/class/thermal/thermal_zone0/temp", timeout=2
                )
                if temp_str and not temp_str.startswith("ERROR"):
                    t = int(temp_str) / 1000.0
                    if t >= 80.0:
                        await SSHManager.execute_async("raspi-gpio set 17 op dh", timeout=2)
                    elif t <= 75.0:
                        await SSHManager.execute_async("raspi-gpio set 17 op dl", timeout=2)
            except Exception as e:
                print(f"⚠️ Termostato: {e}")
            await asyncio.sleep(10)

    # ══════════════════════════════════════════════════════════════════════
    # ARMAR / DESARMAR
    # ══════════════════════════════════════════════════════════════════════
    @rx.event
    async def conmutar_alarma(self):
        # Escribe en archivo → los loops de TODOS los clientes lo leen en ≤1.5 s
        nuevo = await asyncio.to_thread(toggle_sistema_armado)
        # Actualización local instantánea para el cliente que pulsó el botón
        self.sistema_armado = nuevo
        self.status = (
            "🔒 Sistema de Seguridad: ARMADO"
            if nuevo else
            "🔓 Sistema de Seguridad: DESARMADO"
        )

    # ══════════════════════════════════════════════════════════════════════
    # ALERTA MANUAL
    # ══════════════════════════════════════════════════════════════════════
    @rx.event
    def lanzar_alerta_global(self):
        asyncio.create_task(
            asyncio.to_thread(
                self.enviar_notificacion,
                "🆘 ALERTA MANUAL",
                "Se ha activado el botón de pánico desde el panel de control.",
            )
        )
        self.status = "🆘 Alerta Global Enviada"

    # ══════════════════════════════════════════════════════════════════════
    # PUSH
    # ══════════════════════════════════════════════════════════════════════
    def enviar_notificacion(self, titulo: str, mensaje: str, destino: str = "todos"):
        archivo = "suscriptores.json"
        if not os.path.exists(archivo):
            return
        try:
            with open(archivo) as f:
                subs = json.load(f)
            payload = json.dumps({
                "title": titulo, "body": mensaje,
                "icon": "/icono.png", "badge": "/icono.png",
            })
            for sub in subs:
                if destino != "todos" and sub.get("nombre_usuario") != destino:
                    continue
                try:
                    webpush(
                        subscription_info=sub, data=payload,
                        vapid_private_key=VAPID_PRIVATE,
                        vapid_claims={"sub": VAPID_EMAIL}, timeout=5,
                    )
                    print(f"✅ Push → {sub.get('nombre_usuario', '?')}")
                except Exception as ex:
                    print(f"❌ Push → {sub.get('nombre_usuario', '?')}: {ex}")
        except Exception as e:
            print(f"❌ enviar_notificacion: {e}")

    @rx.event
    def guardar_subscripcion(self, js_result: str):
        if js_result == "USER_CANCEL":
            self.status = "Registro cancelado"
            return
        if not js_result or "ERROR" in js_result or js_result == "PERMISO_DENEGADO":
            self.status = f"❌ Push: {js_result}"
            return rx.window_alert(f"Error en notificaciones: {js_result}")
        try:
            data           = json.loads(js_result)
            sub_dict       = data.get("subscription")
            nombre_usuario = data.get("nombre", "").strip()
            if not nombre_usuario:
                self.status = "❌ Nombre inválido"
                return rx.window_alert("Debe proporcionar un nombre para el dispositivo.")
            archivo = "suscriptores.json"
            subs = []
            if os.path.exists(archivo):
                with open(archivo) as f:
                    try: subs = json.load(f)
                    except: subs = []
            existe_endpoint = False
            existe_nombre   = False
            endpoint_dup    = None
            for s in subs:
                if s.get("endpoint") == sub_dict.get("endpoint"):
                    existe_endpoint = True; endpoint_dup = s; break
                if s.get("nombre_usuario") == nombre_usuario:
                    existe_nombre = True
            if existe_endpoint:
                if endpoint_dup.get("nombre_usuario") != nombre_usuario:
                    endpoint_dup["nombre_usuario"] = nombre_usuario
                    with open(archivo, "w") as f: json.dump(subs, f, indent=4)
                    self.status = f"🔄 Nombre actualizado: '{nombre_usuario}'"
                    return rx.window_alert(f"✅ Nombre actualizado a '{nombre_usuario}'")
                else:
                    self.status = "ℹ️ Ya registrado"
                    return rx.window_alert("Este dispositivo ya estaba registrado.")
            if existe_nombre:
                self.status = f"❌ Nombre en uso"
                return rx.window_alert(f"El nombre '{nombre_usuario}' ya está en uso.")
            sub_dict["nombre_usuario"] = nombre_usuario
            subs.append(sub_dict)
            with open(archivo, "w") as f: json.dump(subs, f, indent=4)
            self.status = f"🔔 Vinculado: '{nombre_usuario}'"
            return rx.window_alert(f"✅ Dispositivo '{nombre_usuario}' vinculado!")
        except Exception as e:
            print(f"guardar_subscripcion error: {e}")
            self.status = "❌ Error al vincular"
            return rx.window_alert("Error inesperado.")

    # ══════════════════════════════════════════════════════════════════════
    # CÁMARAS
    # ══════════════════════════════════════════════════════════════════════
    @rx.var
    def url_snapshot_fija(self) -> str:
        return f"http://192.168.1.52/snapshot.jpg?t={int(time.time())}"

    def toggle_fija(self):
        self.ver_fija = not self.ver_fija


    # ── Streams públicos (go2rtc) ─────────────────────────────────────
    @rx.var
    def url_fija_stream(self) -> str:
        return "https://cam.noxuscmmd.uk/stream.html?src=fija"

    show_fija_stream: bool = False
    show_ptz_stream: bool = False

    def toggle_fija_stream(self):
        self.show_fija_stream = not self.show_fija_stream

    def toggle_ptz_stream(self):
        self.show_ptz_stream = not self.show_ptz_stream

    @rx.var
    def url_ptz_embed(self) -> str:
        return f"http://{os.getenv('IP_RASPBERRY', '0.0.0.0')}:1984/webrtc.html?src=ptz"

    @rx.event(background=True)
    async def move_ptz(self, direction: str):
        import aiohttp, hmac, hashlib
        t_id = os.getenv("TUYA_ACCESS_ID")
        t_secret = os.getenv("TUYA_ACCESS_SECRET")
        dev_id = os.getenv("ID_PTZ_TUYA")
        endpoint = "https://openapi.tuyaeu.com"
        def get_sign(method, path, token="", body=""):
            ts = str(int(time.time() * 1000))
            cs = hashlib.sha256(body.encode()).hexdigest()
            sp = t_id + token + ts + f"{method}\n{cs}\n\n{path}"
            return hmac.new(t_secret.encode(), sp.encode(), hashlib.sha256).hexdigest().upper(), ts
        try:
            async with aiohttp.ClientSession() as s:
                sg, ts = get_sign("GET", "/v1.0/token?grant_type=1")
                async with s.get(endpoint + "/v1.0/token?grant_type=1",
                    headers={"client_id": t_id, "sign": sg, "t": ts, "sign_method": "HMAC-SHA256"},
                    timeout=aiohttp.ClientTimeout(total=5)) as r:
                    token = (await r.json()).get("result", {}).get("access_token")
                cp = f"/v1.0/devices/{dev_id}/commands"
                bm = json.dumps({"commands": [{"code": "ptz_control", "value": direction}]})
                sm, tm = get_sign("POST", cp, token, bm)
                h = {"client_id": t_id, "access_token": token, "sign": sm, "t": tm,
                     "sign_method": "HMAC-SHA256", "Content-Type": "application/json"}
                async with s.post(endpoint + cp, headers=h, data=bm, timeout=aiohttp.ClientTimeout(total=5)): pass
                await asyncio.sleep(0.2)
                bs = json.dumps({"commands": [{"code": "ptz_stop", "value": True}]})
                ss2, ts2 = get_sign("POST", cp, token, bs)
                h["sign"] = ss2; h["t"] = ts2
                async with s.post(endpoint + cp, headers=h, data=bs, timeout=aiohttp.ClientTimeout(total=5)): pass
            async with self: self.cam_msg = f"✅ {direction}"
        except Exception as e:
            async with self: self.cam_msg = f"❌ {str(e)[:60]}"

    # ══════════════════════════════════════════════════════════════════════
    # GPIO / VENTILADOR / SNAPSHOT / TEMPERATURA / PC
    # ══════════════════════════════════════════════════════════════════════
    @rx.event(background=True)
    async def gpio_17(self):
        async with self: self.status = "🌬️ Ventilador ON..."
        try:
            await SSHManager.execute_async("raspi-gpio set 17 op dh", timeout=3)
            await asyncio.sleep(5)
            await SSHManager.execute_async("raspi-gpio set 17 op dl", timeout=3)
            async with self: self.status = "🌬️ Test completado"
        except Exception as e:
            async with self: self.status = f"❌ GPIO: {e}"

    @rx.event(background=True)
    async def tomar_foto_raspberry(self):
        async with self:
            if not self.pi_zero_online:
                self.status = "❌ Pi Zero OFFLINE"; return
            self.status = "📸 Capturando..."
        try:
            foto_bytes = await asyncio.to_thread(self._foto_sync)
            foto_b64   = base64.b64encode(foto_bytes).decode()
            async with self:
                self.last_rpi_photo = f"data:image/jpeg;base64,{foto_b64}"
                self.dialog_foto_abierto = True
                self.status = "✅ Foto capturada"
        except Exception as e:
            async with self: self.status = f"❌ Foto: {e}"

    def _foto_sync(self) -> bytes:
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

    def toggle_dialog(self):
        self.dialog_foto_abierto = not self.dialog_foto_abierto

    @rx.event(background=True)
    async def medir_temperatura(self):
        async with self: self.temperaturas = []; self.status = "🌡️ Midiendo..."
        resultados = await asyncio.gather(
            Sensors.get_cpu_temp_async(),
            Sensors.get_cpu_temp_async(),
            Sensors.get_cpu_temp_async(),
        )
        async with self:
            self.temperaturas = [f"🌡️ {t:.1f} °C" for t in resultados]
            self.status = f"🌡️ Temp: {resultados[1]:.1f} °C"

    def wake_pc(self):
        NetUtils.send_wol(os.getenv("PC_MAC")); self.status = "⚡ WOL enviado"

    @rx.event(background=True)
    async def apagar_pc(self):
        async with self: self.status = "🔌 Apagando PC..."
        await asyncio.to_thread(subprocess.run,
            f'ssh -o StrictHostKeyChecking=no -o ConnectTimeout=4 '
            f'{os.getenv("PC_USER")}@{os.getenv("IP_PC")} "shutdown /s /t 0 /f"',
            shell=True)
        async with self: self.status = "🔌 Apagado enviado"

    @rx.event(background=True)
    async def restart_raspberry(self):
        async with self: self.status = "🔄 Reiniciando Raspberry..."
        await asyncio.to_thread(subprocess.Popen,
            f'ssh -o StrictHostKeyChecking=no -o ConnectTimeout=4 '
            f'vpn@{os.getenv("IP_RASPBERRY", "100.76.90.7")} "sudo reboot now"',
            shell=True)
        async with self: self.status = "🔄 Reboot enviado"

    def _run_sh(self, name: str):
        p = f"/home/spamer/{name}.sh"
        if os.path.exists(p): subprocess.Popen(["/bin/bash", p]); self.status = f"▶ {name}..."
        else: self.status = f"❌ Falta {name}.sh"

    def rdp_pc(self):        self._run_sh("portatil_to_pc")
    def rdp_portatil(self):  self._run_sh("pc_to_portatil")
    def rdp_raspberry(self): self._run_sh("pc_to_raspberry")

    async def handle_upload(self, files: list[rx.UploadFile]):
        upload_dir = Path(os.getenv("UPLOAD_FOLDER", "/home/spamer/archivos"))
        upload_dir.mkdir(parents=True, exist_ok=True)
        for file in files:
            data = await file.read()
            (upload_dir / file.name).write_bytes(data)
        self.status = f"✅ {len(files)} archivo(s) subido(s)"