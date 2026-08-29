"""Contrato local de la Smart Home Skill oficial, sin red ni hardware."""
import asyncio
import json
import time
from tests.comun import Caso

from noxuscmmd.domains.devices import (
    alexa_catalog_store, alexa_cloud, alexa_cloud_endpoint,
    alexa_cloud_store, alexa_cloud_sync, comandos,
)
from noxuscmmd.domains.entities import catalog as entities_catalog, service as entities_service
from noxuscmmd.domains.automations import store as automations_store
from noxuscmmd.domains.nodes import store as nodes_store
from noxuscmmd.domains.nodes import operations as node_operations
from noxuscmmd.domains.security import logs, logs_store


def _directiva(endpoint_id: str, namespace: str, nombre: str) -> dict:
    return {"directive": {
        "header": {"namespace": namespace, "name": nombre,
                   "payloadVersion": "3", "messageId": "mensaje-prueba",
                   "correlationToken": "correlacion-prueba"},
        "endpoint": {"endpointId": endpoint_id,
                     "scope": {"type": "BearerToken", "token": "token-prueba"}},
        "payload": {},
    }}


def _acciones_prueba() -> tuple[dict, dict, dict]:
    todos = [item for item in comandos.comandos()
             if item.get("alexa_allowed", False)]
    encender = next((item for item in todos
                     if item["paso"].get("type") == "light.set" and
                     item["paso"].get("params", {}).get("on") == "on"), todos[0])
    apagar = next((item for item in todos
                   if item["paso"].get("type") == "light.set" and
                   item["paso"].get("params", {}).get("on") == "off"), todos[-1])
    pulso = next((item for item in todos
                  if item["paso"].get("type") == "ir_button.press"), encender)
    return encender, apagar, pulso


def _protocolo() -> Caso:
    c = Caso("Alexa cloud: catálogo manual, escenas, estados y OAuth")
    # ARCHIVO apunta a la casa temporal que crea tests/ejecutar.py.
    alexa_catalog_store.ARCHIVO.unlink(missing_ok=True)
    encender, apagar, pulso = _acciones_prueba()
    ids_catalogo = {item["id"] for item in comandos.comandos()}
    ids_botones = {f"host_button:{item['id']}"
                   for item in nodes_store.read_all().get("host_buttons", [])}
    c.cierto("todos los botones personalizados de equipos son seleccionables",
             ids_botones <= ids_catalogo)
    try:
        node_operations._salida_ssh("ERROR: sin conexión")
    except node_operations.OperationError:
        error_ssh_visible = True
    else:
        error_ssh_visible = False
    c.cierto("un fallo SSH no se confirma a Alexa como éxito", error_ssh_visible)

    power = alexa_catalog_store.añadir(
        name="Interruptor Prueba", behavior="power", category="LIGHT",
        on_command=encender["id"], off_command=apagar["id"],
    )
    repeticiones = 3 if pulso["paso"].get("type") == "ir_button.press" else 1
    accion = alexa_catalog_store.añadir(
        name="Volumen Prueba", behavior="action", command=pulso["id"],
        repeat=repeticiones, repeat_pause=0.5,
    )
    accion_apagar = alexa_catalog_store.añadir(
        name="Todo Noxus Prueba", behavior="action", command=pulso["id"],
        scene_operation="deactivate", repeat=1, repeat_pause=0.4,
    )
    c.revisar("las acciones antiguas conservan activar por defecto",
              accion["scene_operation"], "activate")
    c.revisar("una acción puede publicarse expresamente para apagar",
              alexa_catalog_store.obtener(accion_apagar["id"])["scene_operation"],
              "deactivate")

    respuesta = alexa_cloud.discovery_response()
    items = respuesta["event"]["payload"]["endpoints"]
    c.revisar("usa Discover.Response v3", respuesta["event"]["header"]["name"],
              "Discover.Response")
    c.revisar("solo publica las tres fichas creadas a mano", len(items), 3)
    c.cierto("ya no genera ids automáticos de luces o equipos", all(
        item["endpointId"].startswith("noxus:manual:") for item in items))
    c.cierto("la migración sabe retirar los ids automáticos anteriores", all(
        endpoint_id.startswith(("noxus.light.", "noxus.host."))
        for endpoint_id in alexa_cloud.legacy_endpoint_ids()))

    power_api = next(item for item in items
                     if item["friendlyName"] == "Interruptor Prueba")
    scene_api = next(item for item in items
                     if item["friendlyName"] == "Volumen Prueba")
    scene_apagar_api = next(item for item in items
                            if item["friendlyName"] == "Todo Noxus Prueba")
    c.cierto("el dispositivo declara PowerController", "Alexa.PowerController" in {
        cap["interface"] for cap in power_api["capabilities"]})
    c.cierto("el estado físico desconocido no se declara recuperable", not next(
        cap for cap in power_api["capabilities"]
        if cap["interface"] == "Alexa.PowerController")["properties"]["retrievable"])
    c.cierto("la acción declara SceneController", "Alexa.SceneController" in {
        cap["interface"] for cap in scene_api["capabilities"]})
    scene_cap = next(cap for cap in scene_api["capabilities"]
                     if cap["interface"] == "Alexa.SceneController")
    scene_apagar_cap = next(cap for cap in scene_apagar_api["capabilities"]
                            if cap["interface"] == "Alexa.SceneController")
    c.revisar("activar no anuncia desactivación", scene_cap["supportsDeactivation"],
              False)
    c.revisar("apagar anuncia Deactivate a Alexa",
              scene_apagar_cap["supportsDeactivation"], True)
    c.cierto("una escena no finge EndpointHealth", "Alexa.EndpointHealth" not in {
        cap["interface"] for cap in scene_api["capabilities"]})

    endpoint_power = power_api["endpointId"]
    endpoint_accion = scene_api["endpointId"]
    endpoint_apagar = scene_apagar_api["endpointId"]
    c.revisar("TurnOn resuelve la acción elegida",
              alexa_cloud_endpoint._orden(endpoint_power, "on")[0], encender["id"])
    c.revisar("TurnOff resuelve una acción independiente",
              alexa_cloud_endpoint._orden(endpoint_power, "off")[0], apagar["id"])
    c.revisar("una escena conserva las repeticiones configuradas",
              alexa_cloud_endpoint._orden(endpoint_accion, "activate")[1],
              repeticiones)
    c.revisar("la escena de apagado resuelve su secuencia con Deactivate",
              alexa_cloud_endpoint._orden(endpoint_apagar, "deactivate")[0],
              pulso["id"])
    try:
        alexa_cloud_endpoint._orden(endpoint_apagar, "activate")
    except Exception:
        activacion_rechazada = True
    else:
        activacion_rechazada = False
    c.cierto("encender no dispara por error una escena de apagado",
             activacion_rechazada)

    contexto = alexa_cloud.context(endpoint_power, encendido=True)
    c.revisar("la respuesta a encender confirma salud y potencia",
              {prop["namespace"] for prop in contexto["properties"]},
              {"Alexa.EndpointHealth", "Alexa.PowerController"})
    estado = alexa_cloud.state_report(
        _directiva(endpoint_power, "Alexa", "ReportState"), endpoint_power)
    c.revisar("ReportState usa StateReport", estado["event"]["header"]["name"],
              "StateReport")
    c.revisar("ReportState no inventa potencia sin telemetría",
              {prop["namespace"] for prop in estado["context"]["properties"]},
              {"Alexa.EndpointHealth"})
    escena = alexa_cloud.scene_response(
        _directiva(endpoint_accion, "Alexa.SceneController", "Activate"))
    c.revisar("una escena responde ActivationStarted",
              escena["event"]["header"]["name"], "ActivationStarted")
    c.revisar("la respuesta conserva el scope OAuth del endpoint",
              escena["event"]["endpoint"]["scope"]["token"], "token-prueba")
    escena_apagar = alexa_cloud.scene_response(
        _directiva(endpoint_apagar, "Alexa.SceneController", "Deactivate"),
        activar=False)
    c.revisar("una escena de apagado responde DeactivationStarted",
              escena_apagar["event"]["header"]["name"],
              "DeactivationStarted")

    # El endpoint HTTP se prueba con firma, cuenta y programador sustituidos.
    # La fábrica capturada NO se ejecuta: ninguna orden alcanza hardware.
    class PeticionFalsa:
        def __init__(self, payload: dict):
            self.payload = json.dumps(payload).encode()

        async def body(self):
            return self.payload

    firma_real = alexa_cloud_endpoint._firma_valida
    cuenta_real = alexa_cloud_store.cuenta_de_token
    puede_real = alexa_cloud_endpoint.permisos.puede
    tarea_real = alexa_cloud_endpoint._tarea_unica
    tareas = []
    try:
        alexa_cloud_endpoint._firma_valida = lambda _request, _body: True
        alexa_cloud_store.cuenta_de_token = lambda _token: "admin_prueba"
        alexa_cloud_endpoint.permisos.puede = lambda _cuenta, _permiso: True

        def capturar_tarea(message_id, fabrica):
            tareas.append((message_id, fabrica))
            return None

        alexa_cloud_endpoint._tarea_unica = capturar_tarea
        respuesta_apagar = asyncio.run(alexa_cloud_endpoint.directiva(
            PeticionFalsa(_directiva(
                endpoint_apagar, "Alexa.SceneController", "Deactivate"))))
        cuerpo_apagar = json.loads(respuesta_apagar.body)
        c.revisar("Deactivate programa la acción configurada una sola vez",
                  (cuerpo_apagar["event"]["header"]["name"], len(tareas)),
                  ("DeactivationStarted", 1))

        respuesta_erronea = asyncio.run(alexa_cloud_endpoint.directiva(
            PeticionFalsa(_directiva(
                endpoint_apagar, "Alexa.SceneController", "Activate"))))
        cuerpo_erroneo = json.loads(respuesta_erronea.body)
        c.revisar("Activate contrario devuelve error sin crear otra tarea",
                  (cuerpo_erroneo["event"]["payload"]["type"], len(tareas)),
                  ("INVALID_DIRECTIVE", 1))
    finally:
        alexa_cloud_endpoint._firma_valida = firma_real
        alexa_cloud_store.cuenta_de_token = cuenta_real
        alexa_cloud_endpoint.permisos.puede = puede_real
        alexa_cloud_endpoint._tarea_unica = tarea_real

    editado = alexa_catalog_store.editar(
        power["id"], name="Interruptor Editado", behavior="power", category="TV",
        on_command=encender["id"], off_command=apagar["id"])
    c.revisar("editar conserva el id publicado", editado["id"], power["id"])
    try:
        alexa_catalog_store.añadir(
            name="Interruptor Editado", behavior="power", category="TV",
            on_command=encender["id"], off_command=apagar["id"])
    except alexa_catalog_store.CatalogoAlexaError:
        duplicado_rechazado = True
    else:
        duplicado_rechazado = False
    c.cierto("rechaza nombres que Alexa no podría distinguir", duplicado_rechazado)
    try:
        alexa_catalog_store.añadir(
            name="Accion Invalida", behavior="action", command="no-existe")
    except alexa_catalog_store.CatalogoAlexaError:
        referencia_rechazada = True
    else:
        referencia_rechazada = False
    c.cierto("rechaza referencias a acciones inexistentes", referencia_rechazada)
    maximo_real = alexa_catalog_store.ELEMENTOS_MAXIMOS
    alexa_catalog_store.ELEMENTOS_MAXIMOS = 2
    try:
        try:
            alexa_catalog_store.añadir(
                name="Tercer Elemento", behavior="action", command=pulso["id"])
        except alexa_catalog_store.CatalogoAlexaError:
            maximo_respetado = True
        else:
            maximo_respetado = False
    finally:
        alexa_catalog_store.ELEMENTOS_MAXIMOS = maximo_real
    c.cierto("respeta el máximo de elementos admitido por Amazon", maximo_respetado)

    entidades = entities_catalog.all_entities({}, alexa_endpoints=[power, accion])
    c.revisar("los elementos Alexa comparten el contrato global",
              {item["entity_family"] for item in entidades}, {"alexa"})

    informe = alexa_cloud.add_or_update_report(items, "token-de-amazon")
    c.revisar("altas y cambios usan AddOrUpdateReport",
              informe["event"]["header"]["name"], "AddOrUpdateReport")
    baja = alexa_cloud.delete_report([endpoint_power], "token-de-amazon")
    c.revisar("bajas usan DeleteReport", baja["event"]["header"]["name"],
              "DeleteReport")

    enviados = []
    enviar_real = alexa_cloud_sync._enviar

    async def capturar(payload, token):
        enviados.append(payload)
        return token == "event-token"

    alexa_cloud_store.guardar_eventos(
        "cuenta_sync", "event-token", "refresh-token", time.time() + 3600)
    alexa_cloud_sync._enviar = capturar
    lote_real = alexa_cloud_sync.ELEMENTOS_POR_INFORME
    alexa_cloud_sync.ELEMENTOS_POR_INFORME = 1
    try:
        asyncio.run(alexa_cloud_sync.sincronizar_cuenta("cuenta_sync"))
    finally:
        alexa_cloud_sync.ELEMENTOS_POR_INFORME = lote_real
        alexa_cloud_sync._enviar = enviar_real
    nombres_enviados = {item["event"]["header"]["name"] for item in enviados}
    c.cierto("la sincronización proactiva publica el catálogo manual",
             "AddOrUpdateReport" in nombres_enviados)
    c.revisar("divide los informes grandes antes de enviarlos",
              sum(item["event"]["header"]["name"] == "AddOrUpdateReport"
                  for item in enviados), 3)
    if alexa_cloud.legacy_endpoint_ids():
        c.cierto("la primera sincronización retira los endpoints automáticos",
                 "DeleteReport" in nombres_enviados)
        c.cierto("las bajas históricas se envían de una en una", all(
            len(item["event"]["payload"]["endpoints"]) == 1
            for item in enviados
            if item["event"]["header"]["name"] == "DeleteReport"))
    c.cierto("la retirada antigua queda marcada y no se repite",
             alexa_cloud_store.eventos()["cuenta_sync"].get("legacy_retirados"))

    c.cierto("el borrado global conoce los elementos Alexa",
             entities_service.delete("alexa_endpoints", accion["id"]))
    c.revisar("la baja global desaparece del catálogo Alexa",
              alexa_catalog_store.obtener(accion["id"]), None)

    codigo = alexa_cloud_store.emitir_codigo("admin_prueba", "https://retorno.example")
    par = alexa_cloud_store.canjear_codigo(codigo, "https://retorno.example")
    c.cierto("código OAuth se canjea una vez", par is not None)
    c.revisar("un código OAuth no se puede reutilizar",
              alexa_cloud_store.canjear_codigo(codigo, "https://retorno.example"), None)
    if par:
        access, refresh = par
        c.revisar("token identifica la cuenta", alexa_cloud_store.cuenta_de_token(access),
                  "admin_prueba")
        c.cierto("refresh produce un par nuevo", alexa_cloud_store.renovar(refresh) is not None)
        c.revisar("el access token OAuth dura una hora",
                  alexa_cloud_store.CADUCA_TOKEN, 3600)
        c.cierto("el refresh dura más que el access token",
                 alexa_cloud_store.CADUCA_REFRESH > alexa_cloud_store.CADUCA_TOKEN)

    c.cierto("las credenciales de eventos se guardan fuera del repositorio",
             alexa_cloud_sync.guardar_credenciales("id-prueba", "secreto-prueba"))
    c.cierto("las credenciales quedan disponibles para el grant",
             alexa_cloud_sync.eventos_configurados())
    enlace = alexa_cloud_store.emitir_autorizacion("admin_prueba")
    c.revisar("el código de enlace identifica al administrador",
              alexa_cloud_store.canjear_autorizacion(enlace), "admin_prueba")
    c.revisar("el código de enlace no se reutiliza",
              alexa_cloud_store.canjear_autorizacion(enlace), None)
    alexa_cloud_store.guardar_diagnostico("prueba", "sin secretos")
    c.revisar("el diagnóstico cloud no conserva secretos",
              alexa_cloud_store.diagnostico().get("detalle"), "sin secretos")

    alexa_catalog_store.ARCHIVO.write_text("{")
    try:
        alexa_cloud.endpoints()
    except alexa_catalog_store.ArchivoCorrupto:
        corrupcion_visible = True
    else:
        corrupcion_visible = False
    c.cierto("un JSON dañado nunca se interpreta como borrar todo", corrupcion_visible)
    alexa_catalog_store.ARCHIVO.unlink(missing_ok=True)
    return c


def ejecutar() -> list[Caso]:
    return [_protocolo(), _registro_de_actuaciones(), _secuencias_combinadas()]


def _registro_de_actuaciones() -> Caso:
    """Alexa deja una sola huella por orden sin ejecutar hardware real."""
    c = Caso("Alexa cloud: registro de actuaciones")
    antes_rebote = logs_store.contar()
    logs.registrar(logs.SISTEMA, "REBOTE_DE_PRUEBA", "sistema", "mismo mensaje")
    logs.registrar(logs.SISTEMA, "REBOTE_DE_PRUEBA", "sistema", "mismo mensaje")
    c.revisar("el rebote inmediato del sistema se sigue agrupando",
              logs_store.contar(), antes_rebote + 1)
    comando = {
        "id": "prueba:boton-alexa",
        "etiqueta": "Botón ficticio",
        "grupo": "Pruebas",
        "paso": {
            "type": "ir_button.press",
            "target": "remote:prueba:boton:prueba",
            "params": {},
        },
        "alexa_allowed": True,
    }
    comandos_real = comandos.comandos
    dispatch_real = alexa_cloud_endpoint.actions.dispatch
    endpoint = None
    llamadas = []

    async def completar(paso):
        llamadas.append(paso)
        return "acción simulada"

    try:
        # El catálogo y el ejecutor ven exclusivamente este comando falso. El
        # dispatch parcheado es la barrera que garantiza que nada alcance IR,
        # MQTT, SSH ni ningún otro dispositivo de la casa.
        comandos.comandos = lambda: [comando]
        alexa_cloud_endpoint.actions.dispatch = completar
        endpoint = alexa_catalog_store.añadir(
            name="Escena Registro Alexa", behavior="action",
            command=comando["id"], repeat=3, repeat_pause=0,
        )
        endpoint_id = alexa_cloud.PREFIJO_MANUAL + endpoint["id"]
        antes = logs_store.contar()

        asyncio.run(alexa_cloud_endpoint._ejecutar(
            endpoint_id, "activate", "admin_prueba"))
        exito = logs_store.ultimos(1)[0]
        c.revisar("las tres repeticiones ejecutan tres veces el comando",
                  len(llamadas), 3)
        c.revisar("una orden repetida añade una sola fila",
                  logs_store.contar(), antes + 1)
        c.revisar("la actuación se clasifica como comando por voz",
                  (exito["categoria"], exito["accion"]),
                  (logs.SISTEMA, "COMANDO_POR_VOZ"))
        c.revisar("el origen del registro es Alexa", exito["usuario"], "Alexa")
        c.cierto("el éxito identifica elemento, operación y comando", all(
            texto in exito["detalle"] for texto in (
                "Escena Registro Alexa", "Ejecutar", "Botón ficticio")))

        # No es un reintento de Amazon dentro de la misma tarea: es una segunda
        # petición real e idéntica. Las actuaciones humanas/Alexa no son ruido
        # de sensor y las dos tienen que quedar en el histórico.
        asyncio.run(alexa_cloud_endpoint._ejecutar(
            endpoint_id, "activate", "admin_prueba"))
        c.revisar("dos órdenes iguales conservan dos registros",
                  logs_store.contar(), antes + 2)

        async def fallar(_paso):
            raise alexa_cloud_endpoint.actions.ActionError("fallo simulado")

        alexa_cloud_endpoint.actions.dispatch = fallar
        try:
            asyncio.run(alexa_cloud_endpoint._ejecutar(
                endpoint_id, "activate", "admin_prueba"))
        except alexa_cloud_endpoint.actions.ActionError:
            relanzado = True
        else:
            relanzado = False
        fallo = logs_store.ultimos(1)[0]
        c.cierto("el fallo vuelve al protocolo Alexa", relanzado)
        c.revisar("el fallo también añade exactamente una fila",
                  logs_store.contar(), antes + 3)
        c.revisar("el fallo conserva el origen Alexa", fallo["usuario"], "Alexa")
        c.cierto("el registro explica el fallo", all(
            texto in fallo["detalle"]
            for texto in ("Escena Registro Alexa", "FALLÓ", "fallo simulado")))
    finally:
        alexa_cloud_endpoint.actions.dispatch = dispatch_real
        comandos.comandos = comandos_real
        if endpoint:
            alexa_catalog_store.borrar(endpoint["id"])
    return c


def _secuencias_combinadas() -> Caso:
    """Una orden ON/OFF puede apuntar a varios pasos sin tocar hardware."""
    from noxuscmmd.domains.automations.state import ACCIONES, AutomationsState
    from noxuscmmd.domains.devices.voz_state import VozState

    c = Caso("Alexa cloud: secuencias combinadas seguras")
    pasos = [
        {"type": "wait", "target": "", "params": {"seconds": 1},
         "continue_on_error": True},
        {"type": "log", "target": "", "params": {"text": "paso dos"},
         "repeat": 2, "repeat_pause": 0.25, "continue_on_error": True},
    ]
    segura = automations_store.add_rule(
        name="Apagar habitación prueba", enabled=False,
        triggers=[], conditions=[], actions=pasos,
    )
    insegura = automations_store.add_rule(
        name="Secuencia insegura prueba", enabled=False,
        triggers=[], conditions=[], actions=[{
            "type": "door.pulse", "target": "door:prueba",
            "params": {"seconds": 1},
        }],
    )
    endpoint = None
    try:
        guardada = automations_store.get_rule(segura["id"])
        c.revisar("conserva el orden de los pasos",
                  [p["type"] for p in guardada["actions"]], ["wait", "log"])
        c.revisar("conserva repeticiones y pausa",
                  (guardada["actions"][1]["repeat"],
                   guardada["actions"][1]["repeat_pause"]), (2, 0.25))

        todos = {item["id"]: item for item in comandos.comandos()}
        seguro_id = f"regla:{segura['id']}"
        inseguro_id = f"regla:{insegura['id']}"
        c.cierto("la secuencia segura aparece para Alexa",
                 todos[seguro_id]["alexa_allowed"])
        c.revisar("una puerta escondida sigue bloqueada",
                  todos[inseguro_id]["alexa_allowed"], False)
        c.revisar("habilitar reglas no abre una vía indirecta",
                  comandos.paso_permitido_alexa({
                      "type": "rule.enable", "target": f"rule:{insegura['id']}"
                  }), False)

        endpoint = alexa_catalog_store.añadir(
            name="Habitacion Combinada Prueba", behavior="power", category="LIGHT",
            on_command=seguro_id, off_command=seguro_id,
        )
        endpoint_id = alexa_cloud.PREFIJO_MANUAL + endpoint["id"]
        c.revisar("la secuencia puede ocupar la orden de apagar",
                  alexa_cloud_endpoint._orden(endpoint_id, "off")[0], seguro_id)

        voz = VozState(_reflex_internal_init=True)
        voz.alexa_editando = "nuevo"
        voz.alexa_nombre = "Habitación"
        voz.suspender_editor_alexa("off")
        c.cierto("volver selecciona la secuencia creada",
                 voz.reanudar_con_secuencia(segura["id"]))
        c.revisar("la coloca exactamente en APAGAR",
                  voz.alexa_off_command, seguro_id)
        c.revisar("y conserva abierta la ficha Alexa",
                  voz.editor_alexa_abierto, True)

        voz.alexa_comportamiento = "action"
        voz.alexa_scene_operation = "deactivate"
        c.revisar("el editor muestra la orden principal de apagar",
                  voz.alexa_frase_accion_principal,
                  "Alexa, apaga Habitación")
        c.revisar("y muestra desactivar como alternativa de Alexa",
                  voz.alexa_frase_accion_alternativa,
                  "Alexa, desactiva Habitación")
        voz.alexa_scene_operation = "activate"
        c.revisar("el mismo editor conserva las acciones de activar",
                  (voz.alexa_frase_accion_principal,
                   voz.alexa_frase_accion_alternativa),
                  ("Alexa, enciende Habitación",
                   "Alexa, activa Habitación"))

        auto = AutomationsState(_reflex_internal_init=True)
        auto._reload()
        auto.desde_alexa = True
        auto.picker_for = ACCIONES
        tipos = {opcion["kind"] for seccion in auto.picker_sections
                 for opcion in seccion["options"]}
        c.cierto("el constructor ofrece pasos seguros", "wait" in tipos)
        c.revisar("el constructor oculta puertas", "door.pulse" in tipos, False)
        c.revisar("el constructor oculta armado", "system.arm" in tipos, False)
        c.revisar("el constructor oculta activar reglas", "rule.enable" in tipos, False)

        try:
            alexa_catalog_store.añadir(
                name="Combinada Insegura Prueba", behavior="power",
                category="LIGHT", on_command=inseguro_id, off_command=inseguro_id,
            )
        except alexa_catalog_store.CatalogoAlexaError:
            rechazo = True
        else:
            rechazo = False
        c.cierto("el store vuelve a validar una secuencia manipulada", rechazo)
    finally:
        if endpoint:
            alexa_catalog_store.borrar(endpoint["id"])
        automations_store.delete_rule(segura["id"])
        automations_store.delete_rule(insegura["id"])
    return c
