"""
Accesorios que se encienden por mando: la luz del ventilador de techo, la tele.

Comparten colección y mecánica con las luces a propósito (ver store.ASPECTOS):
de ahí les viene salir en el plano, en el Resumen, en las automatizaciones y en
la paleta sin duplicar nada. Lo que cambia es cómo se les manda la orden.

NO se pulsa ninguna tecla de verdad: se prueba lo que decide (qué campos quedan
guardados, qué tecla tocaría y qué pasa si falta) y nunca `send_remote_button`.
"""
import asyncio

from tests.comun import Caso

from noxuscmmd.domains.nodes import operations as ops
from noxuscmmd.domains.nodes import store
from noxuscmmd.domains.devices import ir_bus


def _almacen() -> Caso:
    c = Caso("Accesorios por mando en el almacén")

    rele = store.add_light("Luz de prueba", "nodo1", "Nodo Uno", "22")
    c.revisar("una luz normal sigue siendo de relé", rele["kind"], store.LUZ_RELE)
    c.cierto("y conserva su topic", bool(rele["topic_cmd"]))
    c.revisar("y su aspecto por defecto es luz", rele["aspecto"], "luz")

    mando = store.add_light(
        "Luz del ventilador", "", "", "", kind=store.LUZ_MANDO,
        remote_id="ir_1", btn_on="btn_on1", btn_off="btn_off1",
        aspecto="ventilador")
    c.revisar("guarda que es por mando", mando["kind"], store.LUZ_MANDO)
    c.revisar("guarda el mando", mando["remote_id"], "ir_1")
    c.revisar("guarda la tecla de encender", mando["btn_on"], "btn_on1")
    c.revisar("guarda la tecla de apagar", mando["btn_off"], "btn_off1")
    c.revisar("guarda qué accesorio es", mando["aspecto"], "ventilador")
    c.revisar("apagado automático desactivado por defecto",
              mando["auto_apagado_min"], 0)
    # Sin topics: no hay nada publicando su estado, y dejar un "casa//" haría
    # que el bus se suscribiera a un topic inventado.
    c.revisar("no inventa topic de orden", mando["topic_cmd"], "")
    c.revisar("no inventa topic de estado", mando["topic_state"], "")

    # Cambiar de forma de accionar tiene que limpiar lo de la anterior.
    vuelta = store.update_light(mando["id"], "Luz del ventilador", "nodo1",
                                "Nodo Uno", "23", kind=store.LUZ_RELE)
    c.cierto("al pasar a relé estrena topic", bool(vuelta["topic_cmd"]))
    c.revisar("y suelta el mando", vuelta["remote_id"], "")

    otra_vez = store.update_light(mando["id"], "Luz del ventilador", "", "", "",
                                  kind=store.LUZ_MANDO, remote_id="ir_2",
                                  btn_on="b1", btn_off="b2", aspecto="tv",
                                  auto_apagado_min=15)
    c.revisar("guarda el apagado automático", otra_vez["auto_apagado_min"], 15)
    c.revisar("al volver a mando suelta el topic", otra_vez["topic_cmd"], "")
    c.revisar("y coge el mando nuevo", otra_vez["remote_id"], "ir_2")
    c.revisar("un aspecto inventado cae en luz",
              store.update_light(mando["id"], "x", "", "", "",
                                 kind=store.LUZ_MANDO, remote_id="ir_2",
                                 btn_on="b1", btn_off="b2",
                                 aspecto="platillo_volante")["aspecto"], "luz")

    store.delete_light(rele["id"])
    store.delete_light(mando["id"])
    return c


def _envio() -> Caso:
    c = Caso("Qué tecla se pulsaría (sin pulsarla)")
    pulsado = []

    async def espia(remote_id, button_id, **kwargs):
        pulsado.append((remote_id, button_id))
        return f"{remote_id}·{button_id}"

    original = ops.send_remote_button
    ops.send_remote_button = espia
    try:
        luz = {"id": "l1", "name": "Luz del ventilador", "kind": store.LUZ_MANDO,
               "remote_id": "ir_1", "btn_on": "on1", "btn_off": "off1"}
        asyncio.run(ops._enviar_por_mando(luz, True))
        c.revisar("encender pulsa la tecla de encender", pulsado[-1], ("ir_1", "on1"))
        asyncio.run(ops._enviar_por_mando(luz, False))
        c.revisar("apagar pulsa la tecla de apagar", pulsado[-1], ("ir_1", "off1"))

        # Si falta una tecla se avisa ANTES de mandar nada: un accesorio a medio
        # configurar tiene que decirlo, no quedarse mudo.
        a_medias = {"id": "l2", "name": "A medias", "kind": store.LUZ_MANDO,
                    "remote_id": "ir_1", "btn_on": "", "btn_off": "off1"}
        try:
            asyncio.run(ops._enviar_por_mando(a_medias, True))
            c.revisar("sin tecla de encender protesta", "no protestó", "NotConfigured")
        except ops.NotConfigured as e:
            c.cierto("sin tecla de encender protesta", "encender" in str(e))
        c.revisar("y no ha pulsado nada de más", len(pulsado), 2)
    finally:
        ops.send_remote_button = original
    return c


def _modos_encendido() -> Caso:
    c = Caso("Modos de encendido de accesorios")
    base = {"btn_on": "on", "btn_continuo": "cont", "btn_timing": "timer",
            "pausa_secuencia_s": 1.5}
    for modo, esperado in (("continuo", [("on", 0), ("cont", 1.5)]),
                           ("1h", [("on", 0)]),
                           ("2h", [("on", 0), ("timer", 1.5)]),
                           ("3h", [("on", 0), ("timer", 1.5), ("timer", 1.5)])):
        c.revisar(f"secuencia {modo}", store.secuencia_encendido(
            {**base, "modo_encendido": modo}), esperado)
    c.revisar("modo vacío solo pulsa encendido", store.secuencia_encendido(
        {**base, "modo_encendido": ""}), [("on", 0)])
    c.revisar("modo desconocido solo pulsa encendido", store.secuencia_encendido(
        {**base, "modo_encendido": "x"}), [("on", 0)])
    c.revisar("sin tecla de modo hace fallback", store.secuencia_encendido(
        {"btn_on": "on", "modo_encendido": "2h", "btn_timing": ""}), [("on", 0)])
    for modo, minutos in (("continuo", 0), ("1h", 60), ("2h", 120), ("3h", 180), ("x", 0)):
        c.revisar(f"duración {modo}", store.duracion_ciclo_min(modo), minutos)
    mando = store.add_ir_remote("Mando modos")
    on = store.add_ir_button(mando["id"], "On", "power", "on")
    cont = store.add_ir_button(mando["id"], "Continuo", "waves", "cont")
    timer = store.add_ir_button(mando["id"], "Timer", "clock", "timer")
    luz = store.add_light("Accesorio modos", "", "", "", kind=store.LUZ_MANDO,
                          remote_id=mando["id"], btn_on=on["id"], btn_off=on["id"],
                          btn_continuo=cont["id"], btn_timing=timer["id"])
    c.cierto("guarda teclas existentes", luz["btn_continuo"] == cont["id"] and
             luz["btn_timing"] == timer["id"])
    c.revisar("modo válido cambia", store.set_modo_encendido(luz["id"], "continuo")["modo_encendido"], "continuo")
    c.revisar("modo desconocido no cambia", store.set_modo_encendido(luz["id"], "x"), None)
    store.update_light(luz["id"], luz["name"], "", "", "", kind=store.LUZ_MANDO,
                       remote_id=mando["id"], btn_on=on["id"], btn_off=on["id"],
                       btn_continuo=cont["id"], btn_timing="missing")
    c.revisar("tecla ausente impide 2h", store.set_modo_encendido(luz["id"], "2h"), None)
    store.delete_light(luz["id"])
    store.delete_ir_remote(mando["id"])
    return c


def ejecutar() -> list[Caso]:
    return [_modos_encendido(), _apagar_luz(), _mando_directo_y_pulsacion_larga(),
            _pulsacion_larga_codigos(), _activacion_con_modo(), _almacen(), _envio(), _una_sola_tecla(), _separacion(), _widgets(),
            _estado_compartido(), _orden_idempotente(),
            _apagado_automatico(),
            _secuencia_apagar_habitacion(), _sin_doble_contabilidad(), _familias(),
            _familia_mandos(), _webos_directo(), _alta_boton_webos(),
            _plantilla_humidificador()]


def _apagar_luz() -> Caso:
    c = Caso("Pulsación larga de tecla Luz del humidificador")
    c.revisar("mantener activo", store.luz_a_mantener({
        "apagar_luz_al_encender": True, "btn_luz": "luz",
        "luz_mantener_s": 3,
    }), ("luz", 3.0))
    c.revisar("tecla ausente desactiva", store.luz_a_mantener({
        "apagar_luz_al_encender": True, "btn_luz": "",
    }), None)
    c.revisar("opción desactivada", store.luz_a_mantener({
        "apagar_luz_al_encender": False, "btn_luz": "luz",
    }), None)

    async def escenario():
        mando = store.add_ir_remote("Mando humidificador")
        on = store.add_ir_button(mando["id"], "On", "", "on")
        luz_btn = store.add_ir_button(mando["id"], "Luz", "", "luz")
        cont = store.add_ir_button(mando["id"], "Continuo", "", "cont")
        luz = store.add_light(
            "Humidificador", "", "", "", kind=store.LUZ_MANDO,
            remote_id=mando["id"], btn_on=on["id"], btn_off=on["id"],
            mando_modo=store.UNA_TECLA, modo_encendido="continuo",
            btn_continuo=cont["id"], btn_luz=luz_btn["id"],
            apagar_luz_al_encender=True, luz_mantener_s=3)
        enviados, mantenidas, pausas = [], [], []
        original_send = ops.send_remote_button
        original_sleep = ops.asyncio.sleep
        original_thread = ops.asyncio.to_thread

        async def enviar(remote_id, button_id, **kwargs):
            enviados.append(button_id)
            if kwargs.get("mantener_s") is not None:
                mantenidas.append(kwargs["mantener_s"])

        bloqueada = {"valor": False}
        puerta = asyncio.Event()

        async def dormir(segundos):
            pausas.append(segundos)
            if bloqueada["valor"] and segundos:
                await puerta.wait()
            await original_sleep(0)

        async def en_el_loop(func, *args, **kwargs):
            return func(*args, **kwargs)

        ops.send_remote_button, ops.asyncio.sleep = enviar, dormir
        ops.asyncio.to_thread = en_el_loop
        try:
            await ops.set_light(luz["id"], True)
            c.revisar("vuelve tras encendido", enviados, [on["id"]])
            while ops._LIGHT_BACKGROUND_TASKS:
                await original_sleep(0)
            c.revisar("orden completa", enviados,
                      [on["id"], cont["id"], luz_btn["id"]])
            c.revisar("Luz se mantiene una vez", mantenidas, [3.0])
            c.revisar("pausas entre pasos", pausas, [1.0, 1.0])

            enviados.clear(); pausas.clear()
            await ops.set_light(luz["id"], False)
            bloqueada["valor"] = True
            encender = asyncio.create_task(ops.set_light(luz["id"], True))
            await original_sleep(0)
            apagar = asyncio.create_task(ops.set_light(luz["id"], False))
            await original_sleep(0)
            c.cierto("apagar espera al lock de la secuencia", not apagar.done())
            puerta.set()
            await asyncio.gather(encender, apagar)
            c.revisar("el lock conserva el orden", enviados[:2], [on["id"], on["id"]])
        finally:
            ops.send_remote_button, ops.asyncio.sleep = original_send, original_sleep
            ops.asyncio.to_thread = original_thread
            store.delete_light(luz["id"])
            store.delete_ir_remote(mando["id"])

    asyncio.run(escenario())
    return c


def _mando_directo_y_pulsacion_larga() -> Caso:
    c = Caso("Secuencia al pulsar directamente el mando")
    mando = store.add_ir_remote("Mando directo")
    on = store.add_ir_button(mando["id"], "On", "", "on-code")
    cont = store.add_ir_button(mando["id"], "Continuo", "", "cont-code")
    luz_btn = store.add_ir_button(mando["id"], "Luz", "", "luz-code")
    luz = store.add_light("Humidificador directo", "", "", "",
                          kind=store.LUZ_MANDO, remote_id=mando["id"],
                          btn_on=on["id"], btn_off=on["id"],
                          mando_modo=store.UNA_TECLA, modo_encendido="continuo",
                          btn_continuo=cont["id"], btn_luz=luz_btn["id"],
                          apagar_luz_al_encender=True)
    enviados, mantenidas = [], []
    original_button = ir_bus.send_button
    original_hold = ir_bus.send_hold
    original_thread = ops.asyncio.to_thread

    async def button(code):
        enviados.append(("button", code))

    async def hold(code, segundos):
        enviados.append(("hold", code))
        mantenidas.append(segundos)

    async def en_el_loop(func, *args, **kwargs):
        return func(*args, **kwargs)

    async def escenario():
        await ops.send_remote_button(mando["id"], on["id"])
        while ops._LIGHT_BACKGROUND_TASKS:
            await asyncio.sleep(0)
        c.revisar("mando directo ordena modo y Luz", enviados,
                  [("button", "on-code"), ("button", "cont-code"),
                   ("hold", "luz-code")])
        c.revisar("mando directo mantiene 3 s", mantenidas, [3.0])
        enviados.clear()
        await ops.send_remote_button(mando["id"], on["id"])
        c.revisar("al apagar no lanza continuación", enviados,
                  [("button", "on-code")])

        sim = store.add_ir_remote("Mando simulado")
        store._update("ir_remotes", sim["id"], {"simulado": True})
        sim_btn = store.add_ir_button(sim["id"], "On", "", "sim-code")
        sim_luz = store.add_light("Humidificador simulado", "", "", "",
                                  kind=store.LUZ_MANDO, remote_id=sim["id"],
                                  btn_on=sim_btn["id"], btn_off=sim_btn["id"],
                                  mando_modo=store.UNA_TECLA,
                                  modo_encendido="continuo")
        try:
            enviados.clear()
            await ops.send_remote_button(sim["id"], sim_btn["id"])
            await asyncio.sleep(0)
            c.revisar("mando simulado no envía ni continúa", enviados, [])
            c.revisar("mando simulado sí apunta estado",
                      store.get_sensor_state(sim_luz["id"]), True)
        finally:
            store.delete_light(sim_luz["id"])
            store.delete_ir_remote(sim["id"])

    ir_bus.send_button, ir_bus.send_hold = button, hold
    ops.asyncio.to_thread = en_el_loop
    try:
        asyncio.run(escenario())
    finally:
        ir_bus.send_button, ir_bus.send_hold = original_button, original_hold
        ops.asyncio.to_thread = original_thread
        store.delete_light(luz["id"])
        store.delete_ir_remote(mando["id"])
    return c


def _pulsacion_larga_codigos() -> Caso:
    c = Caso("Construcción de paquetes Broadlink de pulsación larga")

    def empaquetar(unidades):
        payload = bytearray()
        for valor in unidades:
            payload.extend((valor,) if valor <= 255 else (0, valor >> 8, valor & 255))
        return bytes((0x26, 0, len(payload) & 255, len(payload) >> 8)) + payload

    frame = [300, 145, 100, 80, 100, 80, 18, 0x0D05]
    repeat = [300, 70, 18, 0x0D05]
    original = empaquetar(frame + repeat + repeat)
    largo = ir_bus.construir_pulsacion_larga(original.hex(), 3.0)
    datos, unidades = ir_bus._decodificar_codigo(largo)
    c.revisar("conserva cabecera Broadlink", datos[:2].hex(), "2600")
    c.revisar("conserva la trama inicial", unidades[:len(frame)], frame)
    c.revisar("conserva el terminador original", unidades[-1], 0x0D05)
    c.cierto("el paso de las repeticiones es el de la plantilla",
             unidades[len(frame):len(frame) + len(repeat)] == repeat)
    ultimo_inicio = max(i for i in range(0, len(unidades), 2)
                        if unidades[i] >= 200)
    tiempo = sum(unidades[:ultimo_inicio + 1]) * 269 / 8192000
    c.cierto("el tiempo hasta la última marca queda en rango",
             3.0 <= tiempo <= 3.12)
    mas_largo = ir_bus.construir_pulsacion_larga(original.hex(), 6.0)
    c.cierto("más segundos añade repeticiones",
             len(ir_bus._decodificar_codigo(mas_largo)[1]) > len(unidades))
    sin_repeticiones = ir_bus.construir_pulsacion_larga(empaquetar(frame).hex(), 0.5)
    c.cierto("sin repeticiones repite la trama",
             len(ir_bus._decodificar_codigo(sin_repeticiones)[1]) > len(frame))
    for codigo in ("00", "26000100"):
        try:
            ir_bus.construir_pulsacion_larga(codigo, 3)
            c.revisar("hex inválido protesta", "no protestó", "ValueError")
        except ValueError:
            c.cierto("hex inválido protesta", True)
    grande = empaquetar([300] + [1, 100] * 1000 + [1])
    try:
        ir_bus.construir_pulsacion_larga(grande.hex(), 3)
        c.revisar("payload grande protesta", "no protestó", "ValueError")
    except ValueError:
        c.cierto("payload grande protesta", True)
    return c


def _activacion_con_modo() -> Caso:
    """La activación de un aparato temporal no sale nunca de este espía."""
    c = Caso("Activación secuenciada de accesorios")
    mando = store.add_ir_remote("Mando de ciclos")
    on = store.add_ir_button(mando["id"], "ON", "power", "on")
    continuo = store.add_ir_button(mando["id"], "Continuo", "waves", "continuo")
    timing = store.add_ir_button(mando["id"], "Temporizador", "clock", "timing")
    luz = store.add_light(
        "Humidificador de prueba", "", "", "", kind=store.LUZ_MANDO,
        remote_id=mando["id"], btn_on=on["id"], btn_off=on["id"],
        mando_modo=store.UNA_TECLA, btn_continuo=continuo["id"],
        btn_timing=timing["id"], pausa_secuencia_s=1.5,
    )
    enviados, pausas, fallar = [], [], {"indice": None}
    original_enviar = ops.send_remote_button
    original_sleep = ops.asyncio.sleep
    original_thread = ops.asyncio.to_thread
    original_hora = store.time.time
    original_registrar = ops.audit.registrar_sistema

    async def espia(remote_id, button_id, **kwargs):
        enviados.append((remote_id, button_id))
        if fallar["indice"] == len(enviados) - 1:
            raise ops.OperationError("IR no disponible")
        return f"{remote_id} · {button_id}"

    async def dormir(segundos):
        pausas.append(segundos)
        await original_sleep(0)

    async def en_el_loop(func, *args, **kwargs):
        return func(*args, **kwargs)

    def registrar_falso(*args, **kwargs):
        pass

    def ficha():
        return next(x for x in store.read_all()["lights"] if x["id"] == luz["id"])

    async def activar(modo):
        store.set_modo_encendido(luz["id"], modo)
        store.set_mando_state(luz["id"], False)
        enviados.clear()
        pausas.clear()
        await ops.set_light(luz["id"], True)

    async def escenario():
        for modo, teclas, espera, ciclo in (
            ("continuo", [on["id"], continuo["id"]], [1.5], 0),
            ("1h", [on["id"]], [], 60),
            ("2h", [on["id"], timing["id"]], [1.5], 120),
            ("3h", [on["id"], timing["id"], timing["id"]], [1.5, 1.5], 180),
        ):
            await activar(modo)
            c.revisar(f"{modo}: teclas y orden", enviados,
                      [(mando["id"], tecla) for tecla in teclas])
            c.revisar(f"{modo}: pausas", pausas, espera)
            c.revisar(f"{modo}: ciclo guardado", ficha().get("ciclo_min"), ciclo)

        store.time.time = lambda: 100.0
        await activar("2h")
        ops.expirar_accesorios(7299.999)
        c.revisar("2 h: justo antes sigue encendido", store.get_sensor_state(luz["id"]), True)
        ops.expirar_accesorios(7300.0)
        c.revisar("2 h: en el plazo exacto se apaga", store.get_sensor_state(luz["id"]), False)

        store.time.time = lambda: 200.0
        await activar("continuo")
        store.update_light(luz["id"], luz["name"], "", "", "", kind=store.LUZ_MANDO,
                           remote_id=mando["id"], btn_on=on["id"], btn_off=on["id"],
                           mando_modo=store.UNA_TECLA, btn_continuo=continuo["id"],
                           btn_timing=timing["id"], modo_encendido="continuo",
                           auto_apagado_min=1, pausa_secuencia_s=1.5)
        ops.expirar_accesorios(999999.0)
        c.revisar("continuo nunca caduca", store.get_sensor_state(luz["id"]), True)

        store.set_mando_state(luz["id"], False)
        store.set_modo_encendido(luz["id"], "2h")
        enviados.clear()
        fallar["indice"] = 0
        reversiones = []

        async def al_fallar(nuevo, error):
            reversiones.append(nuevo)

        try:
            await ops.set_light(luz["id"], True,
                                on_failed=al_fallar)
        except ops.OperationError:
            pass
        c.revisar("fallo en ON revierte", store.get_sensor_state(luz["id"]), False)
        c.revisar("fallo en ON no sigue la secuencia", enviados, [(mando["id"], on["id"])])
        c.revisar("fallo en ON llama on_failed", reversiones, [True])

        enviados.clear()
        fallar["indice"] = 1
        try:
            await ops.set_light(luz["id"], True)
        except ops.OperationError:
            pass
        c.revisar("fallo posterior conserva ON", store.get_sensor_state(luz["id"]), True)
        c.revisar("fallo posterior conserva ciclo conseguido", ficha().get("ciclo_min"), 60)

        fallar["indice"] = None
        store.set_mando_state(luz["id"], False)
        enviados.clear()
        await asyncio.gather(ops.set_light(luz["id"], True), ops.set_light(luz["id"], True))
        c.revisar("dos encendidos concurrentes mandan una secuencia", enviados,
                  [(mando["id"], on["id"]), (mando["id"], timing["id"])])

        store.set_mando_state(luz["id"], False)
        store.set_modo_encendido(luz["id"], "")
        enviados.clear()
        await ops.set_light(luz["id"], True)
        await ops.set_light(luz["id"], False)
        c.revisar("sin modo y apagar conservan una tecla", enviados,
                  [(mando["id"], on["id"]), (mando["id"], on["id"])])

        store.time.time = lambda: 500.0
        store.set_mando_state(luz["id"], False)
        store.set_modo_encendido(luz["id"], "2h")
        await ops.set_light(luz["id"], True)
        store.set_modo_encendido(luz["id"], "3h")
        c.revisar("cambiar modo encendido no cambia el ciclo", ficha().get("ciclo_min"), 120)
        ops.expirar_accesorios(7699.999)
        c.revisar("ciclo en curso conserva su plazo", store.get_sensor_state(luz["id"]), True)
        ops.expirar_accesorios(7700.0)
        c.revisar("ciclo en curso vence en su plazo original", store.get_sensor_state(luz["id"]), False)

    ops.send_remote_button = espia
    ops.asyncio.sleep = dormir
    ops.asyncio.to_thread = en_el_loop
    ops.audit.registrar_sistema = registrar_falso
    try:
        asyncio.run(escenario())
    finally:
        ops.send_remote_button = original_enviar
        ops.asyncio.sleep = original_sleep
        ops.asyncio.to_thread = original_thread
        ops.audit.registrar_sistema = original_registrar
        store.time.time = original_hora
        store.delete_light(luz["id"])
        store.delete_ir_remote(mando["id"])
    return c


def _webos_directo() -> Caso:
    """Entradas, navegación y apps se despachan por rutas distintas."""
    from noxuscmmd.domains.devices import webos_bus

    c = Caso("Acciones directas de la TV por webOS")

    class TeleFalsa:
        def __init__(self):
            self.llamadas = []

        async def set_input(self, input_id):
            self.llamadas.append(("input", input_id))

        async def button(self, nombre):
            self.llamadas.append(("button", nombre))

        async def launch_app(self, app_id):
            self.llamadas.append(("app", app_id))

    tele = TeleFalsa()

    async def cliente_falso():
        return tele

    original = webos_bus._get_client
    webos_bus._get_client = cliente_falso
    try:
        asyncio.run(webos_bus.send_command("input:HDMI_2"))
        # El prefijo conserva ids opacos: el bus entrega el sufijo intacto a
        # set_input en vez de reinterpretarlo como nombre de aplicación.
        asyncio.run(webos_bus.send_command("input:com.webos.app.hdmi1"))
        asyncio.run(webos_bus.send_command("HOME"))
        asyncio.run(webos_bus.send_command("netflix"))
        c.revisar(
            "cada orden usa el método específico",
            tele.llamadas,
            [("input", "HDMI_2"),
             ("input", "com.webos.app.hdmi1"),
             ("button", "HOME"), ("app", "netflix")],
        )
        opciones = dict(webos_bus.comandos_disponibles())
        for numero in range(1, 5):
            c.cierto(
                f"ofrece HDMI {numero} en el selector",
                f"input:HDMI_{numero}" in opciones,
            )
        try:
            asyncio.run(webos_bus.send_command("input:"))
            c.revisar("una entrada vacía protesta", "no protestó", "RuntimeError")
        except RuntimeError as error:
            c.cierto("una entrada vacía protesta", "HDMI" in str(error))
    finally:
        webos_bus._get_client = original
    return c


def _alta_boton_webos() -> Caso:
    """Un botón de red nace como tal; IR conserva su comportamiento."""
    import inspect

    c = Caso("Alta directa de botones webOS")
    mando = store.add_ir_remote("TV webOS de prueba", "tv", False, "", "vacio")
    try:
        hdmi = store.add_ir_button(
            mando["id"], "HDMI 3", "monitor", "input:HDMI_3", kind="webos")
        infrarrojo = store.add_ir_button(
            mando["id"], "Encender", "power", "codigo-de-prueba")
        c.revisar("el botón de red guarda su vía", hdmi["kind"], "webos")
        c.revisar("el botón de red guarda la entrada", hdmi["code"], "input:HDMI_3")
        c.revisar("el alta anterior sigue siendo IR", infrarrojo["kind"], "ir")

        # Salvaguarda de interfaz: el alta (no solo el editor posterior) tiene
        # que ofrecer webOS y enviar el código elegido al manejador.
        from noxuscmmd.ui.dashboard.views.ir_remotes import _add_button_dialog
        fuente = inspect.getsource(_add_button_dialog)
        c.cierto("Añadir botón ofrece webOS", 'value="webos"' in fuente)
        c.cierto("Añadir botón envía su acción", 'name="webos_code"' in fuente)
    finally:
        store.delete_ir_remote(mando["id"])
    return c


def _una_sola_tecla() -> Caso:
    """La tele: una sola tecla de encendido que hace las dos cosas."""
    c = Caso("Accesorios de una sola tecla")

    tv = store.add_light("Tele del salón", "", "", "", kind=store.LUZ_MANDO,
                         remote_id="ir_tv", btn_on="power", btn_off="",
                         aspecto="tv", mando_modo=store.UNA_TECLA)
    c.revisar("guarda el modo", tv["mando_modo"], store.UNA_TECLA)
    # La misma tecla queda en los dos sitios: así todo el que lea la ficha
    # encuentra una tecla donde la busca.
    c.revisar("copia la tecla en la de apagar", tv["btn_off"], "power")

    vent = store.add_light("Ventilador", "", "", "", kind=store.LUZ_MANDO,
                           remote_id="ir_v", btn_on="on", btn_off="off",
                           aspecto="ventilador", mando_modo=store.DOS_TECLAS)
    c.revisar("con dos teclas cada una es la suya",
              (vent["btn_on"], vent["btn_off"]), ("on", "off"))

    pulsado = []

    async def espia(remote_id, button_id, **kwargs):
        pulsado.append((remote_id, button_id))

    original = ops.send_remote_button
    ops.send_remote_button = espia
    try:
        ficha_tv = {"id": tv["id"], "name": "Tele", "kind": store.LUZ_MANDO,
                    "remote_id": "ir_tv", "btn_on": "power", "btn_off": "power",
                    "mando_modo": store.UNA_TECLA}
        asyncio.run(ops._enviar_por_mando(ficha_tv, True))
        asyncio.run(ops._enviar_por_mando(ficha_tv, False))
        c.revisar("encender y apagar mandan la MISMA tecla",
                  pulsado, [("ir_tv", "power"), ("ir_tv", "power")])

        pulsado.clear()
        ficha_v = {"id": vent["id"], "name": "Ventilador", "kind": store.LUZ_MANDO,
                   "remote_id": "ir_v", "btn_on": "on", "btn_off": "off",
                   "mando_modo": store.DOS_TECLAS}
        asyncio.run(ops._enviar_por_mando(ficha_v, True))
        asyncio.run(ops._enviar_por_mando(ficha_v, False))
        c.revisar("con dos teclas manda cada una la suya",
                  pulsado, [("ir_v", "on"), ("ir_v", "off")])

        sin_tecla = {"id": "x", "name": "Tele a medias", "kind": store.LUZ_MANDO,
                     "remote_id": "ir_tv", "btn_on": "", "btn_off": "",
                     "mando_modo": store.UNA_TECLA}
        try:
            asyncio.run(ops._enviar_por_mando(sin_tecla, True))
            c.revisar("sin tecla protesta", "no protestó", "NotConfigured")
        except ops.NotConfigured as e:
            c.cierto("sin tecla protesta y lo dice en singular",
                     "tecla de encendido" in str(e))
    finally:
        ops.send_remote_button = original

    store.delete_light(tv["id"])
    store.delete_light(vent["id"])
    return c


def _separacion() -> Caso:
    """Los accesorios salen en su pestaña, no entre las bombillas."""
    c = Caso("Accesorios separados de las luces")
    from noxuscmmd.domains.nodes.state import NodesState

    luz = store.add_light("Bombilla prueba", "nodo1", "Nodo Uno", "22")
    tele = store.add_light("Tele prueba", "", "", "", kind=store.LUZ_MANDO,
                           remote_id="ir_1", btn_on="p", btn_off="p",
                           aspecto="tv", mando_modo=store.UNA_TECLA)
    try:
        s = NodesState(_reflex_internal_init=True)
        s.lights = store.read_all()["lights"]
        s.rooms = store.read_all()["rooms"]

        ids_accesorios = {a["id"] for a in s.accesorios}
        c.cierto("la tele sale en Accesorios", tele["id"] in ids_accesorios)
        c.revisar("la bombilla NO sale en Accesorios", luz["id"] in ids_accesorios, False)

        en_luces = {l["id"] for grupo in s.lights_by_room.values() for l in grupo}
        c.cierto("la bombilla sale en Luces", luz["id"] in en_luces)
        c.revisar("la tele NO sale en Luces", tele["id"] in en_luces, False)
        c.cierto("hay_luces detecta que hay bombillas", s.hay_luces)
    finally:
        store.delete_light(luz["id"])
        store.delete_light(tele["id"])
    return c


def _widgets() -> Caso:
    """Que un accesorio y un mando entero se puedan poner en el Resumen."""
    c = Caso("Accesorios y mandos en los widgets del Resumen")
    from noxuscmmd.domains.nodes import referencias

    tele = store.add_light("Tele del salón", "", "", "", kind=store.LUZ_MANDO,
                           remote_id="ir_1", btn_on="p", btn_off="p",
                           aspecto="tv", mando_modo=store.UNA_TECLA)
    try:
        catalogo = referencias._catalogo()
        etiqueta, icono = referencias.etiqueta_widget(
            "action_light", tele["id"], catalogo)
        c.revisar("un accesorio se puede referenciar", etiqueta, "Tele del salón")

        # El mando entero, que es lo que ahora se ofrece en la sección Mandos.
        mandos = store.read_all()["ir_remotes"]
        if mandos:
            mid = mandos[0]["id"]
            etiqueta, icono = referencias.etiqueta_widget(
                "action_ir_remote", mid, catalogo)
            c.revisar("un mando entero se puede referenciar",
                      etiqueta, mandos[0]["name"])
            c.cierto("y trae icono", bool(icono))
            c.cierto("el mando existe para el sincronizador",
                     referencias._existe(mid, "action_ir_remote", catalogo))

        # Las pestañas nuevas tienen que poder referenciarse con "Ir a ...".
        for vista in ("accesorios", "presencia", "instalador"):
            c.cierto(f"la pestaña {vista} es referenciable",
                     referencias._existe(vista, "action_view", catalogo))
    finally:
        store.delete_light(tele["id"])
    return c


def _estado_compartido() -> Caso:
    """Pulsar la tecla del mando tiene que mover el estado del accesorio.

    Es lo que hace que el botón del plano, el del Resumen y el mando digan
    siempre lo mismo, se haya encendido desde donde se haya encendido.
    """
    c = Caso("Estado compartido entre todas las formas de accionar")

    dos = store.add_light("Luz del ventilador", "", "", "", kind=store.LUZ_MANDO,
                          remote_id="ir_x", btn_on="b_on", btn_off="b_off",
                          aspecto="ventilador", mando_modo=store.DOS_TECLAS)
    una = store.add_light("Tele", "", "", "", kind=store.LUZ_MANDO,
                          remote_id="ir_y", btn_on="power", btn_off="power",
                          aspecto="tv", mando_modo=store.UNA_TECLA)
    try:
        def estado(lid):
            return store.read_all().get("sensor_states", {}).get(lid, False)

        store.set_sensor_state(dos["id"], False)
        ops._apuntar_estado_de_accesorios("ir_x", "b_on")
        c.revisar("la tecla de encender lo pone encendido", estado(dos["id"]), True)
        ops._apuntar_estado_de_accesorios("ir_x", "b_off")
        c.revisar("la de apagar lo pone apagado", estado(dos["id"]), False)

        # Con una sola tecla, cada pulsación alterna: es lo que hace el aparato.
        store.set_sensor_state(una["id"], False)
        ops._apuntar_estado_de_accesorios("ir_y", "power")
        c.revisar("la primera pulsación lo enciende", estado(una["id"]), True)
        ops._apuntar_estado_de_accesorios("ir_y", "power")
        c.revisar("la segunda lo apaga", estado(una["id"]), False)

        # Una tecla cualquiera del mismo mando no toca nada.
        store.set_sensor_state(dos["id"], True)
        ops._apuntar_estado_de_accesorios("ir_x", "otra_tecla")
        c.revisar("una tecla que no es suya no lo cambia", estado(dos["id"]), True)
        # Ni una tecla igual pero de OTRO mando.
        ops._apuntar_estado_de_accesorios("ir_z", "b_off")
        c.revisar("ni la misma tecla de otro mando", estado(dos["id"]), True)
    finally:
        store.delete_light(dos["id"])
        store.delete_light(una["id"])
    return c


def _apagado_automatico() -> Caso:
    """El fin de ciclo solo cambia el estado lógico, una vez y sin transporte."""
    c = Caso("Apagado automático de accesorios por mando")
    mando = store.add_light(
        "Humidificador temporal", "", "", "", kind=store.LUZ_MANDO,
        remote_id="ir_temporal", btn_on="power", btn_off="power",
        aspecto="otro", mando_modo=store.UNA_TECLA, auto_apagado_min=1,
    )
    sin_auto = store.add_light(
        "Accesorio sin temporizador", "", "", "", kind=store.LUZ_MANDO,
        remote_id="ir_sin_auto", btn_on="power", btn_off="power",
        aspecto="otro", mando_modo=store.UNA_TECLA, auto_apagado_min=0,
    )
    rele = store.add_light("Relé sin ciclo", "nodo_prueba", "Nodo Prueba", "33")
    eventos = []
    enviados = []
    original_hora = ops.time.time
    original_registrar = ops.audit.registrar_sistema
    original_enviar = ops._enviar_por_mando
    original_to_thread = ops.asyncio.to_thread

    def hora(valor):
        ops.time.time = lambda: valor

    def registrar(*args, **kwargs):
        eventos.append((args, kwargs))

    async def enviar(light, on):
        enviados.append((light["id"], on))

    async def en_el_loop(func, *args, **kwargs):
        return func(*args, **kwargs)

    try:
        ops.audit.registrar_sistema = registrar
        ops._enviar_por_mando = enviar

        hora(100.0)
        ops._apuntar_estado_de_accesorios("ir_temporal", "power")
        c.revisar("al encender guarda el inicio", mando["id"] in {
                  l["id"] for l in store.read_all()["lights"]
                  if l.get("encendido_en") == 100.0}, True)
        ops.expirar_accesorios(159.999)
        c.revisar("justo antes del borde sigue encendido",
                  store.get_sensor_state(mando["id"]), True)
        ops.expirar_accesorios(160.0)
        c.revisar("en el borde exacto se apaga", store.get_sensor_state(mando["id"]), False)
        c.revisar("limpia el inicio al caducar", any(
            l["id"] == mando["id"] and "encendido_en" in l
            for l in store.read_all()["lights"]), False)
        c.revisar("registra un evento de accesorios", len(eventos), 1)
        c.revisar("el evento describe el fin de ciclo",
                  eventos[0][0][1:3], ("ACCESORIO_APAGADO_AUTOMATICO", mando["name"]))
        ops.expirar_accesorios(160.0)
        c.revisar("repetir la caducidad no duplica evento", len(eventos), 1)
        c.revisar("caducar no manda IR", enviados, [])

        hora(200.0)
        ops._apuntar_estado_de_accesorios("ir_sin_auto", "power")
        ops.expirar_accesorios(10000.0)
        c.revisar("cero minutos no cambia nada", store.get_sensor_state(sin_auto["id"]), True)
        store.set_sensor_state(rele["id"], True)
        ops.expirar_accesorios(10000.0)
        c.revisar("solo caducan los accesorios por mando", store.get_sensor_state(rele["id"]), True)

        hora(300.0)
        ops._apuntar_estado_de_accesorios("ir_temporal", "power")
        hora(320.0)
        ops._apuntar_estado_de_accesorios("ir_temporal", "power")
        hora(400.0)
        ops._apuntar_estado_de_accesorios("ir_temporal", "power")
        ops.expirar_accesorios(459.999)
        c.revisar("reencender reinicia el contador", store.get_sensor_state(mando["id"]), True)
        ops.expirar_accesorios(460.0)
        c.revisar("el contador reiniciado vence en su nuevo plazo",
                  store.get_sensor_state(mando["id"]), False)

        hora(500.0)
        ops._apuntar_estado_de_accesorios("ir_temporal", "power")
        hora(561.0)
        ops.asyncio.to_thread = en_el_loop
        asyncio.run(ops.set_light(mando["id"], None))
        c.revisar("set_light tras caducar conmuta desde apagado", enviados[-1:], [(mando["id"], True)])
        c.revisar("la orden posterior deja el accesorio encendido",
                  store.get_sensor_state(mando["id"]), True)
    finally:
        ops.time.time = original_hora
        ops.audit.registrar_sistema = original_registrar
        ops._enviar_por_mando = original_enviar
        ops.asyncio.to_thread = original_to_thread
        store.delete_light(mando["id"])
        store.delete_light(sin_auto["id"])
        store.delete_light(rele["id"])
    return c


def _orden_idempotente() -> Caso:
    """El estado del plano hace idempotentes TODOS los tipos de luz.

    Se sustituyen ambos transportes por espías: ni MQTT/SSH ni un mando real
    pueden recibir nada durante esta prueba. Para relés, mandos con ON/OFF y
    mandos con POWER se exige el mismo contrato: repetir el estado visible no
    actúa; cambiarlo actúa una única vez.
    """
    c = Caso("Estado del plano como verdad para todas las luces")
    rele = store.add_light(
        "Relé idempotente", "nodo_prueba", "Nodo Prueba", "22")
    dos_teclas = store.add_light(
        "Ventilador idempotente", "", "", "", kind=store.LUZ_MANDO,
        remote_id="ir_ventilador", btn_on="luz_on", btn_off="luz_off",
        aspecto="ventilador", mando_modo=store.DOS_TECLAS,
    )
    una_tecla = store.add_light(
        "Tele idempotente", "", "", "", kind=store.LUZ_MANDO,
        remote_id="ir_tv", btn_on="power", btn_off="power",
        aspecto="tv", mando_modo=store.UNA_TECLA,
    )
    luces = (rele, dos_teclas, una_tecla)
    enviados: list[tuple[str, str, bool]] = []

    async def espia_mando(light, on):
        enviados.append(("mando", light["id"], on))

    async def espia_rele(light, on, *_):
        enviados.append(("rele", light["id"], on))

    original_mando = ops._enviar_por_mando
    original_rele = ops._enviar_a_rele
    original_to_thread = ops.asyncio.to_thread

    async def en_el_loop(func, *args, **kwargs):
        # Aquí se prueba la decisión, no el executor. Algunos selectores del
        # entorno de pruebas no despiertan al terminar un hilo si el loop no
        # tiene ningún otro temporizador pendiente, y dejarían asyncio.run()
        # esperando aunque la escritura ya hubiera terminado.
        return func(*args, **kwargs)

    async def escenario():
        for luz in luces:
            via = "mando" if luz["kind"] == store.LUZ_MANDO else "rele"
            store.set_sensor_state(luz["id"], False)

            inicio = len(enviados)
            await ops.set_light(luz["id"], False)
            await ops.set_light(luz["id"], False)
            c.revisar(
                f'{luz["name"]}: repetir apagado no toca el transporte',
                enviados[inicio:], [],
            )

            await ops.set_light(luz["id"], True)
            await ops.set_light(luz["id"], True)
            c.revisar(
                f'{luz["name"]}: encender actúa exactamente una vez',
                enviados[inicio:], [(via, luz["id"], True)],
            )

            await ops.set_light(luz["id"], False)
            await ops.set_light(luz["id"], False)
            c.revisar(
                f'{luz["name"]}: apagar actúa exactamente una vez',
                enviados[inicio:],
                [(via, luz["id"], True), (via, luz["id"], False)],
            )
            c.revisar(
                f'{luz["name"]}: el plano queda apagado',
                store.get_sensor_state(luz["id"]), False,
            )

    ops._enviar_por_mando = espia_mando
    ops._enviar_a_rele = espia_rele
    ops.asyncio.to_thread = en_el_loop
    try:
        asyncio.run(escenario())
    finally:
        ops._enviar_por_mando = original_mando
        ops._enviar_a_rele = original_rele
        ops.asyncio.to_thread = original_to_thread
        for luz in luces:
            store.delete_light(luz["id"])
    return c


def _secuencia_apagar_habitacion() -> Caso:
    """Una secuencia Alexa omite lo apagado y continúa en orden.

    Alexa ejecuta estas acciones mediante el mismo motor de automatizaciones.
    Se llama directamente a ese motor con una casa temporal y transportes
    espía: los pasos ya satisfechos cuentan como correctos, pero no emiten una
    orden; los que estaban encendidos se apagan en el orden declarado.
    """
    from noxuscmmd.domains.automations import engine

    c = Caso("Apagar habitación desde una secuencia Alexa")
    rele_apagado = store.add_light(
        "Relé ya apagado", "nodo_prueba", "Nodo Prueba", "31")
    tele_encendida = store.add_light(
        "Tele encendida", "", "", "", kind=store.LUZ_MANDO,
        remote_id="ir_tv", btn_on="power", btn_off="power",
        aspecto="tv", mando_modo=store.UNA_TECLA,
    )
    ventilador_apagado = store.add_light(
        "Ventilador ya apagado", "", "", "", kind=store.LUZ_MANDO,
        remote_id="ir_ventilador", btn_on="on", btn_off="off",
        aspecto="ventilador", mando_modo=store.DOS_TECLAS,
    )
    rele_encendido = store.add_light(
        "Relé encendido", "nodo_prueba", "Nodo Prueba", "32")
    luces = (rele_apagado, tele_encendida, ventilador_apagado, rele_encendido)
    enviados: list[tuple[str, str, bool]] = []

    async def espia_mando(light, on):
        enviados.append(("mando", light["id"], on))

    async def espia_rele(light, on, *_):
        enviados.append(("rele", light["id"], on))

    async def en_el_loop(func, *args, **kwargs):
        return func(*args, **kwargs)

    pasos = [{
        "type": "light.set",
        "target": f'light:{luz["id"]}',
        "params": {"on": "off"},
        "continue_on_error": True,
        "timeout": 2,
    } for luz in luces]
    regla = {"actions": pasos}

    original_mando = ops._enviar_por_mando
    original_rele = ops._enviar_a_rele
    original_to_thread = ops.asyncio.to_thread
    ops._enviar_por_mando = espia_mando
    ops._enviar_a_rele = espia_rele
    ops.asyncio.to_thread = en_el_loop
    try:
        store.set_sensor_state(rele_apagado["id"], False)
        store.set_sensor_state(tele_encendida["id"], True)
        store.set_sensor_state(ventilador_apagado["id"], False)
        store.set_sensor_state(rele_encendido["id"], True)

        hechos, errores = asyncio.run(engine._ejecutar_pasos(regla))
        c.revisar("los cuatro pasos continúan y terminan", (hechos, errores), (4, []))
        c.revisar(
            "solo actúa sobre lo que el plano mostraba encendido y en orden",
            enviados,
            [("mando", tele_encendida["id"], False),
             ("rele", rele_encendido["id"], False)],
        )
        c.revisar(
            "todos terminan apagados en el plano",
            [store.get_sensor_state(luz["id"]) for luz in luces],
            [False, False, False, False],
        )
    finally:
        ops._enviar_por_mando = original_mando
        ops._enviar_a_rele = original_rele
        ops.asyncio.to_thread = original_to_thread
        for luz in luces:
            store.delete_light(luz["id"])
    return c


def _sin_doble_contabilidad() -> Caso:
    """Encender desde el propio botón NO debe apuntar el estado dos veces.

    Con un accesorio de UNA sola tecla, la segunda escritura alternaba lo que
    acababa de escribir la primera y el botón se quedaba siempre al revés: la
    tele salía permanentemente encendida y el ventilador permanentemente
    apagado.
    """
    c = Caso("Sin doble contabilidad del estado")
    import inspect

    firma = inspect.signature(ops.send_remote_button)
    c.cierto("send_remote_button admite no apuntar",
             "apuntar_estado" in firma.parameters)
    c.revisar("y por defecto SÍ apunta (pulsar la tecla coordina)",
              firma.parameters["apuntar_estado"].default, True)

    fuente = (inspect.getsource(ops._enviar_por_mando)
              + inspect.getsource(ops._pulsar_tecla_mando))
    c.cierto("el envío desde el accesorio pide NO apuntar",
             "apuntar_estado=False" in fuente)
    return c


def _familias() -> Caso:
    """Un accesorio no puede salir bajo «Luces» en ningún sitio."""
    c = Caso("Accesorios fuera de la familia Luces")
    from noxuscmmd.domains.nodes.state import NodesState

    luz = store.add_light("Bombilla", "nodo1", "Nodo Uno", "22")
    tele = store.add_light("Tele", "", "", "", kind=store.LUZ_MANDO,
                           remote_id="ir_1", btn_on="p", btn_off="p",
                           aspecto="tv", mando_modo=store.UNA_TECLA)
    try:
        c.cierto("existe la familia Accesorios",
                 any(f[0] == "accesorios" for f in store.ACTION_FAMILIES))

        s = NodesState(_reflex_internal_init=True)
        s.lights = store.read_all()["lights"]
        s.widgets = [
            {"kind": "action_light", "target_id": luz["id"], "label": "Bombilla"},
            {"kind": "action_light", "target_id": tele["id"], "label": "Tele"},
        ]
        por_familia = s.actions_by_family
        ids_luces = {w["target_id"] for w in por_familia.get("luces", [])}
        ids_acc = {w["target_id"] for w in por_familia.get("accesorios", [])}

        c.cierto("la bombilla va a Luces", luz["id"] in ids_luces)
        c.revisar("la tele NO va a Luces", tele["id"] in ids_luces, False)
        c.cierto("la tele va a Accesorios", tele["id"] in ids_acc)

        # Y el contador de luces tampoco los cuenta.
        c.revisar("el contador de Luces solo cuenta luces",
                  s.total_luces,
                  sum(1 for l in s.lights if (l.get("aspecto") or "luz") == "luz"))
    finally:
        store.delete_light(luz["id"])
        store.delete_light(tele["id"])
    return c


def _familia_mandos() -> Caso:
    """Un mando va a Mandos, nunca a «Otros».

    Pasó con el widget de mando entero recién añadido: al no estar en la tabla
    de familias caía en el cajón de sastre.
    """
    c = Caso("Los mandos en su familia")
    c.revisar("el mando entero va a Mandos",
              store.familia_de("action_ir_remote"), "mandos")
    c.revisar("una tecla suelta también", store.familia_de("action_ir_button"), "mandos")

    # Y ninguna acción conocida debería acabar en «otros» por olvido: si se
    # añade un kind nuevo, esta lista obliga a decidir dónde va.
    esperadas = {
        "action_arm": "alarma", "action_group": "alarma", "action_light": "luces",
        "action_door": "puertas", "action_camera": "camaras",
        "action_ir_button": "mandos", "action_ir_remote": "mandos",
        "action_rdp": "equipos", "action_host_button": "equipos",
        "action_host_shutdown": "equipos", "action_host_wol": "equipos",
    }
    for kind, familia in esperadas.items():
        c.revisar(f"{kind} -> {familia}", store.familia_de(kind), familia)
    return c


def _plantilla_humidificador() -> Caso:
    """La plantilla del humidificador: sin señal, sin solapes y con la tecla
    que usa el accesorio."""
    from noxuscmmd.domains.devices import remote_templates as rt

    c = Caso("Plantilla del humidificador")
    botones = rt.botones("humidificador")
    etiquetas = [b["label"] for b in botones]
    c.cierto("está en el desplegable", "humidificador" in dict(rt.opciones()))
    c.revisar("seis teclas", len(botones), 6)
    c.cierto("todos los botones sin señal", all(not b["code"] for b in botones))
    c.cierto("etiquetas únicas", len(set(etiquetas)) == len(etiquetas))
    c.cierto("sin placas de grupo", not rt.grupos("humidificador"))
    c.cierto("existe «Encender / Apagar»", "Encender / Apagar" in etiquetas)
    c.revisar("icono sugerido", rt.icono_sugerido("humidificador"), "droplets")
    ancho, alto = rt.cuerpo("humidificador")
    pos = [(float(b["pos_left"][:-1]) * ancho / 100,
            float(b["pos_top"][:-1]) * alto / 100) for b in botones]
    solapes = [
        (etiquetas[i], etiquetas[j])
        for i in range(len(pos)) for j in range(i + 1, len(pos))
        if abs(pos[i][0] - pos[j][0]) < 44 and abs(pos[i][1] - pos[j][1]) < 44
    ]
    c.revisar("ninguna tecla se solapa", solapes, [])
    return c
