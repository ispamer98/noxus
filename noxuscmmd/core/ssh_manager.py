"""
La conexión SSH persistente hacia la Raspberry Pi que hace de puente VPN
(sensores.py la usa para leer la temperatura; otros dominios pueden querer
ejecutar comandos remotos en el futuro).

UNA SOLA CONEXIÓN, REUTILIZADA. Abrir y cerrar SSH en cada consulta (era el
diseño original) tarda demasiado para algo que se pregunta cada pocos
segundos, así que aquí se abre una vez, se mantiene viva con un keepalive cada
20s, y se reconecta sola si se cae (Wi-Fi de la Raspberry, reinicio, etc.).

SINGLETON DE CLASE, NO INSTANCIA: no hace falta más de una conexión a la vez
en todo el proceso, así que todo vive en atributos de clase protegidos por un
`Lock` — dos peticiones a la vez no deben abrir dos conexiones (la segunda
pisaría el cliente de la primera, que se quedaría huérfano y sin cerrar).

Arranca con `run_forever` como lifespan task del proceso (ver noxuscmmd.py):
depende de que la máquina esté viva, no de que haya una pestaña abierta.
"""
import paramiko
import os
import asyncio
import threading
from dotenv import load_dotenv

load_dotenv()

class SSHManager:
    _client = None
    _transport = None
    _lock = threading.Lock()
    _connecting = False

    @classmethod
    def connect(cls):
        """Establece o restablece la conexión SSH persistente (síncrono, thread-safe)."""
        with cls._lock:
            if cls._connecting:
                return
            cls._connecting = True

        try:
            if cls._client is not None:
                try:
                    cls._client.close()
                except Exception:
                    pass
                cls._client = None
                cls._transport = None

            host = os.getenv("IP_RASPBERRY", "100.76.90.7")
            user = "vpn"
            key_path = os.path.expanduser("~/.ssh/id_ed25519")

            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname=host,
                username=user,
                key_filename=key_path,
                timeout=5,
                banner_timeout=5,
                auth_timeout=5,
            )
            transport = client.get_transport()
            transport.set_keepalive(20)

            with cls._lock:
                cls._client = client
                cls._transport = transport

            print(f"✅ SSH persistente conectado a {host}")
        except Exception as e:
            print(f"⚠️ Error SSH persistente: {e}")
            with cls._lock:
                cls._client = None
                cls._transport = None
        finally:
            cls._connecting = False

    @classmethod
    async def connect_async(cls):
        """Versión asíncrona del connect para no bloquear el event loop."""
        await asyncio.to_thread(cls.connect)

    @classmethod
    def _is_alive(cls) -> bool:
        """Comprueba si la conexión SSH sigue activa sin bloquear."""
        try:
            t = cls._transport
            return t is not None and t.is_active()
        except Exception:
            return False

    @classmethod
    async def execute_async(cls, command: str, timeout: int = 3) -> str:
        """Ejecuta un comando SSH de forma asíncrona. Reconecta si es necesario."""
        if not cls._is_alive():
            await cls.connect_async()

        if cls._client is None:
            return "ERROR: sin conexión SSH"

        try:
            return await asyncio.wait_for(
                asyncio.to_thread(cls._execute_sync, command, timeout),
                timeout=timeout + 1,
            )
        except asyncio.TimeoutError:
            return "ERROR: timeout"
        except Exception as e:
            print(f"⚠️ execute_async falló, reconectando: {e}")
            await cls.connect_async()
            if cls._client:
                try:
                    return await asyncio.to_thread(cls._execute_sync, command, timeout)
                except Exception as e2:
                    return f"ERROR: {e2}"
            return f"ERROR: {e}"

    @classmethod
    def _execute_sync(cls, command: str, timeout: int) -> str:
        try:
            _, stdout, stderr = cls._client.exec_command(command, timeout=timeout)
            out = stdout.read().decode().strip()
            err = stderr.read().decode().strip()
            return out if not err else f"ERROR: {err}"
        except Exception as e:
            return f"ERROR: {e}"

    @classmethod
    async def run_forever(cls):
        """Conexión persistente y su keepalive, para el lifespan.

        Antes esto lo arrancaba la primera sesión que cargaba el panel, con un
        global (`_SSH_STARTED`) para no repetirlo. Cuando los bucles de sesión
        pasaron a morir con su navegador, el keepalive se moría con ellos y el
        global impedía que nadie lo relanzara: la conexión se quedaba sin quien
        la vigilara ni la reconectara. Mantener viva una conexión SSH no es
        cosa de una pantalla."""
        await cls.connect_async()
        await cls.keep_alive_loop()

    @classmethod
    async def keep_alive_loop(cls):
        """Keepalive loop — lanzar UNA sola vez como background task."""
        while True:
            await asyncio.sleep(20)
            if cls._is_alive():
                try:
                    await asyncio.to_thread(
                        cls._client.exec_command, "echo k", 2
                    )
                except Exception:
                    print("⚠️ Keepalive falló, reconectando...")
                    await cls.connect_async()
            else:
                await cls.connect_async()