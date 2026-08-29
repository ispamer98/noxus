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
                                  btn_on="b1", btn_off="b2", aspecto="tv")
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


def ejecutar() -> list[Caso]:
    return [_almacen(), _envio(), _una_sola_tecla(), _separacion(), _widgets(),
            _estado_compartido(), _orden_idempotente(),
            _secuencia_apagar_habitacion(), _sin_doble_contabilidad(), _familias(),
            _familia_mandos(), _webos_directo(), _alta_boton_webos()]


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

    async def espia_rele(light, on, ssh):
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

    async def espia_rele(light, on, ssh):
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

    fuente = inspect.getsource(ops._enviar_por_mando)
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
