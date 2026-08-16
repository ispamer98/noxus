"""
Puente con el mando IR/RF (Broadlink RM4 Pro): aprende y repite señales de
mandos reales sin pasar por la nube del fabricante — 100% LAN, mismo espíritu
que gpio_bus/ssh_bus. Un único hub físico (IP_BROADLINK/MAC_BROADLINK en
.env) controla cualquier número de "mandos virtuales" (TV, ventilador...),
que aquí no son más que un nombre y una lista de botones — cada botón, un
código guardado en hex (ver domains/nodes/store.py: colección "ir_remotes").

Singleton de proceso, igual que mqtt_bus.get_mqtt_bus(): el objeto `device`
de la librería `broadlink` guarda la clave de autenticación tras el primer
auth() y no hace falta rehacerlo en cada botón.
"""
import asyncio
import contextlib
import os

import broadlink
from broadlink.exceptions import (
    AuthenticationError, AuthorizationError, BroadlinkException,
    ConnectionClosedError, DeviceOfflineError, NetworkTimeoutError,
    StorageError,
)

_device = None

# Errores que significan "la sesión con el hub ya no vale", no "el mando no ha
# dicho nada". El Broadlink caduca la sesión por su cuenta (tras un rato, tras
# un puñado de operaciones o si se reinicia), y como el cliente se guarda en
# memoria para todo el proceso, sin esto la primera caducidad dejaba el mando
# inservible hasta reiniciar la app: aprender dejaba de funcionar de golpe
# después de unos cuantos botones, sin decir por qué.
_ERRORES_DE_SESION = (
    AuthenticationError, AuthorizationError, ConnectionClosedError,
    DeviceOfflineError, NetworkTimeoutError, OSError,
)

# Hay UN hub físico y una sola sesión con él, así que sus operaciones van de
# una en una. Importa más de lo que parece: aprender pone el aparato en modo
# escucha durante segundos, y un envío colado en medio se lleva por delante la
# captura; y dos envíos a la vez pueden hacer que el forget_connection() de uno
# invalide la sesión que el otro está usando (ver _con_reintento).
_LOCK = asyncio.Lock()

# Cuánto esperar como mucho a que el hub quede libre. Con espera ilimitada, una
# tecla pulsada mientras se aprende otra señal saldría 25 segundos después, con
# el usuario ya en otra cosa — encender la tele a destiempo es peor que decir
# que ahora no se puede.
_ESPERA_MAX = 8.0


@contextlib.asynccontextmanager
async def _hub_para_mi(espera: float = _ESPERA_MAX):
    try:
        await asyncio.wait_for(_LOCK.acquire(), timeout=espera)
    except asyncio.TimeoutError:
        raise RuntimeError(
            "El mando está ocupado con otra operación (aprendiendo una señal, "
            "probablemente) — espera a que termine e inténtalo otra vez."
        )
    try:
        yield
    finally:
        _LOCK.release()


def _connect():
    host = os.getenv("IP_BROADLINK", "").strip()
    mac = os.getenv("MAC_BROADLINK", "").strip()
    if not host or not mac:
        raise RuntimeError(
            "Falta IP_BROADLINK/MAC_BROADLINK en .env — configúralos con la IP "
            "reservada y la MAC del Broadlink antes de aprender o enviar botones."
        )
    mac_bytes = bytes.fromhex(mac.replace(":", "").replace("-", ""))
    dev = broadlink.hello(host)
    dev.auth()
    # Comprobación de que el host/mac configurados son el mismo aparato que ha
    # contestado — evita aprender/enviar contra el dispositivo equivocado si
    # algún día hay más de un Broadlink en la red.
    if dev.mac != mac_bytes:
        raise RuntimeError(
            f"El Broadlink en {host} no tiene la MAC configurada en .env "
            f"(MAC_BROADLINK) — revisa la IP reservada."
        )
    return dev


def _get_device():
    global _device
    if _device is None:
        _device = _connect()
    return _device


def _con_reintento(accion):
    """Ejecuta `accion(dispositivo)` y, si el hub contesta que la sesión ya no
    vale, reconecta desde cero y lo intenta UNA vez más.

    Es lo que hace que el mando siga funcionando indefinidamente: el Broadlink
    invalida la sesión cada cierto tiempo por su cuenta, y antes eso dejaba de
    aprender botones para siempre (hasta reiniciar el proceso), porque el
    cliente cacheado ya nunca volvía a autenticarse."""
    try:
        return accion(_get_device())
    except _ERRORES_DE_SESION:
        forget_connection()
        return accion(_get_device())


def _limpiar_estado(dev) -> None:
    """Vacía el buffer de captura del hub antes de empezar uno nuevo, para que
    una señal vieja no se dé por recién capturada.

    SOLO se drena check_data. Aquí NO se cancela el barrido de
    radiofrecuencia: en el camino de infrarrojos no hay ningún barrido que
    cancelar, y mandárselo igualmente dejaba al aparato sin captar nada — un
    mando que aprendía bien dejaba de responder de golpe. El barrido RF ya se
    cancela donde de verdad se abre, en learn_rf_button.

    Un fallo aquí no importa (lo normal es que no haya nada que drenar, y el
    hub contesta con error a eso), así que se ignora: esto es una limpieza
    previa, no una operación."""
    try:
        dev.check_data()
    except Exception:
        pass


def _entrar_en_aprendizaje(rf_frecuencia=None):
    """Deja el hub escuchando, limpio de capturas anteriores y reconectando si
    hiciera falta."""
    def _accion(dev):
        _limpiar_estado(dev)
        if rf_frecuencia is None:
            dev.enter_learning()
        else:
            dev.find_rf_packet(rf_frecuencia)
        return dev

    return _con_reintento(_accion)


async def learn_button(timeout: float = 15.0) -> str:
    async with _hub_para_mi():
        return await _learn_button(timeout)


async def _learn_button(timeout: float = 15.0) -> str:
    """Pone el hub en modo aprendizaje y espera a que llegue una señal — el
    usuario acerca el mando real y pulsa el botón. Devuelve el código
    capturado en hex, listo para guardar y repetir con send_button().

    Lanza TimeoutError si no llega ninguna señal a tiempo (mando fuera de
    rango, pila gastada, o se les olvidó pulsar)."""
    dev = await asyncio.to_thread(_entrar_en_aprendizaje)
    # Margen para que el hub se ponga a escuchar de verdad. Sin él, el primer
    # sondeo llega antes de que el modo aprendizaje esté activo y hay
    # firmwares que lo interpretan como "captura terminada sin datos".
    await asyncio.sleep(0.3)
    elapsed = 0.0
    ultimo_error = None
    reconectado = False
    while elapsed < timeout:
        await asyncio.sleep(0.5)
        elapsed += 0.5
        try:
            data = await asyncio.to_thread(dev.check_data)
        except _ERRORES_DE_SESION as exc:
            # La sesión ha caducado a mitad de la espera: se rehace y se
            # vuelve a poner a escuchar, UNA vez, en vez de agotar el tiempo
            # entero preguntando contra una sesión muerta.
            ultimo_error = exc
            if reconectado:
                break
            reconectado = True
            forget_connection()
            dev = await asyncio.to_thread(_entrar_en_aprendizaje)
            continue
        except StorageError:
            # "Todavía no ha llegado nada". El RM4 contesta a check_data con
            # el código -5, cuyo texto oficial es "the device storage is
            # full", pero NO significa eso: es su forma de decir que el buffer
            # de captura sigue vacío. Es la respuesta NORMAL mientras se
            # espera a que pulses el mando, así que ni se guarda como error ni
            # se enseña — sacarlo por pantalla hacía pensar que el aparato
            # estaba lleno y había algo que borrar, cuando no pasaba nada.
            continue
        except BroadlinkException as exc:
            # Cualquier otra respuesta rara: se sigue esperando igual, pero se
            # guarda para poder contarla si al final se agota el tiempo — así
            # se distingue "no llegó nada nunca" de "llegó algo y el hub lo
            # rechazó".
            ultimo_error = exc
            continue
        if data:
            return data.hex()
    detalle = f" (el hub respondió: {ultimo_error})" if ultimo_error else ""
    raise TimeoutError(
        "No se captó la señal. Apunta el mando a la ventanita del Broadlink a "
        f"unos 5 cm y mantén el botón pulsado un segundo{detalle}"
    )


async def learn_rf_button(on_status=None, timeout_sweep: float = 25.0,
                           timeout_capture: float = 15.0) -> str:
    async with _hub_para_mi():
        return await _learn_rf_button(on_status, timeout_sweep, timeout_capture)


async def _learn_rf_button(on_status=None, timeout_sweep: float = 25.0,
                            timeout_capture: float = 15.0) -> str:
    """Aprendizaje de radiofrecuencia (433/315MHz) — mandos de ventiladores de
    techo, la mayoría de las veces. A diferencia del IR, es un proceso en DOS
    fases porque primero hay que encontrar la frecuencia exacta que usa el
    mando antes de poder capturar la señal en sí:

    1. Barrido de frecuencia: mantener el botón PULSADO mientras el hub
       escucha en todo el espectro hasta identificarla.
    2. Captura: soltar y pulsar el botón BREVEMENTE otra vez, ya en la
       frecuencia encontrada, para grabar la señal exacta.

    `on_status`, si se da, es una corrutina que se llama con un texto para
    informar de en qué fase está — el paso de "mantén pulsado" a "pulsa
    brevemente" pasa desapercibido si no se avisa.

    El código que devuelve se envía exactamente igual que uno de IR — el
    formato del paquete ya lleva dentro si es IR o RF, send_button() no
    necesita distinguirlos."""
    dev = await asyncio.to_thread(_con_reintento, lambda d: d)

    if on_status:
        await on_status("📡 Mantén PULSADO el botón del mando (buscando frecuencia)...")
    await asyncio.to_thread(_con_reintento, lambda d: d.sweep_frequency())
    elapsed = 0.0
    frequency = None
    try:
        while elapsed < timeout_sweep:
            await asyncio.sleep(1.0)
            elapsed += 1.0
            encontrada, freq = await asyncio.to_thread(dev.check_frequency)
            if encontrada:
                frequency = freq
                break
    finally:
        await asyncio.to_thread(dev.cancel_sweep_frequency)
    if frequency is None:
        raise TimeoutError(
            "No se detectó la frecuencia — mantén el botón pulsado más tiempo y acércate al hub"
        )

    if on_status:
        await on_status(f"✅ Frecuencia {frequency:.2f}MHz encontrada. Suelta y pulsa el botón BREVEMENTE otra vez...")
    dev = await asyncio.to_thread(_entrar_en_aprendizaje, frequency)
    elapsed = 0.0
    ultimo_error = None
    reconectado = False
    while elapsed < timeout_capture:
        await asyncio.sleep(0.5)
        elapsed += 0.5
        try:
            data = await asyncio.to_thread(dev.check_data)
        except _ERRORES_DE_SESION as exc:
            ultimo_error = exc
            if reconectado:
                break
            reconectado = True
            forget_connection()
            dev = await asyncio.to_thread(_entrar_en_aprendizaje, frequency)
            continue
        except BroadlinkException as exc:
            ultimo_error = exc
            continue
        if data:
            return data.hex()
    detalle = f" (el hub respondió: {ultimo_error})" if ultimo_error else ""
    raise TimeoutError(f"Frecuencia encontrada pero no se capturó la señal — vuelve a intentarlo{detalle}")


async def send_button(code_hex: str) -> None:
    """Repite un código ya aprendido — esto es lo que dispara cada botón del
    mando virtual del panel.

    Con reintento por el mismo motivo que el aprendizaje: si el hub ha
    caducado la sesión, un mando que llevaba rato sin usarse fallaría en el
    primer botón y no se recuperaría solo."""
    datos = bytes.fromhex(code_hex)
    async with _hub_para_mi():
        await asyncio.to_thread(_con_reintento, lambda d: d.send_data(datos))


def forget_connection() -> None:
    """Fuerza una reconexión/reautenticación en el próximo uso — para cuando
    el Broadlink cambia de IP o hay que reintentar tras un error de red."""
    global _device
    _device = None
