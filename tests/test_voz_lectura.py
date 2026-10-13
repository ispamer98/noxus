"""Contrato de los GET de voz: consulta autenticada y sin efectos secundarios."""
import asyncio
import hashlib
import json

from tests.comun import Caso

from noxuscmmd.domains.auth import permisos, sessions, store as auth_store
from noxuscmmd.domains.devices import voz
from noxuscmmd.domains.security import logs_store


class Peticion:
    def __init__(self, *, clave: str = "", query: dict | None = None,
                 path: dict | None = None):
        self.headers = {"x-noxus-clave": clave} if clave else {}
        self.query_params = query or {}
        self.path_params = path or {}


def _cuerpo(respuesta) -> dict:
    return json.loads(respuesta.body)


def _autenticacion_y_rol() -> Caso:
    c = Caso("API de voz de lectura: autenticación y rol")
    c.revisar("sin clave se rechaza", asyncio.run(voz.inventario_casa(Peticion())).status_code, 401)

    verificar_real = sessions.verificar_voz
    ficha_real = auth_store.dispositivo
    puede_real = permisos.puede
    try:
        sessions.verificar_voz = lambda _clave: "asistente_prueba"
        auth_store.dispositivo = lambda _id: {"nombre": "Asistente de prueba"}
        permisos.puede = lambda _id, _capacidad: False
        respuesta = asyncio.run(voz.inventario_casa(Peticion(clave="clave-prueba")))
        c.revisar("un rol sin VER se rechaza", respuesta.status_code, 403)
    finally:
        sessions.verificar_voz = verificar_real
        auth_store.dispositivo = ficha_real
        permisos.puede = puede_real
    return c


def _limites_y_lectura_pura() -> Caso:
    c = Caso("API de voz de lectura: límites y sin escrituras")
    autorizar_real = voz._autorizar_lectura
    consultar_real = logs_store.eventos_solo_lectura
    try:
        voz._autorizar_lectura = lambda _request, _ademas=None: ("asistente_prueba", None)
        llamadas = []

        def capturar(**kwargs):
            llamadas.append(kwargs)
            return []

        logs_store.eventos_solo_lectura = capturar
        respuesta = asyncio.run(voz.eventos_casa(Peticion(query={"n": "999"})))
        c.revisar("n se limita a 100", (respuesta.status_code, llamadas[0]["limite"]), (200, 100))
        llamadas.clear()
        respuesta = asyncio.run(voz.estado_alarma(Peticion(query={"n": "999"})))
        c.revisar("los eventos de alarma se limitan a 50",
                  (respuesta.status_code, llamadas[0]["limite"]), (200, 50))
        c.revisar("n inválido da 400", asyncio.run(
            voz.eventos_casa(Peticion(query={"n": "muchos"}))).status_code, 400)
    finally:
        voz._autorizar_lectura = autorizar_real
        logs_store.eventos_solo_lectura = consultar_real

    # La consulta real abre el histórico en mode=ro; su contenido no puede
    # cambiar por pedir eventos. Se mide el fichero temporal, nunca el vivo.
    antes = hashlib.sha256(logs_store.RUTA.read_bytes()).hexdigest()
    try:
        voz._autorizar_lectura = lambda _request, _ademas=None: ("asistente_prueba", None)
        respuesta = asyncio.run(voz.eventos_casa(Peticion(query={"n": "1"})))
        despues = hashlib.sha256(logs_store.RUTA.read_bytes()).hexdigest()
        c.revisar("consultar el histórico no lo escribe", (respuesta.status_code, despues), (200, antes))
    finally:
        voz._autorizar_lectura = autorizar_real
    return c


def _camaras_paradas() -> Caso:
    c = Caso("API de voz de lectura: cámara parada")
    autorizar_real = voz._autorizar_lectura
    leer_real = voz.nodes_store.read_all
    foto_real = voz._foto_go2rtc
    try:
        voz._autorizar_lectura = lambda _request, _ademas=None: ("asistente_prueba", None)
        voz.nodes_store.read_all = lambda: {"cameras": [
            {"id": "cam_prueba", "name": "Cámara de prueba", "kind": "go2rtc", "url": "prueba"},
        ]}

        async def parada(_src):
            return None, "La cámara está parada o no responde."

        voz._foto_go2rtc = parada
        respuesta = asyncio.run(voz.foto_camara(Peticion(path={"id": "cam_prueba"})))
        c.revisar("explica que la cámara está parada", (respuesta.status_code, _cuerpo(respuesta)["mensaje"]),
                  (503, "La cámara está parada o no responde."))
    finally:
        voz._autorizar_lectura = autorizar_real
        voz.nodes_store.read_all = leer_real
        voz._foto_go2rtc = foto_real
    return c


def _camaras_exigen_permiso() -> Caso:
    c = Caso("API de voz de lectura: cámaras exigen CAMARAS")
    quien_real, puede_real = voz._quien, voz.permisos.puede
    try:
        voz._quien = lambda _request, _cuerpo: ("asistente_prueba", "Asistente")
        voz.permisos.puede = lambda _id, capacidad: capacidad == voz.permisos.VER
        respuesta = asyncio.run(voz.camaras_casa(Peticion()))
        c.revisar("sin CAMARAS devuelve 403", respuesta.status_code, 403)
        voz.permisos.puede = lambda _id, capacidad: True
        _, error = voz._autorizar_lectura(Peticion(), voz.permisos.CAMARAS)
        c.revisar("con CAMARAS autoriza", error, None)
    finally:
        voz._quien, voz.permisos.puede = quien_real, puede_real
    return c


def _inventario_publico() -> Caso:
    c = Caso("API de voz de lectura: inventario seguro")
    catalogo_real = voz.catalogo.construir
    nodos_real = voz.nodes_store.read_all
    comandos_real = voz.comandos.comandos
    autorizar_real = voz._autorizar_lectura
    fila_sensor = {
        "id": "sensor_puerta_prueba", "nombre": "Puerta de prueba",
        "familia": "sensores", "tipo": "magnetic", "padre": "nodo_prueba",
        "estancia": "Entrada", "ip_local": "192.0.2.10", "mac": "00:00:00:00:00:01",
        "modelo": "modelo-prueba", "ubicacion": "pared", "entity_collection": "sensors",
        "entity_capabilities": ["edit", "inventory"], "entity_inventory_family": "sensores",
        "entity_type": "magnetic", "entity_id": "sensor_puerta_prueba",
        "entity_name": "Puerta de prueba", "notas": "no debe salir", "topic": "secreto",
    }
    fila_suelto = {
        "id": "suelto_prueba", "nombre": "Switch de prueba", "familia": "red",
        "entity_inventory_family": "sueltos", "entity_type": "network",
        "entity_id": "suelto_prueba", "entity_name": "Switch de prueba",
        "ip_local": "192.0.2.20", "password": "no debe salir",
    }
    fila_luz = {
        "entity_id": "luz_demo", "entity_name": "Cocina parecida",
        "entity_inventory_family": "luces", "entity_type": "light",
        "entity_collection": "lights",
    }
    fila_puerta = {
        "entity_id": "puerta_demo", "entity_name": "Puerta demo",
        "entity_inventory_family": "cerraderos", "entity_type": "door",
        "entity_collection": "doors",
    }
    fila_mando = {
        "entity_id": "mando_demo", "entity_name": "Mando demo",
        "entity_inventory_family": "mandos", "entity_type": "remote",
        "entity_collection": "ir_remotes",
    }
    fila_boton = {
        "entity_id": "boton_demo", "entity_name": "Encender demo",
        "entity_inventory_family": "botones", "entity_type": "button",
        "entity_collection": "ir_buttons", "entity_parent_id": "mando_demo",
    }
    comandos_prueba = [
        {"id": "luz:luz_demo:on", "etiqueta": "Encender Cocina parecida",
         "familia": "Luces", "paso": {"type": "light.set"}, "elemento": "luz_demo"},
        {"id": "luz:luz_demo:off", "etiqueta": "Apagar Cocina parecida",
         "familia": "Luces", "paso": {"type": "light.set"}, "elemento": "luz_demo"},
        {"id": "luz:luz_parecida:on", "etiqueta": "Encender Cocina parecida",
         "familia": "Luces", "paso": {"type": "light.set"}, "elemento": "luz_parecida"},
        {"id": "puerta:puerta_demo", "etiqueta": "Abrir Puerta demo",
         "familia": "Puertas", "paso": {"type": "door.pulse"}, "elemento": "puerta_demo"},
        {"id": "ir:mando_demo:boton_demo", "etiqueta": "Mando demo: Encender demo",
         "familia": "Mandos", "paso": {"type": "ir_button.press"}, "elemento": "boton_demo"},
        {"id": "modo:noche", "etiqueta": "Poner la casa en «Noche»",
         "familia": "Modos", "paso": {"type": "modo"}, "elemento": ""},
        {"id": "regla:demo", "etiqueta": "Ejecutar demo", "familia": "Automatizaciones",
         "paso": {"type": "rule.run"}, "elemento": ""},
        {"id": "sistema:on", "etiqueta": "Armar el sistema", "familia": "Alarma",
         "paso": {"type": "system.arm"}, "elemento": ""},
    ]
    try:
        voz._autorizar_lectura = lambda _request, _ademas=None: ("asistente_prueba", None)
        voz.nodes_store.read_all = lambda: {
            "rooms": [{"id": "room_prueba", "name": "Entrada"}],
            "sensor_states": {"sensor_puerta_prueba": True},
            "host_online": {"nodo_prueba": True},
            "sensors": [{"id": "sensor_puerta_prueba", "node_id": "nodo_prueba",
                         "room_id": "room_prueba"}],
        }
        voz.catalogo.construir = lambda: {
            "sensores": [fila_sensor], "sueltos": [fila_suelto], "luces": [fila_luz],
            "cerraderos": [fila_puerta], "mandos": [fila_mando], "botones": [fila_boton],
        }
        voz.comandos.comandos = lambda: comandos_prueba
        respuesta = asyncio.run(voz.inventario_casa(Peticion()))
        datos = _cuerpo(respuesta)
        c.revisar("inventario responde 200", respuesta.status_code, 200)
        c.revisar("campos exactos", set(datos["elementos"][0]), voz._CAMPOS_INVENTARIO_VOZ)
        sensor = next(e for e in datos["elementos"] if e["id"] == "sensor_puerta_prueba")
        suelto = next(e for e in datos["elementos"] if e["id"] == "suelto_prueba")
        c.revisar("padre por id", sensor["padre"], "nodo_prueba")
        c.revisar("estado del sensor", sensor["estado"], "abierto")
        c.cierto("elemento suelto presente", suelto["id"] == "suelto_prueba")
        c.cierto("no salen campos prohibidos", not ({"notas", "topic", "password"} & set(suelto)))
        luz = next(e for e in datos["elementos"] if e["id"] == "luz_demo")
        puerta = next(e for e in datos["elementos"] if e["id"] == "puerta_demo")
        mando = next(e for e in datos["elementos"] if e["id"] == "mando_demo")
        boton = next(e for e in datos["elementos"] if e["id"] == "boton_demo")
        c.revisar("la luz tiene on y off", [a["comando"] for a in luz["acciones"]],
                  ["luz:luz_demo:on", "luz:luz_demo:off"])
        c.revisar("la puerta tiene su comando", [a["comando"] for a in puerta["acciones"]],
                  ["puerta:puerta_demo"])
        c.revisar("el botón IR cuelga del mando correcto", boton["padre"], "mando_demo")
        c.revisar("el IR va al botón exacto", [a["comando"] for a in boton["acciones"]],
                  ["ir:mando_demo:boton_demo"])
        c.revisar("el mando no recibe la acción del botón", mando["acciones"], [])
        c.revisar("elemento sin comandos no es controlable",
                  (sensor["acciones"], sensor["controlable"]), ([], False))
        c.cierto("no casa por nombre parecido",
                  all(a["comando"] != "luz:luz_parecida:on" for a in luz["acciones"]))
        c.revisar("acciones globales separadas",
                  [a["comando"] for a in datos["acciones_casa"]],
                  ["modo:noche", "regla:demo", "sistema:on"])
    finally:
        voz.catalogo.construir = catalogo_real
        voz.nodes_store.read_all = nodos_real
        voz.comandos.comandos = comandos_real
        voz._autorizar_lectura = autorizar_real
    return c


def ejecutar() -> list[Caso]:
    return [_autenticacion_y_rol(), _limites_y_lectura_pura(), _camaras_paradas(),
            _camaras_exigen_permiso(), _inventario_publico()]
