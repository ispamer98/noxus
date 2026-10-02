"""
Alta de hardware en caliente, desde la propia web — nodos ESP32, sus
sensores/relés, puertas, luces, cámaras extra y equipos a monitorizar por
IP. Mismo patrón de persistencia que logs.py/shared_state.py (JSON plano con
lock de fichero), pero aquí es CRUD genérico en vez de campos fijos, porque
el conjunto de entidades lo decide el usuario en tiempo de ejecución, no el
código.

Convenio de topics MQTT (mismo estilo que devices/registry.py: casa/<host>/<sensor>,
ej. casa/raspberry/puerta, casa/pizero/tamper1):
  - Un sensor (magnético/PIR) publica su estado en   casa/{nombre-del-nodo}/{señal}
  - Una puerta/luz se ordena publicando ON/OFF en    casa/{nombre-del-nodo}/{señal}/set
El "nombre-del-nodo" es el nombre del nodo tal cual se le puso al darlo de
alta, pasado a slug (minúsculas, sin espacios/acentos) — NO su id interno —
así el ESP32 solo necesita saber su propio nombre y el nombre de cada señal
que publica/escucha, exactamente igual que ya hacen la Raspberry/Pi Zero.
"""
import fcntl
import json
import os
import re
import time
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path

from ...core import bus, pruebas

ARCHIVO = Path(os.getenv("NODOS_FILE", "nodos_dinamicos.json"))

_COLLECTIONS = (
    "nodes", "sensors", "doors", "lights", "cameras", "hosts", "host_buttons", "rooms",
    "overview_widgets", "ir_remotes", "electrodomesticos", "planos", "puertas",
    "metricas_paneles", "comandos_voz",
)

# Sistemas operativos que sabe manejar ssh_bus (apagar/reiniciar cambian de
# comando según cuál sea) — cualquier otro valor se trata como linux.
SISTEMAS = ("linux", "windows")

# La ficha de un equipo, campo a campo y en este orden. TODOS los equipos se
# reescriben con exactamente estas claves (ver _normalizar_equipos): el que
# venía de fábrica y el que se añadió hace un minuto son el mismo objeto, con
# la misma forma, y así se ven también al abrir nodos_dinamicos.json a mano.
# "acciones_extra" va al final porque es la única lista, y suele estar vacía.
# Los campos del plano van AQUÍ DENTRO por obligación, no por gusto: esta
# función reconstruye cada equipo desde cero con estas claves y solo estas, en
# cada lectura y en cada escritura. Un campo que no esté en la lista se borra
# solo, en silencio y a la primera — así que colocar un equipo en el plano sin
# pasar por aquí habría durado hasta la siguiente lectura del fichero.
CLAVES_EQUIPO = (
    "id", "created_at", "name", "ip", "user", "rdp_user", "rdp_launch_host",
    "os", "mac", "ping_retries", "icon", "order", "en_metricas", "acciones_extra",
    "floor_icon", "floor_top", "floor_left", "floor_subtle", "floor_color",
    "floor_color_on", "posiciones",
)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _migrar_equipos(data: dict) -> None:
    """factory_hosts + custom_hosts -> hosts (UNA sola colección).

    Antes había dos clases de equipo con campos distintos: los "de fábrica"
    (server, pc, raspberry, iphone...) con usuario/os/mac/reintentos, y los
    añadidos desde la web, que solo tenían nombre/ip/icono/ssh_user. Eso hacía
    que la misma pantalla ofreciese formularios distintos según de dónde
    viniera el equipo, y que los de fábrica se pintasen desde Python (había que
    reiniciar para ver una edición) mientras los otros eran reactivos.

    Ahora todos son la misma cosa. La fusión conserva los ids literales
    (raspberry, pi_zero... están referenciados por id en grupos_armado.json,
    en los niveles de acceso y en el node_id de cada sensor) y renombra
    ssh_user -> user, que era el mismo dato con dos nombres. Es idempotente:
    tras la primera lectura ya no quedan las claves viejas que migrar."""
    if "factory_hosts" not in data and "custom_hosts" not in data:
        return
    fusion = list(data.get("hosts", []))
    vistos = {h.get("id") for h in fusion}
    for host in data.pop("factory_hosts", []) + data.pop("custom_hosts", []):
        if host.get("id") in vistos:
            continue
        vistos.add(host.get("id"))
        if "ssh_user" in host:
            host["user"] = host.pop("ssh_user")
        fusion.append(host)
    data["hosts"] = fusion


def _migrar_nodos_desde_equipos(data: dict) -> None:
    """La Raspberry y la Pi Zero eran «nodos» por estar en una lista del código
    (la antigua lista GPIO_HOSTS del registry) y se pintaban y editaban aparte. Pasan a ser nodos
    NORMALES de `nodes`, con el MISMO id (así todo lo que cuelga de ellas —
    luces, puertas, sensores— sigue apuntando bien). Una sola vez: con la
    marca, borrar luego uno de esos nodos no lo resucita."""
    if data.get("nodos_desde_equipos"):
        return
    nodos = data.setdefault("nodes", [])
    for host in data.get("hosts", []):
        if host.get("id") in ("raspberry", "pi_zero") and not any(
                n.get("id") == host["id"] for n in nodos):
            nodos.append({"id": host["id"], "name": host.get("name") or host["id"],
                          "ip": host.get("ip", ""), "kind": "raspberry", "user": ""})
    data["nodos_desde_equipos"] = True


def _migrar_entidades_estaticas(data: dict) -> None:
    """Integra las antiguas colecciones separadas en sensors/cameras.

    La lectura aplica esta migracion sin escribir y ``_mutate`` la persiste en
    su siguiente operación. Se conserva el diccionario completo de cada
    entidad. Si el id ya existe, manda su ficha gestionada y solo se rellenan
    campos que le faltasen; nunca se crea un duplicado.
    """
    data.setdefault("sensors", [])
    data.setdefault("cameras", [])
    pares = (
        ("factory_sensors", "sensors"),
        ("factory_cameras", "cameras"),
    )
    for origen, destino in pares:
        existentes = {item.get("id"): item for item in data[destino]}
        for antiguo in data.pop(origen, []) or []:
            entity_id = antiguo.get("id")
            actual = existentes.get(entity_id)
            if actual is None:
                actual = dict(antiguo)
                data[destino].append(actual)
                existentes[entity_id] = actual
            else:
                for campo, valor in antiguo.items():
                    if campo == "posiciones" and isinstance(valor, dict):
                        actuales = actual.get(campo)
                        if isinstance(actuales, dict):
                            actual[campo] = {**valor, **actuales}
                            continue
                    if campo not in actual or actual[campo] in (None, "", [], {}):
                        actual[campo] = valor

    # Las referencias de estancia sí incluyen la colección en su identidad.
    # Se migran junto con las fichas para que ninguna tablet pierda miembros.
    reemplazos = {
        "factory_sensors:": "sensors:",
        "factory_cameras:": "cameras:",
    }

    def reemplazar(valor):
        if isinstance(valor, str):
            for viejo, nuevo in reemplazos.items():
                if valor.startswith(viejo):
                    return nuevo + valor[len(viejo):]
            return valor
        if isinstance(valor, list):
            return [reemplazar(item) for item in valor]
        if isinstance(valor, dict):
            return {reemplazar(k): reemplazar(v) for k, v in valor.items()}
        return valor

    for room in data.get("rooms", []):
        for campo in ("entidades", "orden", "personalizado"):
            if campo in room:
                room[campo] = reemplazar(room[campo])


def _normalizar_equipos(data: dict) -> None:
    """Deja TODOS los equipos con exactamente las mismas claves, en el mismo
    orden y con los mismos tipos — da igual de dónde vinieran. Se ejecuta en
    cada lectura y dentro de cada escritura, así que no hay forma de que un
    equipo acabe con una forma distinta de la de sus vecinos.

    Aquí es también donde el usuario SSH se recorta: " " no es un usuario,
    es un campo vacío con un espacio dentro. Sin esto bool(" ") vale True y el
    equipo se anunciaba como accionable por SSH — con la bandera puesta y
    fallando cualquier conexión, porque detrás no había ningún usuario."""
    normalizados = []
    for i, host in enumerate(data["hosts"]):
        limpio = {
            "id": host.get("id", ""),
            "created_at": host.get("created_at") or time.strftime("%Y-%m-%d %H:%M:%S"),
            "name": (host.get("name") or "").strip(),
            "ip": (host.get("ip") or "").strip(),
            "user": (host.get("user") or "").strip(),
            "rdp_user": (host.get("rdp_user") or "").strip(),
            "rdp_launch_host": (host.get("rdp_launch_host") or "").strip(),
            "os": host["os"] if host.get("os") in SISTEMAS else "linux",
            "mac": (host.get("mac") or "").strip() or None,
            "ping_retries": _entero(host.get("ping_retries"), por_defecto=1, minimo=1),
            "icon": host.get("icon") or "server",
            # El orden lo fija el usuario desde la pestaña Equipos; si falta
            # (fichero de antes de que se pudiera ordenar) se toma el orden
            # actual del fichero, que es justo como se venían pintando.
            "order": _entero(host.get("order"), por_defecto=i, minimo=0),
            # ¿Se guarda en el histórico si este equipo está en línea? Apagado
            # por defecto a propósito: son 288 muestras al día POR EQUIPO, y
            # guardarlas de los once para luego mirar dos es engordar la base
            # para nada. Se enciende el que se quiera vigilar (pestaña
            # Métricas). El recuento total sí se guarda siempre.
            "en_metricas": bool(host.get("en_metricas", False)),
            # «Test Ventilador» (gpio_17_test) se retiró: pulsaba el GPIO17 de
            # la Raspberry, que es el pin de la puerta de la habitación.
            "acciones_extra": [a for a in (host.get("acciones_extra") or [])
                               if a.get("handler_name") != "gpio_17_test"],
            # Plano. Se copian tal cual y sin inventar nada: un equipo que no
            # se ha colocado nunca los tiene a None y no sale pintado en
            # ninguna parte. `posiciones` es {plano_id: {top, left}} — el mismo
            # formato que luces, puertas y cámaras (ver _poner_posicion).
            "floor_icon": host.get("floor_icon") or None,
            "floor_top": host.get("floor_top") or None,
            "floor_left": host.get("floor_left") or None,
            "floor_subtle": bool(host.get("floor_subtle", False)),
            "floor_color": host.get("floor_color") or None,
            "floor_color_on": host.get("floor_color_on") or None,
            "posiciones": host.get("posiciones") or {},
        }
        normalizados.append(limpio)
    normalizados.sort(key=lambda h: h["order"])
    # Se reasigna 0..N-1 para que el orden guardado no acumule huecos ni
    # empates al borrar equipos o al moverlos muchas veces.
    for posicion, host in enumerate(normalizados):
        host["order"] = posicion
    data["hosts"] = normalizados


def _entero(valor, por_defecto: int, minimo: int) -> int:
    try:
        return max(minimo, int(valor))
    except (TypeError, ValueError):
        return por_defecto


def _repeticiones_luz(valor) -> int:
    try:
        return min(60, max(1, int(valor)))
    except (TypeError, ValueError):
        return 25


def _intervalo_luz(valor) -> float:
    try:
        return min(1.0, max(0.05, float(valor)))
    except (TypeError, ValueError):
        return 0.12


def _apply_defaults(data: dict) -> dict:
    """Rellena colecciones y campos que puedan faltar (ficheros de versiones
    anteriores del programa). Se aplica tanto al leer como dentro de _mutate,
    para que ambos caminos vean siempre la misma forma."""
    _migrar_equipos(data)
    _migrar_entidades_estaticas(data)
    _migrar_nodos_desde_equipos(data)
    for k in _COLLECTIONS:
        data.setdefault(k, [])
    # `doors` son las CERRADURAS de Accesos. Los segundos que tardan en
    # abrirse o cerrarse de verdad (puerta ~3, portón ~10): mientras, el plano
    # dice «Abriendo…» en vez de enseñar un magnético que no ha tenido tiempo.
    for cerradura in data["doors"]:
        cerradura.setdefault("transito_s", 3)
        # Los tres tiempos describen portones con una maniobra completa. Cero
        # conserva el comportamiento anterior basado únicamente en transito_s.
        cerradura["apertura_s"] = _entero(cerradura.get("apertura_s"), 0, 0)
        cerradura["espera_s"] = _entero(cerradura.get("espera_s"), 0, 0)
        cerradura["cierre_s"] = _entero(cerradura.get("cierre_s"), 0, 0)
        # Cómo mueve el relé la puerta (ver MODOS_CERRADURA). Lo de antes era
        # siempre un pulso que abre y deja que la puerta se cierre sola.
        if cerradura.get("modo") not in MODOS_CERRADURA:
            cerradura["modo"] = MODO_PULSO
    # `puertas` son las PUERTAS DEL PLANO: un elemento propio que junta lo que
    # tenga esa puerta — magnético, cerradura de Accesos y anclados (una
    # persiana...). Ninguna pieza es obligatoria.
    sensores = {x.get("id") for x in data["sensors"]}
    cerraduras = {x.get("id") for x in data["doors"]}
    for puerta in data["puertas"]:
        if puerta.get("sensor_id") not in sensores:
            puerta["sensor_id"] = ""
        if puerta.get("cerradura_id") not in cerraduras:
            puerta["cerradura_id"] = ""
        puerta.setdefault("anclados", [])
    for room in data["rooms"]:
        # Las luces conservan room_id por compatibilidad. El resto de cosas de
        # una estancia se referencia como "colección:id", la misma identidad
        # inequívoca que usa el catálogo del plano.
        entidades = room.get("entidades")
        room["entidades"] = list(dict.fromkeys(
            ref for ref in (entidades if isinstance(entidades, list) else [])
            if isinstance(ref, str) and ":" in ref
        ))
        # La selección de equipos solo admite las dos colecciones vigilables.
        # Ausente/None conserva el comportamiento heredado de la estancia.
        if room.get("equipos_vista") is not None:
            validas = {
                f"{coleccion}:{item['id']}"
                for coleccion in ("hosts", "nodes")
                for item in data[coleccion]
            }
            refs = room.get("equipos_vista")
            room["equipos_vista"] = list(dict.fromkeys(
                ref for ref in (refs if isinstance(refs, list) else [])
                if isinstance(ref, str) and ref in validas
            ))
    data.setdefault("sensor_states", {})
    data.setdefault("host_online", {})
    vw = data.get("video_wall")
    if not isinstance(vw, dict):
        vw = {}
        data["video_wall"] = vw
    vw.setdefault("layout", "4")
    if not isinstance(vw.get("slots"), dict):
        vw["slots"] = {}
    for node in data["nodes"]:
        node.setdefault("kind", "esp32")
        node.setdefault("user", "")
    for cam in data["cameras"]:
        cam.setdefault("kind", "go2rtc" if cam.get("stream_src") else "embed")
    # Qué cámara mira a ese elemento, para guardar un fotograma cuando salte la
    # alarma (ver domains/cameras/fotogramas.py). Vacío = ninguna.
    for sensor in data["sensors"]:
        sensor.setdefault("camara", "")
        sensor.setdefault("isolated", False)
        sensor.setdefault("pin", (sensor.get("topic") or "").rsplit("/", 1)[-1])
        sensor.setdefault("node_id", "")
        sensor.setdefault("node_name", "")
        sensor.setdefault("floor_top", None)
        sensor.setdefault("floor_left", None)
        sensor.setdefault("floor_icon", None)
        sensor.setdefault("floor_subtle", False)
        sensor.setdefault("floor_color", None)
        sensor.setdefault("floor_color_on", None)
    for door in data["doors"]:
        door.setdefault("pulse_seconds", 2)
        door.setdefault("floor_top", None)
        door.setdefault("floor_left", None)
        door.setdefault("floor_icon", None)
        door.setdefault("floor_subtle", False)
        door.setdefault("floor_color", None)
        door.setdefault("floor_color_on", None)
    for light in data["lights"]:
        # Las luces de antes de que existieran las de mando son todas de relé.
        light.setdefault("kind", LUZ_RELE)
        light.setdefault("aspecto", "luz")
        light.setdefault("mando_modo", DOS_TECLAS)
        light["auto_apagado_min"] = _entero(
            light.get("auto_apagado_min"), por_defecto=0, minimo=0)
        light["modo_encendido"] = _modo_encendido(light.get("modo_encendido", ""))
        light["pausa_secuencia_s"] = _pausa_secuencia(light.get("pausa_secuencia_s", 1.0))
        light["apagar_luz_al_encender"] = bool(light.get("apagar_luz_al_encender", False))
        light["luz_repeticiones"] = _repeticiones_luz(light.get("luz_repeticiones", 25))
        light["luz_intervalo_s"] = _intervalo_luz(light.get("luz_intervalo_s", 0.12))
        # Solo los accesorios por mando necesitan recordar el inicio del ciclo.
        # Se guarda en su propia ficha: ``sensor_states`` conserva estrictamente
        # su contrato booleano para el plano, Alexa y las automatizaciones.
        if light["kind"] != LUZ_MANDO:
            light.pop("encendido_en", None)
            light.pop("ciclo_min", None)
        light.setdefault("remote_id", "")
        light.setdefault("btn_on", "")
        light.setdefault("btn_off", "")
        light.setdefault("btn_continuo", "")
        light.setdefault("btn_timing", "")
        light.setdefault("btn_luz", "")
        light["btn_continuo"] = _tecla_valida(
            data, light.get("remote_id", ""), light.get("btn_continuo", ""))
        light["btn_timing"] = _tecla_valida(
            data, light.get("remote_id", ""), light.get("btn_timing", ""))
        light["btn_luz"] = _tecla_valida(
            data, light.get("remote_id", ""), light.get("btn_luz", ""))
        light.setdefault("room_id", "")
        light.setdefault("floor_top", None)
        light.setdefault("floor_left", None)
        light.setdefault("floor_icon", None)
        light.setdefault("floor_subtle", False)
        light.setdefault("floor_color", None)
        light.setdefault("floor_color_on", None)
    # Una luz que apunte a una estancia que ya no existe pasa a "sin estancia".
    # delete_room ya lo deja así, pero esto recupera además las que quedaron
    # huérfanas antes (y las que pueda dejar cualquier edición a mano del
    # fichero): con un room_id fantasma la luz no salía ni en su estancia ni en
    # "sin estancia", así que parecía borrada aunque siguiera aquí.
    ids_estancias = {r.get("id") for r in data["rooms"]}
    for light in data["lights"]:
        if light["room_id"] and light["room_id"] not in ids_estancias:
            light["room_id"] = ""
    for cam in data["cameras"]:
        if cam.get("stream_src") and not cam.get("url"):
            cam["url"] = cam["stream_src"]
        cam.setdefault("url", "")
        # Migración idempotente: los controles del dispositivo ya no forman
        # parte del modelo. Se conserva id, URL y toda su colocación.
        cam.pop("tuya_device_id", None)
        cam.pop("has_ptz", None)
        cam.setdefault("icon", None)
        cam.setdefault("floor_top", None)
        cam.setdefault("floor_left", None)
        cam.setdefault("floor_icon", None)
        cam.setdefault("floor_subtle", False)
        cam.setdefault("floor_color", None)
        cam.setdefault("floor_color_on", None)
    _normalizar_equipos(data)
    for remote in data["ir_remotes"]:
        remote.setdefault("icon", "tv")
        remote.setdefault("buttons", [])
        remote.setdefault("groups", [])
        # Mandos de antes de que el cuerpo fuera configurable: los que se
        # montaron a mano usaban el vertical, que es el que se les queda.
        remote.setdefault("body_w", 250)
        remote.setdefault("body_h", 850)
        remote.setdefault("floor_top", None)
        remote.setdefault("floor_left", None)
        remote.setdefault("floor_icon", None)
        remote.setdefault("floor_subtle", False)
        remote.setdefault("floor_color", None)
        remote.setdefault("floor_color_on", None)
        for boton in remote["buttons"]:
            # Botones de antes de que existieran las plantillas: todos eran
            # infrarrojos y todos tenían señal, así que ese es el valor que les
            # corresponde.
            boton.setdefault("kind", "ir")
            boton.setdefault("code", "")
            # Rótulo impreso en la tecla (los números) y tinte de color (las
            # cuatro teclas de color de la TV) — ver remote_templates.py.
            boton.setdefault("text", "")
            boton.setdefault("color", "")
            # Tamaño del icono dentro de la tecla: los pares "más/menos" del
            # mando (los dos soles de la luz, las dos aspas de la velocidad)
            # solo se distinguen por eso.
            boton.setdefault("icon_size", "46%")
        _asegurar_posiciones(remote)
    for electro in data["electrodomesticos"]:
        electro["tipo"] = (electro.get("tipo") if electro.get("tipo") in TIPOS_ELECTRO
                           else "lavadora")
        electro["simulado"] = True
        electro.setdefault("node_id", "")
        electro.setdefault("node_name", "")
        electro.setdefault("estado", {})
        electro.setdefault("floor_top", None)
        electro.setdefault("floor_left", None)
        electro.setdefault("floor_icon", None)
        electro.setdefault("floor_subtle", False)
        electro.setdefault("floor_color", None)
        electro.setdefault("floor_color_on", None)
    # LO ÚLTIMO: los planos y la posición de cada elemento en cada plano. Va al
    # final y no en medio porque es quien tiene la última palabra sobre
    # floor_top/floor_left (los mantiene como espejo del plano principal), y
    # ponerlo antes de los `setdefault` de esos campos haría que el resultado
    # dependiera del orden en que están escritos los bucles de aquí arriba.
    _sincronizar_planos(data)
    return data


def _read() -> dict:
    if not ARCHIVO.exists():
        return _apply_defaults({})
    try:
        with open(ARCHIVO, "r") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                content = f.read().strip()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        data = json.loads(content) if content else {}
    except Exception:
        data = {}
    return _apply_defaults(data)


def _mutate(mutator):
    """Ciclo leer-modificar-escribir ATÓMICO: el cerrojo exclusivo se mantiene
    durante TODO el ciclo, no solo durante la lectura y luego durante la
    escritura por separado.

    Sin esto se pierden escrituras, y de forma intermitente: como cada
    operación reescribe el fichero ENTERO, si entre el _read() y el _write()
    de una (p.ej. guardar la posición de un icono del plano) se cuela otra
    (set_sensor_state, que dispara con cada mensaje MQTT, o
    set_host_online_bulk cada 10s), la que escribe última machaca los cambios
    de la otra. Medido antes de este arreglo: 8 de 60 posiciones perdidas con
    un escritor concurrente."""
    ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
    lock_path = ARCHIVO.with_suffix(ARCHIVO.suffix + ".lock")
    with open(lock_path, "a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            content = ARCHIVO.read_text(encoding="utf-8").strip() if ARCHIVO.exists() else ""
            try:
                data = json.loads(content) if content else {}
            except Exception:
                data = {}
            _apply_defaults(data)
            result = mutator(data)
            # Otra vez DESPUÉS de mutar: lo que acabe de tocar el mutador (un
            # equipo recién añadido, un `order` intercambiado) queda con la
            # forma canónica ya en esta misma escritura, no en la siguiente.
            # Es idempotente, así que pasarlo dos veces no cambia nada más.
            _apply_defaults(data)
            # El cerrojo vive en un fichero estable: bloquear el JSON y luego
            # reemplazarlo dejaría a otro proceso bloqueando el inodo antiguo.
            # Así todas las mutaciones se serializan y el lector solo puede ver
            # el fichero anterior o el nuevo, nunca media escritura.
            tmp = ARCHIVO.with_suffix(ARCHIVO.suffix + ".tmp")
            with open(tmp, "w", encoding="utf-8") as salida:
                json.dump(data, salida, indent=2, ensure_ascii=False)
                salida.write("\n")
                salida.flush()
                os.fsync(salida.fileno())
            os.replace(tmp, ARCHIVO)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    bus.publicar(bus.ENTIDADES)
    return result


def _write(data: dict) -> None:
    def _reemplazar(actual):
        actual.clear()
        actual.update(data)

    _mutate(_reemplazar)


def read_all() -> dict:
    return _read()


def apply_migrations() -> None:
    """Persiste de forma atómica las migraciones/defaults sobre ARCHIVO."""
    _mutate(lambda data: None)


def slugify(texto: str) -> str:
    """"Nodo Garaje" -> "nodo_garaje" — mismo estilo que los slugs ya usados a
    mano en registry.py (raspberry, pizero)."""
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", sin_acentos.lower()).strip("_") or "nodo"


def sensor_topic(node_name: str, pin: str) -> str:
    return f"casa/{slugify(node_name)}/{pin}"


def command_topic(node_name: str, pin: str) -> str:
    return f"casa/{slugify(node_name)}/{pin}/set"


def _add(collection: str, prefix: str, item: dict) -> dict:
    nuevo = {"id": _new_id(prefix), "created_at": time.strftime("%Y-%m-%d %H:%M:%S"), **item}

    def _apply(data):
        data[collection].append(nuevo)
        return nuevo

    return _mutate(_apply)


def _add_with_id(collection: str, item: dict) -> dict:
    """Igual que _add pero conservando el id tal cual viene en `item` — solo
    para la migración de entidades "de fábrica" (puerta_ppal, tamper1,
    raspberry...), que deben mantener su id literal de siempre porque ya
    están referenciadas por ese id en grupos_armado.json y en niveles de
    acceso. No usar para altas normales desde la UI (esas sí generan un id
    nuevo con _add)."""
    def _apply(data):
        existente = next((x for x in data[collection] if x.get("id") == item["id"]), None)
        if existente is not None:
            return existente
        nuevo = {"created_at": time.strftime("%Y-%m-%d %H:%M:%S"), **item}
        data[collection].append(nuevo)
        return nuevo

    return _mutate(_apply)


def _delete(collection: str, item_id: str) -> None:
    def _apply(data):
        data[collection] = [x for x in data[collection] if x.get("id") != item_id]

    _mutate(_apply)


def _update(collection: str, item_id: str, fields: dict) -> dict | None:
    def _apply(data):
        updated = None
        for item in data[collection]:
            if item["id"] == item_id:
                item.update(fields)
                updated = item
        return updated

    return _mutate(_apply)


# ── Nodos ────────────────────────────────────────────────────────────────────
# kind="esp32" (por defecto): se actúa/lee por MQTT, como cualquier ESP32.
# kind="ssh": es un equipo tipo Raspberry más — se actúa por SSH+raspi-gpio
# igual que la Raspberry/Pi Zero fijas del registry, pero dado de alta desde
# la web en vez de hardcodeado. `user` solo se usa cuando kind="ssh".
def add_node(name: str, ip: str, kind: str = "esp32", user: str = "") -> dict:
    return _add("nodes", "node", {"name": name, "ip": ip, "kind": kind, "user": user})


def delete_node(node_id: str) -> None:
    _delete("nodes", node_id)


def update_node(node_id: str, name: str, ip: str, kind: str = "esp32", user: str = "") -> dict | None:
    return _update("nodes", node_id, {"name": name, "ip": ip, "kind": kind, "user": user})


# ── Posición en el plano de planta (room.png) ────────────────────────────────
# Cualquier sensor o cámara (de fábrica o añadido desde la web) puede
# mostrarse en el plano — floor_top/floor_left en None significa "no se
# muestra". floor_fields() traduce el toggle "mostrar en el plano" + icono
# elegido del formulario de edición a los campos de storage; el arrastre en
# el propio plano usa set_floor_position() directamente (ver device_list.py).
_FLOOR_DEFAULT_POS = {"floor_top": "50%", "floor_left": "50%"}

# ── Planos múltiples ─────────────────────────────────────────────────────────
# Hasta ahora había UN plano: la imagen estaba escrita en el código
# (`/room.png`) y cada elemento guardaba su sitio en `floor_top`/`floor_left`.
# Ahora hay una colección `planos` y cada elemento guarda una posición POR
# PLANO, en `posiciones`:
#
#   "posiciones": {"plano_1": {"top": "80.9%", "left": "89.8%"}}
#
# El icono, el color y lo de «apagado» siguen siendo del ELEMENTO y no del
# plano: una luz es la misma luz se pinte donde se pinte, y tener que
# recolorearla en cada plano sería trabajo repetido para acabar igual.
#
# LO QUE HACE QUE ESTE CAMBIO NO ROMPA NADA: `floor_top`/`floor_left` siguen
# existiendo, mantenidos como ESPEJO de la posición en el plano principal (ver
# _sincronizar_planos). Así todo lo que ya leía esos dos campos —los marcadores
# del plano, el popover de la vista clásica, el catálogo— sigue funcionando sin
# tocar una línea, y lo nuevo lee `posiciones`. Cuando no quede nadie leyendo el
# espejo, se quita y no se entera nadie.
#
# El id del primer plano es FIJO y no un uuid. Es importante: _apply_defaults se
# ejecuta en cada LECTURA, y una lectura no escribe, así que un id aleatorio
# saldría distinto en cada lectura hasta que alguien guardara algo — y las
# posiciones apuntarían a un plano que cambia de nombre solo.
PLANO_INICIAL = "plano_1"
NOMBRE_PLANO_INICIAL = "Planta baja"

# La imagen que ya estaba en el código. Su tamaño va escrito porque se conoce
# (1254x1254) y así la migración no tiene que abrir un fichero de 2 MB en cada
# lectura del store.
IMAGEN_INICIAL = "room.png"
_MEDIDAS_INICIALES = (1254, 1254)

# Colecciones cuyos elementos pueden estar en un plano. Es la misma lista que
# construye el catálogo del plano (ver nodes/state._build_floor_catalog).
COLECCIONES_EN_PLANO = (
    "nodes", "sensors", "cameras", "doors", "lights", "ir_remotes",
    "electrodomesticos", "puertas",
)


def plano_principal(data: dict) -> dict | None:
    """El plano que se abre por defecto. Si ninguno está marcado, el primero:
    quedarse sin plano principal por un fichero editado a mano dejaría el plano
    en blanco, y es mejor enseñar uno que ninguno."""
    planos = data.get("planos") or []
    if not planos:
        return None
    return next((p for p in planos if p.get("principal")), planos[0])


def _sincronizar_planos(data: dict) -> None:
    """Crea el primer plano si no hay ninguno, y mantiene el espejo de
    floor_top/floor_left. Idempotente: se ejecuta en cada lectura y escritura.

    Del orden depende que la migración sea correcta: primero se asegura que hay
    un plano al que atribuir las posiciones de antes, después se sube cada
    `floor_top` a `posiciones`, y solo al final se vuelve a bajar el espejo."""
    planos = data.setdefault("planos", [])

    hay_posiciones = any(
        e.get("floor_top") or e.get("posiciones")
        for coleccion in COLECCIONES_EN_PLANO for e in data.get(coleccion, [])
    )
    if not planos and hay_posiciones:
        # Instalación de antes de los planos múltiples: lo que había se convierte
        # en el plano principal, con la imagen que estaba escrita en el código.
        planos.append({
            "id": PLANO_INICIAL,
            "nombre": NOMBRE_PLANO_INICIAL,
            "imagen": IMAGEN_INICIAL,
            "ancho": _MEDIDAS_INICIALES[0],
            "alto": _MEDIDAS_INICIALES[1],
            "orden": 0,
            "principal": True,
        })

    for i, plano in enumerate(planos):
        plano.setdefault("nombre", f"Plano {i + 1}")
        plano.setdefault("imagen", "")
        plano.setdefault("ancho", 0)
        plano.setdefault("alto", 0)
        plano.setdefault("orden", i)
        plano.setdefault("principal", False)
    # Exactamente uno principal, nunca cero ni dos: con dos, cuál se abre
    # dependería del orden del fichero.
    if planos and not any(p["principal"] for p in planos):
        planos[0]["principal"] = True

    principal = plano_principal(data)
    ids = {p["id"] for p in planos}
    for coleccion in COLECCIONES_EN_PLANO:
        for elemento in data.get(coleccion, []):
            posiciones = elemento.get("posiciones")
            if not isinstance(posiciones, dict):
                posiciones = {}
                elemento["posiciones"] = posiciones
            # Sube la posición de antes al plano principal. La condición es «no
            # tiene NINGUNA posición», no «le falta la del principal»: con lo
            # segundo, quitar un elemento del plano principal se deshacía solo —
            # se borraba de `posiciones`, y esta misma función lo volvía a crear
            # leyendo el `floor_top` viejo, que todavía no se había recalculado.
            # Un elemento sin ninguna posición y con floor_top puesto es lo único
            # que de verdad significa «esto viene de antes de los planos» (o «lo
            # acaba de escribir floor_fields al marcar "mostrar en el plano"»).
            if principal and elemento.get("floor_top") and not posiciones:
                posiciones[principal["id"]] = {
                    "top": elemento["floor_top"],
                    "left": elemento.get("floor_left") or "50%",
                }
            # Posiciones de planos borrados: fuera, o el elemento contaría como
            # colocado en un plano que no existe.
            for plano_id in [k for k in posiciones if k not in ids]:
                posiciones.pop(plano_id)
            # Y el espejo, para todo lo que sigue leyendo floor_top.
            sitio = posiciones.get(principal["id"]) if principal else None
            elemento["floor_top"] = sitio["top"] if sitio else None
            elemento["floor_left"] = sitio["left"] if sitio else None


def floor_fields(show_on_floor: bool, floor_icon: str, current: dict | None) -> dict:
    # Al EDITAR (hay `current`) la ficha ya no toca la posición: con varios
    # planos, «mostrar en el plano» no dice en cuál, y el toggle leía el espejo
    # del principal — desmarcarlo no quitaba nada y marcarlo lo metía en el
    # principal. Dónde sale cada cosa se decide solo desde el editor de cada plano.
    if current is not None:
        return {"floor_icon": floor_icon or None}
    if not show_on_floor:
        return {"floor_top": None, "floor_left": None, "floor_icon": floor_icon or None}
    fields = {"floor_icon": floor_icon or None}
    if not current or not current.get("floor_top"):
        fields.update(_FLOOR_DEFAULT_POS)
    return fields


def _poner_posicion(data: dict, coleccion: str, entity_id: str, plano_id: str,
                    top: str | None, left: str | None) -> dict | None:
    """Escribe (o borra, con top=None) la posición de un elemento en un plano.

    Uso interno: hay que estar dentro de un _mutate, porque hace falta `data`
    para saber cuál es el plano principal cuando no se dice ninguno."""
    destino = plano_id or (plano_principal(data) or {}).get("id", "")
    if not destino:
        return None
    for item in data.get(coleccion, []):
        if item.get("id") != entity_id:
            continue
        posiciones = item.setdefault("posiciones", {})
        if top is None:
            posiciones.pop(destino, None)
            # El espejo se limpia aquí también, y no solo al final: mientras
            # `floor_top` siga puesto, cualquier cosa que lo lea dentro de esta
            # misma escritura creería que el elemento sigue colocado.
            item["floor_top"] = None
            item["floor_left"] = None
        else:
            posiciones[destino] = {"top": top, "left": left or "50%"}
        return item
    return None


def set_floor_position(collection: str, entity_id: str, top: str, left: str,
                       plano_id: str = "") -> dict | None:
    """Persiste la posición (%) de un marcador tras arrastrarlo. Sin `plano_id`
    va al plano principal, que es lo que hacía cuando solo había uno."""
    return _mutate(lambda data: _poner_posicion(
        data, collection, entity_id, plano_id, top, left))


def set_floor_positions_bulk(updates: list[dict]) -> None:
    """Guarda de una sola vez la posición de VARIOS marcadores — es lo que usa
    el botón "Listo" del editor del plano, que se trae toda la sesión de
    recolocar iconos junta. Al ir en un único _mutate, o se guardan todas o no
    se guarda ninguna: no puede quedar media recolocación a medias.

    Cada entrada: {"collection", "id", "top", "left"} y opcionalmente "plano".
    Sin "plano" se entiende el principal — así el editor de siempre sigue
    funcionando sin enterarse de que ahora hay más de un plano."""
    def _apply(data):
        for u in updates:
            _poner_posicion(data, u["collection"], u["id"], u.get("plano", ""),
                            u["top"], u["left"])

    _mutate(_apply)


def clear_floor_position(collection: str, entity_id: str,
                         plano_id: str = "") -> dict | None:
    """Quita el elemento de ESE plano (deja de pintarse ahí) sin tocar nada más
    de su configuración, ni su sitio en los demás planos."""
    return _mutate(lambda data: _poner_posicion(
        data, collection, entity_id, plano_id, None, None))


def duplicar_en_plano(coleccion: str, entity_id: str, origen: str,
                      destino: str) -> bool:
    """Pone un elemento en otro plano, en el mismo sitio que ocupaba en el de
    origen.

    Copiar la posición y no centrarlo es lo útil de verdad cuando los planos son
    dos plantas de la misma casa: la puerta de arriba suele caer casi donde la de
    abajo, así que se queda a un empujón en vez de haber que buscarle el sitio."""
    def _apply(data):
        for item in data.get(coleccion, []):
            if item.get("id") != entity_id:
                continue
            sitio = (item.get("posiciones") or {}).get(origen)
            if not sitio:
                return False
            item.setdefault("posiciones", {})[destino] = dict(sitio)
            return True
        return False

    return bool(_mutate(_apply))


def set_floor_icon(collection: str, entity_id: str, icon: str) -> dict | None:
    return _update(collection, entity_id, {"floor_icon": icon or None})


def set_floor_color(collection: str, entity_id: str, color: str) -> dict | None:
    """Color EN REPOSO del marcador: de qué color se ve cuando todo está en
    orden. El de cuando está activo se elige aparte (ver set_floor_color_on)."""
    return _update(collection, entity_id, {"floor_color": color or None})


def set_floor_color_on(collection: str, entity_id: str, color: str) -> dict | None:
    """Color del marcador CUANDO ESTÁ ACTIVO: encendido si es una luz o un
    accesorio, abierto o disparado si es un sensor o una puerta.

    Vacío = el que pone el sistema para esa familia (ámbar para lo que se
    enciende, rojo para lo que se abre o salta), que es lo que había antes de
    que esto se pudiera elegir. Se guarda por elemento porque en un plano con
    diez marcadores el color es lo único que los distingue de un vistazo."""
    return _update(collection, entity_id, {"floor_color_on": color or None})


def toggle_floor_subtle(collection: str, entity_id: str) -> bool:
    """Alterna el modo "discreto" de un marcador: se pinta pequeño y atenuado,
    para elementos que interesa tener localizados pero que no deben robar
    atención (un tamper, por ejemplo). Devuelve el estado resultante."""
    def _apply(data):
        for item in data.get(collection, []):
            if item.get("id") == entity_id:
                item["floor_subtle"] = not item.get("floor_subtle", False)
                return item["floor_subtle"]
        return False

    return _mutate(_apply)


# ── Sensores (magnético / PIR / tamper) ──────────────────────────────────────
# node_name se guarda duplicado (además de node_id) para poder pintar "Nodo:
# X" en la UI sin tener que cruzar listas con un Var reactivo — si el nodo se
# renombra más tarde, las entidades ya creadas se quedan con el nombre viejo.
def add_sensor(name: str, kind: str, node_id: str, node_name: str, pin: str,
               show_on_floor: bool = False, floor_icon: str = "") -> dict:
    item = {
        "name": name, "kind": kind, "node_id": node_id, "node_name": node_name,
        "pin": pin, "topic": sensor_topic(node_name, pin),
        "isolated": False,
        **floor_fields(show_on_floor, floor_icon, None),
    }
    return _add("sensors", "sensor", item)


def delete_sensor(sensor_id: str) -> None:
    _delete("sensors", sensor_id)


def update_sensor(sensor_id: str, name: str, kind: str, node_id: str, node_name: str, pin: str,
                   show_on_floor: bool = False, floor_icon: str = "") -> dict | None:
    current = next((s for s in _read()["sensors"] if s["id"] == sensor_id), None)
    topic = (current or {}).get("topic", "")
    if not current or current.get("node_id") != node_id or current.get("pin") != pin:
        topic = sensor_topic(node_name, pin)
    return _update("sensors", sensor_id, {
        "name": name, "kind": kind, "node_id": node_id, "node_name": node_name,
        "pin": pin, "topic": topic,
        **floor_fields(show_on_floor, floor_icon, current),
    })


# ── Elemento de alarma -> cámara que lo mira ─────────────────────────────────
# Vive aquí y no en el dominio de cámaras porque es puro dato: este módulo es
# el que guarda la ficha del sensor Y la de la cámara, así que es el único sitio
# donde resolver la cadena no obliga a nadie a importar a nadie.
def set_sensor_camera(sensor_id: str, camera_id: str) -> bool:
    """Asigna (o quita, con "") la cámara de un sensor. False si no existe."""
    def _apply(data):
        for s in data["sensors"]:
            if s["id"] == sensor_id:
                s["camara"] = camera_id
                return True
        return False

    return bool(_mutate(_apply))


def camara_de_sensor(sensor_id: str) -> str:
    data = _read()
    for s in data["sensors"]:
        if s["id"] == sensor_id:
            return s.get("camara", "") or ""
    return ""


def src_de_sensor(sensor_id: str) -> str:
    """El stream de go2rtc que hay que pedirle para ver ese elemento, o "".

    Devuelve "" tanto si no tiene cámara asignada como si la que tiene no puede
    dar una imagen fija, y eso es lo mismo para quien captura: no hay foto.

    Solo las de tipo `go2rtc` sirven: a un `embed` o a un `rtsp` no hay a
    quién pedirle un fotograma."""
    camara_id = camara_de_sensor(sensor_id)
    if not camara_id:
        return ""
    data = _read()
    for c in data["cameras"]:
        if c["id"] == camara_id:
            return ((c.get("url") or c.get("stream_src") or "")
                    if c.get("kind") == "go2rtc" else "")
    # Apuntaba a una cámara que ya no está.
    return ""


def camaras_para_fotograma() -> list[dict]:
    """[{"id", "name"}] de las cámaras que pueden dar una imagen fija — las que
    tiene sentido ofrecer al elegir la cámara de un elemento."""
    data = _read()
    return [{"id": c["id"], "name": c.get("name", c["id"])}
            for c in data["cameras"] if c.get("kind") == "go2rtc"]


def toggle_sensor_isolated(sensor_id: str) -> dict | None:
    def _apply(data):
        updated = None
        for s in data["sensors"]:
            if s["id"] == sensor_id:
                s["isolated"] = not s.get("isolated", False)
                updated = s
        return updated

    return _mutate(_apply)


# ── Puertas / cerraduras ─────────────────────────────────────────────────────
# Cómo trabaja la cerradura o el motor que manda el relé:
#   pulso       un pulso abre y la puerta vuelve sola (cerradero eléctrico, portón
#               con cierre automático). Mantener abierta = relé activado.
#   dos_pulsos  un pulso abre y OTRO cierra (portón paso a paso). Abrir para
#               pasar da el segundo pulso al acabar la espera; mantener abierta o
#               cerrada da un solo pulso, y solo si la puerta no estaba ya así.
MODO_PULSO, MODO_DOS_PULSOS = "pulso", "dos_pulsos"
MODOS_CERRADURA = {
    MODO_PULSO: "Un pulso abre; se cierra sola",
    MODO_DOS_PULSOS: "Un pulso abre y otro cierra",
}


def _maniobra(modo: str, apertura_s, espera_s, cierre_s) -> dict:
    """Campos de cómo se mueve la puerta, ya saneados. Los tres tiempos a cero
    dejan la puerta como antes (solo `transito_s`)."""
    return {
        "modo": modo if modo in MODOS_CERRADURA else MODO_PULSO,
        "apertura_s": _entero(apertura_s, 0, 0),
        "espera_s": _entero(espera_s, 0, 0),
        "cierre_s": _entero(cierre_s, 0, 0),
    }


# topic_state es opcional de usar por el firmware (confirmación de estado real
# del relé); topic_cmd es donde el sistema publica ON/OFF para actuar.
# pulse_seconds: duración del pulso de "Abrir" antes de cerrarse solo — definible
# por puerta (2, 3, 4, 5s...) en vez de fijo en el código.
def add_door(name: str, node_id: str, node_name: str, pin: str, pulse_seconds: int = 2,
             show_on_floor: bool = False, floor_icon: str = "", *,
             modo: str = MODO_PULSO, apertura_s: int = 0, espera_s: int = 0,
             cierre_s: int = 0) -> dict:
    item = {
        "name": name, "node_id": node_id, "node_name": node_name, "pin": pin,
        "topic_cmd": command_topic(node_name, pin),
        "topic_state": sensor_topic(node_name, pin),
        "pulse_seconds": pulse_seconds,
        **_maniobra(modo, apertura_s, espera_s, cierre_s),
        **floor_fields(show_on_floor, floor_icon, None),
    }
    return _add("doors", "door", item)


def add_puerta(name: str, cerradura_id: str = "", sensor_id: str = "") -> dict:
    """Una Puerta del plano. Se crea al poner en el plano una cerradura de
    Accesos o un magnético de puerta, con esa pieza ya dentro."""
    return _add("puertas", "puerta", {
        "name": name, "cerradura_id": cerradura_id, "sensor_id": sensor_id,
        "anclados": [], "floor_icon": "door-closed",
    })


def delete_puerta(puerta_id: str) -> None:
    """Quita la Puerta del plano. Sus piezas (cerradura, magnético...) siguen
    existiendo: vuelven a ofrecerse sueltas para ponerlas en otra Puerta."""
    _delete("puertas", puerta_id)


def _una_sola(data: dict, puerta: dict, campo: str, valor: str) -> None:
    """Una pieza solo puede estar en UNA puerta: al meterla aquí se saca de
    cualquier otra."""
    for otra in data["puertas"]:
        if otra is not puerta and otra.get(campo) == valor:
            otra[campo] = ""


def asociar_magnetico(puerta_id: str, sensor_id: str) -> dict | None:
    """El magnético que dice si ESTA puerta está abierta. Vacío = ninguno."""
    def _apply(data):
        if sensor_id and not any(x["id"] == sensor_id for x in data["sensors"]):
            return None
        puerta = next((p for p in data["puertas"] if p["id"] == puerta_id), None)
        if puerta is None:
            return None
        puerta["sensor_id"] = sensor_id
        if sensor_id:
            _una_sola(data, puerta, "sensor_id", sensor_id)
        return puerta
    return _mutate(_apply)


def set_door_grupo(puerta_id: str, *, anclados: list[str] | None = None,
                   cerradura: str | None = None) -> dict | None:
    """Cambia la cerradura ("_ninguna" o el id de una de Accesos) y/o los
    anclados de una Puerta del plano."""
    def _apply(data):
        puerta = next((p for p in data["puertas"] if p["id"] == puerta_id), None)
        if puerta is None:
            return None
        if cerradura is not None:
            if cerradura == "_ninguna":
                puerta["cerradura_id"] = ""
            elif any(d["id"] == cerradura for d in data["doors"]):
                puerta["cerradura_id"] = cerradura
                _una_sola(data, puerta, "cerradura_id", cerradura)
        if anclados is not None:
            limpios = list(dict.fromkeys(
                r for r in anclados
                if isinstance(r, str) and r.split(":", 1)[0] in ("lights", "ir_remotes")))
            for otra in data["puertas"]:
                if otra is not puerta:
                    otra["anclados"] = [r for r in otra.get("anclados", []) if r not in limpios]
            puerta["anclados"] = limpios
        return puerta
    return _mutate(_apply)


def cerraduras_prestadas(data: dict | None = None) -> set[str]:
    """Cerraduras de Accesos que ya están dentro de una Puerta del plano."""
    datos = data if data is not None else _read()
    return {p["cerradura_id"] for p in datos.get("puertas", []) if p.get("cerradura_id")}


def anclados_a_puertas(data: dict | None = None) -> set[str]:
    """Refs de todo lo que va dentro de alguna Puerta (no sale suelto)."""
    datos = data if data is not None else _read()
    return {r for p in datos.get("puertas", []) for r in p.get("anclados", [])}


def magneticos_asociados(data: dict | None = None) -> dict[str, str]:
    """{sensor_id: puerta_id} de los magnéticos que ya van dentro de una Puerta."""
    datos = data if data is not None else _read()
    return {p["sensor_id"]: p["id"] for p in datos.get("puertas", []) if p.get("sensor_id")}


def delete_door(door_id: str) -> None:
    _delete("doors", door_id)


def update_door(door_id: str, name: str, node_id: str, node_name: str, pin: str, pulse_seconds: int = 2,
                show_on_floor: bool = False, floor_icon: str = "", *,
                maniobra: dict | None = None) -> dict | None:
    """`maniobra` ({modo, apertura_s, espera_s, cierre_s}) None = no tocarla."""
    current = next((d for d in _read()["doors"] if d["id"] == door_id), None)
    cambios = {
        "name": name, "node_id": node_id, "node_name": node_name, "pin": pin,
        "topic_cmd": command_topic(node_name, pin),
        "topic_state": sensor_topic(node_name, pin),
        "pulse_seconds": pulse_seconds,
        **floor_fields(show_on_floor, floor_icon, current),
    }
    if maniobra is not None:
        cambios.update(_maniobra(maniobra.get("modo", MODO_PULSO), maniobra.get("apertura_s"),
                                 maniobra.get("espera_s"), maniobra.get("cierre_s")))
    return _update("doors", door_id, cambios)


# ── Luces ─────────────────────────────────────────────────────────────────────
# room_id agrupa las luces por estancia (ver add_room/list_rooms más abajo) —
# opcional, "" significa "sin estancia asignada".
# Cómo se acciona una luz. RELE es la de siempre (GPIO por SSH o MQTT); MANDO es
# una luz que solo se enciende por infrarrojos, como la del ventilador de techo:
# no tiene relé ni topic, tiene dos teclas de un mando virtual.
LUZ_RELE, LUZ_MANDO = "rele", "mando"

# Qué es el aparato, para el icono y para cómo se le llama en la pantalla. La
# mecánica es la misma para todos (encender/apagar y guardar el estado), así que
# comparten colección con las luces a propósito: de ahí les viene gratis salir en
# el plano, en los accesos rápidos del Resumen, en las automatizaciones y en la
# paleta de comandos. Un ventilador de techo y una tele que se encienden con el
# mando son eso: un interruptor con otro icono.
# "persiana": dos señales, una por sentido. Sale de un mando: la tecla de
# «encender» es SUBIR y la de «apagar», BAJAR (y opcionalmente btn_parar).
ASPECTOS = ("luz", "ventilador", "tv", "enchufe", "persiana", "otro")

# Icono de cada uno. Vive aquí y no en la vista porque lo necesitan tres sitios:
# la pestaña Accesorios, el catálogo del plano y el del Resumen. Con una copia
# por sitio, un accesorio nuevo salía con icono distinto según dónde se mirara.
ICONO_ASPECTO = {
    "luz": "lightbulb", "ventilador": "fan", "tv": "tv",
    "enchufe": "plug", "persiana": "blinds", "otro": "toggle-right",
}


def es_luz(item: dict) -> bool:
    """Si esta ficha de la colección `lights` es una luz de verdad o un
    accesorio (el ventilador, la tele). Se pregunta desde varios sitios y
    siempre con la misma regla: sin aspecto, es una luz de las de antes."""
    return (item.get("aspecto") or "luz") == "luz"

# Cómo se apaga y enciende con el mando, que no todos los mandos son iguales:
#   DOS_TECLAS  el ventilador de techo, con «Luz ON» y «Luz OFF» separadas.
#   UNA_TECLA   la tele, con una sola tecla de encendido que hace las dos cosas.
# Con una sola tecla el panel no puede SABER si está encendido: manda la misma
# orden siempre y se limita a llevar la cuenta. Si alguien la apaga con el mando
# de la mano, el panel se queda creyendo lo contrario hasta que se le vuelva a
# dar (lo mismo que le pasa a cualquier mando de toda la vida).
DOS_TECLAS, UNA_TECLA = "dos", "una"
MODOS_ENCENDIDO = ("", "continuo", "1h", "2h", "3h")


def _modo_encendido(valor: str) -> str:
    return valor if valor in MODOS_ENCENDIDO else ""


def _pausa_secuencia(valor) -> float:
    try:
        return max(0.0, float(valor))
    except (TypeError, ValueError):
        return 1.0


def _tecla_existe(data: dict, remote_id: str, button_id: str) -> bool:
    if not remote_id or not button_id:
        return False
    remote = next((r for r in data["ir_remotes"] if r.get("id") == remote_id), None)
    return bool(remote and any(b.get("id") == button_id for b in remote.get("buttons", [])))


def _tecla_valida(data: dict, remote_id: str, button_id: str) -> str:
    return button_id if _tecla_existe(data, remote_id, button_id) else ""


def _campos_luz(kind: str, node_name: str, pin: str, remote_id: str,
                btn_on: str, btn_off: str,
                mando_modo: str = DOS_TECLAS, modo_encendido: str = "",
                btn_continuo: str = "", btn_timing: str = "",
                pausa_secuencia_s: float = 1.0,
                apagar_luz_al_encender: bool = False, btn_luz: str = "",
                luz_repeticiones: int = 25, luz_intervalo_s: float = 0.12) -> dict:
    """Lo que distingue a una luz de relé de una de mando.

    Una de mando se queda SIN topics a propósito: no hay nada publicando su
    estado ni escuchando órdenes, y dejar ahí un "casa//" con el nodo vacío haría
    que el bus se suscribiera a un topic inventado."""
    if kind == LUZ_MANDO:
        modo = mando_modo if mando_modo in (DOS_TECLAS, UNA_TECLA) else DOS_TECLAS
        # Con una sola tecla se guarda la misma en los dos sitios: así todo lo
        # que lea la ficha (el envío, el inventario, las pruebas) encuentra
        # siempre una tecla donde la busca, y el modo solo decide si se
        # distinguen.
        if modo == UNA_TECLA:
            btn_off = btn_on
        return {
            "kind": LUZ_MANDO, "topic_cmd": "", "topic_state": "",
            "remote_id": remote_id, "btn_on": btn_on, "btn_off": btn_off,
            "mando_modo": modo,
            "modo_encendido": _modo_encendido(modo_encendido),
            "btn_continuo": btn_continuo, "btn_timing": btn_timing,
            "pausa_secuencia_s": _pausa_secuencia(pausa_secuencia_s),
            "apagar_luz_al_encender": bool(apagar_luz_al_encender),
            "btn_luz": btn_luz,
            "luz_repeticiones": _repeticiones_luz(luz_repeticiones),
            "luz_intervalo_s": _intervalo_luz(luz_intervalo_s),
        }
    return {
        "kind": LUZ_RELE,
        "topic_cmd": command_topic(node_name, pin),
        "topic_state": sensor_topic(node_name, pin),
        "remote_id": "", "btn_on": "", "btn_off": "", "mando_modo": DOS_TECLAS,
        "modo_encendido": "", "btn_continuo": "", "btn_timing": "",
        "pausa_secuencia_s": 1.0,
        "apagar_luz_al_encender": False, "btn_luz": "",
        "luz_repeticiones": 25, "luz_intervalo_s": 0.12,
    }


def add_light(name: str, node_id: str, node_name: str, pin: str, room_id: str = "",
              show_on_floor: bool = False, floor_icon: str = "",
              kind: str = LUZ_RELE, remote_id: str = "", btn_on: str = "",
              btn_off: str = "", aspecto: str = "luz",
              mando_modo: str = DOS_TECLAS, auto_apagado_min: int = 0,
              modo_encendido: str = "", btn_continuo: str = "",
              btn_timing: str = "", pausa_secuencia_s: float = 1.0,
              apagar_luz_al_encender: bool = False, btn_luz: str = "",
              luz_repeticiones: int = 25, luz_intervalo_s: float = 0.12) -> dict:
    datos = _read()
    if kind == LUZ_MANDO:
        btn_continuo = _tecla_valida(datos, remote_id, btn_continuo)
        btn_timing = _tecla_valida(datos, remote_id, btn_timing)
        btn_luz = _tecla_valida(datos, remote_id, btn_luz)
        modo_encendido = _modo_encendido(modo_encendido)
    else:
        modo_encendido, btn_continuo, btn_timing = "", "", ""
    item = {
        "name": name, "node_id": node_id, "node_name": node_name, "pin": pin,
        **_campos_luz(kind, node_name, pin, remote_id, btn_on, btn_off, mando_modo,
                       modo_encendido, btn_continuo, btn_timing, pausa_secuencia_s,
                       apagar_luz_al_encender, btn_luz, luz_repeticiones, luz_intervalo_s),
        "aspecto": aspecto if aspecto in ASPECTOS else "luz",
        "auto_apagado_min": _entero(auto_apagado_min, por_defecto=0, minimo=0)
        if kind == LUZ_MANDO else 0,
        "room_id": room_id,
        **floor_fields(show_on_floor, floor_icon, None),
    }
    return _add("lights", "light", item)


PERSIANA_RELE = "persiana_rele"
# Cómo está cada persiana, para verlo desde cualquier aparato:
# "subiendo" | "bajando" | "subida" | "bajada" | "parada" (a medias).
ESTADOS_PERSIANA = ("subiendo", "bajando", "subida", "bajada", "parada")


def set_persiana_estado(light_id: str, estado: str) -> None:
    if estado not in ESTADOS_PERSIANA:
        return
    _mutate(lambda data: data.setdefault("persianas_estado", {}).__setitem__(light_id, estado))


def add_persiana(name: str, node_id: str, node_name: str, pin_subir: str,
                 pin_bajar: str, room_id: str = "", recorrido_s: int = 7) -> dict:
    """Persiana de motor con DOS relés (uno por sentido), en un nodo (Pi o
    ESP32). Vive en `lights` porque se usa como cualquier aparato (plano,
    baldosas, estancias), pero con kind propio: ver operations.mover_persiana_rele."""
    item = {
        "name": name, "node_id": node_id, "node_name": node_name, "pin": "",
        "kind": PERSIANA_RELE, "aspecto": "persiana",
        "pin_subir": pin_subir, "pin_bajar": pin_bajar,
        "topic_subir": command_topic(node_name, pin_subir),
        "topic_bajar": command_topic(node_name, pin_bajar),
        "topic_cmd": "", "topic_state": "", "remote_id": "", "btn_on": "", "btn_off": "",
        "mando_modo": DOS_TECLAS, "recorrido_s": int(recorrido_s), "room_id": room_id,
        "floor_icon": "blinds",
    }
    return _add("lights", "light", item)


def delete_light(light_id: str) -> None:
    _delete("lights", light_id)


def update_light(light_id: str, name: str, node_id: str, node_name: str, pin: str, room_id: str = "",
                 show_on_floor: bool = False, floor_icon: str = "",
                 kind: str = LUZ_RELE, remote_id: str = "", btn_on: str = "",
                 btn_off: str = "", aspecto: str = "luz",
                 mando_modo: str = DOS_TECLAS, auto_apagado_min: int = 0,
                 modo_encendido: str = "", btn_continuo: str = "",
                 btn_timing: str = "", pausa_secuencia_s: float = 1.0,
                 apagar_luz_al_encender: bool = False, btn_luz: str = "",
                 luz_repeticiones: int = 25, luz_intervalo_s: float = 0.12) -> dict | None:
    datos = _read()
    current = next((l for l in datos["lights"] if l["id"] == light_id), None)
    if kind == LUZ_MANDO:
        btn_continuo = _tecla_valida(datos, remote_id, btn_continuo)
        btn_timing = _tecla_valida(datos, remote_id, btn_timing)
        btn_luz = _tecla_valida(datos, remote_id, btn_luz)
        modo_encendido = _modo_encendido(modo_encendido)
    else:
        modo_encendido, btn_continuo, btn_timing = "", "", ""
    return _update("lights", light_id, {
        "name": name, "node_id": node_id, "node_name": node_name, "pin": pin,
        **_campos_luz(kind, node_name, pin, remote_id, btn_on, btn_off, mando_modo,
                       modo_encendido, btn_continuo, btn_timing, pausa_secuencia_s,
                       apagar_luz_al_encender, btn_luz, luz_repeticiones, luz_intervalo_s),
        "aspecto": aspecto if aspecto in ASPECTOS else "luz",
        "auto_apagado_min": _entero(auto_apagado_min, por_defecto=0, minimo=0)
        if kind == LUZ_MANDO else 0,
        "room_id": room_id,
        **floor_fields(show_on_floor, floor_icon, current),
    })


def set_modo_encendido(light_id: str, modo: str) -> dict | None:
    if modo not in MODOS_ENCENDIDO:
        return None

    def _apply(data):
        light = next((x for x in data["lights"] if x.get("id") == light_id), None)
        if light is None or light.get("kind") != LUZ_MANDO:
            return None
        remote_id = light.get("remote_id", "")
        if modo == "continuo" and not _tecla_existe(data, remote_id, light.get("btn_continuo", "")):
            return None
        if modo in ("2h", "3h") and not _tecla_existe(data, remote_id, light.get("btn_timing", "")):
            return None
        light["modo_encendido"] = modo
        return light

    return _mutate(_apply)


def secuencia_encendido(light: dict) -> list[tuple[str, float]]:
    on = light.get("btn_on", "")
    pausa = _pausa_secuencia(light.get("pausa_secuencia_s", 1.0))
    modo = light.get("modo_encendido", "")
    if modo == "continuo" and light.get("btn_continuo"):
        return [(on, 0), (light["btn_continuo"], pausa)]
    if modo == "2h" and light.get("btn_timing"):
        return [(on, 0), (light["btn_timing"], pausa)]
    if modo == "3h" and light.get("btn_timing"):
        return [(on, 0), (light["btn_timing"], pausa), (light["btn_timing"], pausa)]
    return [(on, 0)]


def pasos_apagar_luz(light: dict) -> list[tuple[str, float]]:
    """Pulsaciones que emulan mantener pulsada la tecla Luz."""
    if not light.get("apagar_luz_al_encender") or not light.get("btn_luz"):
        return []
    repeticiones = _repeticiones_luz(light.get("luz_repeticiones", 25))
    intervalo = _intervalo_luz(light.get("luz_intervalo_s", 0.12))
    return [(light["btn_luz"], 0 if indice == 0 else intervalo)
            for indice in range(repeticiones)]


def duracion_ciclo_min(modo: str) -> int:
    return {"continuo": 0, "1h": 60, "2h": 120, "3h": 180}.get(modo, 0)


# ── Estancias (agrupación de luces) ──────────────────────────────────────────
def list_rooms() -> list[dict]:
    return _read()["rooms"]


def add_room(name: str) -> dict:
    return _add("rooms", "room", {"name": name, "entidades": []})


def update_room(room_id: str, name: str, entidades: list[str]) -> dict | None:
    """Actualiza nombre y miembros explícitos en una sola escritura atómica."""
    limpias = list(dict.fromkeys(
        ref for ref in entidades if isinstance(ref, str) and ":" in ref
    ))
    return _update("rooms", room_id, {
        "name": (name or "").strip(),
        "entidades": limpias,
    })


def set_room_equipos_vista(room_id: str,
                           refs: list[str] | None) -> dict | None:
    """Equipos/nodos visibles en una estancia, en orden.

    ``None`` elimina la personalización y recupera sus miembros efectivos.
    La normalización común descarta duplicados, tipos ajenos e ids borrados.
    """
    def _apply(data):
        for room in data["rooms"]:
            if room["id"] != room_id:
                continue
            if refs is None:
                room.pop("equipos_vista", None)
            else:
                room["equipos_vista"] = list(refs)
            return room
        return None

    return _mutate(_apply)


def referencias_estancia(room_id: str, data: dict | None = None) -> set[str]:
    """Miembros efectivos: luces por room_id más las refs añadidas a mano."""
    datos = data if data is not None else _read()
    room = next((r for r in datos["rooms"] if r.get("id") == room_id), None)
    if room is None:
        return set()
    refs = {
        f"lights:{light['id']}" for light in datos["lights"]
        if light.get("room_id") == room_id
    }
    refs.update(room.get("entidades") or [])
    return refs


def referencia_en_estancia(room_id: str, referencia: str) -> bool:
    datos = _read()
    refs = referencias_estancia(room_id, datos)
    if referencia in refs:
        return True
    # La tablet controla una Puerta del plano, pero los eventos actúan sobre
    # su cerradura. La cerradura hereda la estancia de esa Puerta sin tener
    # que duplicar ``doors:<id>`` en la ficha de habitación.
    coleccion, _, entity_id = referencia.partition(":")
    if coleccion == "doors":
        return any(p.get("cerradura_id") == entity_id
                   and f"puertas:{p['id']}" in refs
                   for p in datos["puertas"])
    return False


def delete_room(room_id: str) -> None:
    """Borrar una estancia NO borra sus luces: se quedan sin estancia y pasan
    al bloque "SIN ESTANCIA" de la pestaña Luces.

    El barrido del room_id va en la MISMA mutación que la baja de la estancia
    (un solo _mutate) para que no pueda quedar a medias. Sin él, las luces
    seguían apuntando a una estancia que ya no existía: no se borraban del
    fichero, pero tampoco se pintaban en ningún sitio —ni en su estancia, que
    ya no estaba, ni en "sin estancia", porque su room_id no estaba vacío—,
    así que desaparecían de la vista sin haberse borrado."""
    def _apply(data):
        data["rooms"] = [r for r in data["rooms"] if r.get("id") != room_id]
        for light in data["lights"]:
            if light.get("room_id") == room_id:
                light["room_id"] = ""

    _mutate(_apply)


# ── Cámaras ──────────────────────────────────────────────────────────────────────────────────
def add_camera(name: str, url: str, icon: str, kind: str = "embed") -> dict:
    return _add("cameras", "cam", {"name": name, "url": url, "icon": icon, "kind": kind})


def delete_camera(camera_id: str) -> None:
    _delete("cameras", camera_id)


def update_camera(camera_id: str, name: str, url: str, icon: str, kind: str = "embed",
                   show_on_floor: bool = False, floor_icon: str = "") -> dict | None:
    current = next((c for c in _read()["cameras"] if c["id"] == camera_id), None)
    return _update("cameras", camera_id, {
        "name": name, "url": url, "icon": icon, "kind": kind,
        **floor_fields(show_on_floor, floor_icon, current),
    })


# ── Equipos (TODOS: los de siempre y los añadidos desde la web) ──────────────
# Una sola colección y un solo juego de campos, para que la pestaña Equipos
# pueda tratarlos a todos igual — mismo formulario de alta que de edición, y
# lo mismo para un equipo de hace un año que para uno dado de alta hace un
# minuto. user="" significa "solo ping, sin consola ni acciones SSH".
def host_fields(name: str, ip: str, user: str = "", sistema: str = "linux",
                mac: str = "", ping_retries: str | int = 1, icon: str = "server",
                rdp_user: str = "", rdp_launch_host: str = "") -> dict:
    """Normaliza en un único sitio lo que llega de CUALQUIER formulario de
    equipo. Que el alta y la edición pasen las dos por aquí es lo que impide
    que se cuele un usuario con espacios (" " no es un usuario) o unos
    reintentos de ping en 0, que dejaría al equipo sin comprobar nunca."""
    try:
        reintentos = max(1, int(ping_retries or 1))
    except (TypeError, ValueError):
        reintentos = 1
    return {
        "name": name.strip(),
        "ip": ip.strip(),
        "user": user.strip(),
        # Cuenta con la que entra el escritorio remoto. Es OTRA cosa que el
        # usuario SSH: en un PC el SSH puede ir con una cuenta y el RDP
        # ser la sesión de otra persona.
        "rdp_user": rdp_user.strip(),
        # Desde QUÉ equipo se abre la sesión remota. Vacío = desde el navegador
        # de quien pulsa (se le pasa la dirección al sistema o se le baja el
        # .rdp). Con un id de equipo puesto, el servidor entra por SSH a ESE
        # equipo y abre allí el cliente — ver domains/nodes/rdp.py.
        "rdp_launch_host": rdp_launch_host.strip(),
        "os": sistema if sistema in SISTEMAS else "linux",
        "mac": (mac or "").strip() or None,
        "ping_retries": reintentos,
        "icon": icon or "server",
    }


def mutar(mutator):
    """Ciclo leer-modificar-escribir atómico, para quien necesite tocar varias
    colecciones de una vez (ver nodes/referencias.py). Es _mutate con nombre
    público: el ciclo con cerrojo no debe reimplementarse fuera."""
    return _mutate(mutator)


def get_all_hosts() -> list[dict]:
    return _read()["hosts"]


def add_host(**campos) -> dict:
    """El equipo nuevo entra al FINAL de la lista (order = cuántos había), no
    al principio: quien acaba de darlo de alta espera verlo aparecer abajo,
    no colado entre los que ya tenía ordenados a su gusto."""
    nuevo_id = _new_id("host")

    def _apply(data):
        data["hosts"].append({
            "id": nuevo_id,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "order": len(data["hosts"]),
            "acciones_extra": [],
            **campos,
        })
        # Se devuelve buscándolo DESPUÉS de que _mutate lo normalice, para que
        # quien llame reciba la ficha con la forma definitiva y no la cruda.
        return lambda: next(h for h in data["hosts"] if h["id"] == nuevo_id)

    return _mutate(_apply)()


def move_host(host_id: str, direction: int) -> None:
    """direction: -1 sube el equipo una posición, +1 lo baja. Intercambia el
    `order` con el vecino, igual que move_widget en el Resumen."""
    def _apply(data):
        items = data["hosts"]  # ya vienen ordenados por _normalizar_equipos
        idx = next((i for i, h in enumerate(items) if h["id"] == host_id), None)
        if idx is None:
            return
        destino = idx + direction
        if not (0 <= destino < len(items)):
            return
        items[idx]["order"], items[destino]["order"] = items[destino]["order"], items[idx]["order"]

    _mutate(_apply)


def add_host_with_id(item: dict) -> dict:
    """Alta conservando el id indicado — solo para la migración de los equipos
    que ya venían con id literal (raspberry, pi_zero, iphone...)."""
    return _add_with_id("hosts", item)


def update_host(host_id: str, **campos) -> dict | None:
    return _update("hosts", host_id, campos)


def delete_host(host_id: str) -> None:
    """Al borrar un equipo hay que llevarse también su último estado de ping.
    Si no, la entrada se queda huérfana en host_online para siempre con el
    valor que tuviera al borrarlo — y si era True, el contador "Equipos en
    línea" del Resumen sigue sumándola aunque el equipo ya no exista."""
    _delete("hosts", host_id)

    def _apply(data):
        data["host_online"].pop(host_id, None)

    _mutate(_apply)


def find_host_by_ip(ip: str) -> dict | None:
    return next((h for h in _read()["hosts"] if h["ip"] == ip), None)


def find_host_by_id(host_id: str) -> dict | None:
    return next((h for h in _read()["hosts"] if h["id"] == host_id), None)


# ── Estado en vivo de sensores/puertas/luces dinámicos (vía MQTT) ───────────
# Guardado aparte de nodes/sensors/... para no reescribir toda la config en
# cada evento MQTT; misma fuente de verdad compartida entre workers que usa
# shared_state.py para el sistema de alarma clásico.
def get_sensor_state(entity_id: str) -> bool:
    return _read().get("sensor_states", {}).get(entity_id, False)


def set_sensor_state(entity_id: str, value: bool) -> None:
    def _apply(data):
        data["sensor_states"][entity_id] = value

    _mutate(_apply)
    # El aviso va DESPUÉS de escribir: quien despierte va a releer el fichero
    # y tiene que encontrarse ya el valor nuevo (ver core/bus.py).
    bus.publicar(bus.SENSORES)


def _aplicar_estado_mando(data: dict, light_id: str, value: bool, ahora: float,
                          ciclo_min: int | None = None) -> bool:
    """Camino único, dentro de una mutación ya abierta, para un accesorio IR."""
    light = next((x for x in data["lights"] if x.get("id") == light_id), None)
    if light is None or light.get("kind") != LUZ_MANDO:
        return False
    actual = bool(data["sensor_states"].get(light_id, False))
    nuevo = bool(value)
    data["sensor_states"][light_id] = nuevo
    if nuevo and not actual:
        light["encendido_en"] = float(ahora)
        if ciclo_min is None:
            light.pop("ciclo_min", None)
        else:
            light["ciclo_min"] = max(0, int(ciclo_min))
    elif nuevo and ciclo_min is not None:
        # Un fallo después de ON deja el aparato en su ciclo inicial de 1 h.
        # No se toca encendido_en: el ciclo sigue contando desde la activación.
        light["ciclo_min"] = max(0, int(ciclo_min))
    elif not nuevo:
        light.pop("encendido_en", None)
        light.pop("ciclo_min", None)
    return nuevo != actual


def set_mando_state(light_id: str, value: bool, ahora: float | None = None,
                    ciclo_min: int | None = None) -> bool:
    """Actualiza el booleano de un accesorio por mando y su inicio de ciclo.

    Devuelve si hubo transición. Encender de nuevo algo que ya estaba encendido
    no alarga su ciclo; apagar siempre elimina una marca antigua que pudiera
    quedar de una edición manual del fichero.
    """
    if ahora is None:
        ahora = time.time()

    def _apply(data):
        return _aplicar_estado_mando(data, light_id, value, ahora, ciclo_min)

    cambio = _mutate(_apply)
    if cambio:
        bus.publicar(bus.SENSORES)
    return cambio


def get_all_sensor_states(real: bool = False) -> dict:
    """`real=True` ignora los valores forzados de core/pruebas.py: lo usan las
    automatizaciones y todo lo que actúa sobre la casa."""
    datos = _read().get("sensor_states", {})
    return datos if real else pruebas.aplicar_sensores(datos)


# ── Estado en vivo de ping de equipos extra ──────────────────────────────────
# Igual que sensor_states: el bucle que hace ping corre una sola vez por
# proceso, pero cada sesión/pestaña necesita poder leerlo, así que se persiste
# aquí en vez de guardarse solo en el `self` de la sesión que hizo el ping.
def set_host_online_bulk(updates: dict) -> None:
    """`updates` trae SIEMPRE todos los equipos de la vuelta de ping, así que
    se reemplaza el diccionario entero en vez de fusionarlo: así cualquier
    entrada huérfana (equipo borrado en una versión anterior, que no limpiaba
    host_online) se cae sola en el primer ping tras arrancar."""
    def _apply(data):
        data["host_online"] = dict(updates)

    _mutate(_apply)
    bus.publicar(bus.EQUIPOS)


def get_all_host_online(real: bool = False) -> dict:
    datos = _read().get("host_online", {})
    return datos if real else pruebas.aplicar_equipos(datos)


# ── Botones de acción personalizados por host ────────────────────────────────
# Mismo mecanismo para CUALQUIER host (fijo del registry o extra dado de alta
# en Equipos) — se guardan aparte, referenciados solo por host_id (un string),
# así que aplican igual sin importar de dónde viene el host.
# kind: "ssh_command" (ejecuta y muestra la salida) | "pin_write" (pone un pin
# a on/off) | "pin_read" (lee el estado de un pin y muestra la salida cruda).
def list_host_buttons(host_id: str) -> list[dict]:
    return [b for b in _read()["host_buttons"] if b["host_id"] == host_id]


def add_host_button(host_id: str, label: str, kind: str, value: str) -> dict:
    return _add("host_buttons", "btn", {"host_id": host_id, "label": label, "kind": kind, "value": value})


def delete_host_button(button_id: str) -> None:
    _delete("host_buttons", button_id)


# ── Mural de vídeo ───────────────────────────────────────────────────────────
# Una sola rejilla persistente (no varias vistas guardadas): un reparto
# elegido + qué cámara va en cada hueco. (id, etiqueta, columnas, filas) —
# repartos cuadrados o rectangulares de verdad, no el "1 grande + 5 pequeñas"
# de un NVR profesional, que exigiría celdas de tamaños distintos.
VIDEO_WALL_LAYOUTS = (
    ("1", "1", 1, 1),
    ("2h", "2 · lado a lado", 2, 1),
    ("2v", "2 · apiladas", 1, 2),
    ("4", "4", 2, 2),
    ("6", "6", 3, 2),
    ("8", "8", 4, 2),
    ("9", "9", 3, 3),
    ("16", "16", 4, 4),
)
_VIDEO_WALL_LAYOUT_IDS = {l[0] for l in VIDEO_WALL_LAYOUTS}


def get_video_wall() -> dict:
    return _read()["video_wall"]


def set_video_wall_layout(layout: str) -> None:
    if layout not in _VIDEO_WALL_LAYOUT_IDS:
        return

    def _apply(data):
        vw = data["video_wall"]
        vw["layout"] = layout
        total = next(c * r for lid, _, c, r in VIDEO_WALL_LAYOUTS if lid == layout)
        # Al reducir el reparto, los huecos que ya no caben se sueltan: una
        # cámara "colocada" en el hueco 12 de un mural que pasa a tener 4
        # quedaría asignada pero invisible e inalcanzable para siempre.
        vw["slots"] = {k: v for k, v in vw["slots"].items() if int(k) < total}

    _mutate(_apply)


def set_video_wall_slot(slot: str, camera_id: str) -> None:
    def _apply(data):
        slots = data["video_wall"]["slots"]
        # Una cámara solo puede estar en UN hueco: si ya estaba en otro, se
        # retira de allí antes de ponerla en el nuevo, para no verla repetida.
        for k in [k for k, v in slots.items() if v == camera_id]:
            del slots[k]
        slots[slot] = camera_id

    _mutate(_apply)


def clear_video_wall_slot(slot: str) -> None:
    def _apply(data):
        data["video_wall"]["slots"].pop(slot, None)

    _mutate(_apply)


def clear_video_wall() -> None:
    def _apply(data):
        data["video_wall"]["slots"] = {}

    _mutate(_apply)


# ── Mandos IR (Broadlink) ─────────────────────────────────────────────────────
# Un "mando" es solo un nombre + una lista de botones — el hub físico es uno
# solo (IP_BROADLINK/MAC_BROADLINK, ver domains/devices/ir_bus.py), así que
# aquí no se guarda ninguna referencia a él. Cada botón lleva su propio código
# aprendido (hex) — aprenderlo es domains/devices/ir_bus.learn_button(),
# dispararlo es ir_bus.send_button(código).
#
# pos_top/pos_left son la posición (%) del botón DENTRO del cuerpo del mando
# virtual (ver ui/dashboard/views/ir_remotes.py) — igual que floor_top/
# floor_left posicionan un icono sobre el plano de planta, solo que aquí el
# "plano" es la silueta del mando.
#
# La posición de un botón NO puede depender nunca de su sitio en la lista.
# Antes se calculaba con una rejilla a partir del índice, y eso hacía que al
# borrar un botón se corrieran los índices de los demás y saltaran de columna
# — el mando entero se reorganizaba solo. Ahora un botón sin posición recibe
# un hueco libre calculado contra los botones YA colocados (no contra su
# índice), se le guarda, y a partir de ahí no se vuelve a mover nunca salvo
# que lo arrastres tú.
def _asegurar_posiciones(remote: dict) -> None:
    ancho = int(remote.get("body_w") or 300)
    alto = int(remote.get("body_h") or 820)
    ocupados = [
        (_porcentaje(b.get("pos_left"), ancho), _porcentaje(b.get("pos_top"), alto))
        for b in remote["buttons"]
        if b.get("pos_top") and b.get("pos_left")
    ]
    for boton in remote["buttons"]:
        if boton.get("pos_top") and boton.get("pos_left"):
            continue
        x, y = _primer_hueco(ocupados, ancho, alto)
        boton["pos_left"] = f"{x / ancho * 100:.2f}%"
        boton["pos_top"] = f"{y / alto * 100:.2f}%"
        ocupados.append((x, y))


def _primer_hueco(ocupados: list[tuple[float, float]], ancho: int, alto: int) -> tuple[float, float]:
    """Primer punto del cuerpo (px) donde cabe una tecla sin pisar a las que ya
    están, barriendo en rejilla de arriba abajo. Si no queda sitio, el centro."""
    paso = _TECLA_PX + 12
    margen = _TECLA_PX / 2 + 6
    y = margen
    while y <= alto - margen:
        x = margen
        while x <= ancho - margen:
            if all(abs(x - ox) >= _TECLA_PX or abs(y - oy) >= _TECLA_PX for ox, oy in ocupados):
                return x, y
            x += paso
        y += paso
    return ancho / 2, alto / 2


def get_all_ir_remotes() -> list[dict]:
    return _read()["ir_remotes"]


def add_ir_remote(name: str, icon: str = "tv",
                   show_on_floor: bool = False, floor_icon: str = "",
                   plantilla: str = "vacio") -> dict:
    """`plantilla` rellena el mando de entrada con TODOS los botones de un
    mando físico real, ya colocados pero sin señal aprendida — ver
    ../devices/remote_templates.py. "vacio" lo deja como estaba: sin botones."""
    from ..devices import remote_templates

    botones = [
        {"id": _new_id("btn"), **b} for b in remote_templates.botones(plantilla)
    ]
    # Las placas de la plantilla dicen a qué teclas agrupan por su NOMBRE
    # (los ids se generan aquí); se traducen a ids, que es lo que aguanta un
    # renombrado posterior.
    id_por_nombre = {b["label"]: b["id"] for b in botones}
    grupos = []
    for grupo in remote_templates.grupos(plantilla):
        miembros = [id_por_nombre[n] for n in grupo["members"] if n in id_por_nombre]
        if miembros:
            grupos.append({**grupo, "members": miembros})
    # La forma del cuerpo viaja con el mando, no con la plantilla: el de la TV
    # es alto y estrecho y el del ventilador apaisado, y las posiciones de sus
    # botones están en % sobre SU cuerpo. Guardarla aquí es lo que permite
    # que cada mando se pinte con su propia proporción.
    ancho, alto = remote_templates.cuerpo(plantilla)
    item = {
        "name": name, "icon": icon or "tv", "buttons": botones,
        # Placas decorativas del mando real (balancín, rueda, tira de colores,
        # pad de la luz...). No se pulsan: son lo que hace que se reconozca
        # como el mando de verdad y no como círculos sueltos.
        "groups": grupos,
        "body_w": ancho, "body_h": alto,
        # En el plano se ve el MISMO icono que tiene el mando: un mando no
        # necesita dos identidades distintas, y tener que elegir el icono dos
        # veces solo servía para que acabaran descuadrados.
        **floor_fields(show_on_floor, icon or "tv", None),
    }
    return _add("ir_remotes", "ir", item)


def delete_ir_remote(remote_id: str) -> None:
    _delete("ir_remotes", remote_id)


def update_ir_remote(remote_id: str, name: str, icon: str,
                      show_on_floor: bool = False, floor_icon: str = "") -> dict | None:
    current = next((r for r in _read()["ir_remotes"] if r["id"] == remote_id), None)
    return _update("ir_remotes", remote_id, {
        "name": name, "icon": icon or "tv",
        # El icono del plano sigue al del mando: cambiarle el icono al mando
        # lo cambia también donde se ve en la casa, sin tener que acordarse.
        **floor_fields(show_on_floor, icon or "tv", current),
    })


# ── Electrodomésticos simulados ─────────────────────────────────────────────
TIPOS_ELECTRO = ("lavadora", "nevera", "placa", "horno", "extractor", "freidora", "aire")
ICONOS_ELECTRO = {
    "lavadora": "washing-machine", "nevera": "refrigerator",
    "placa": "flame", "horno": "microwave",
    "extractor": "fan", "freidora": "cooking-pot", "aire": "air-vent",
}


def add_electro(name: str, tipo: str, node_id: str = "", node_name: str = "",
                 show_on_floor: bool = False, floor_icon: str = "") -> dict:
    if tipo not in TIPOS_ELECTRO:
        raise ValueError("tipo de electrodoméstico inválido")
    return _add("electrodomesticos", "electro", {
        "name": name.strip() or tipo.capitalize(), "tipo": tipo,
        "node_id": node_id, "node_name": node_name, "simulado": True,
        "estado": {},
        **floor_fields(show_on_floor, floor_icon or ICONOS_ELECTRO[tipo], None),
    })


def update_electro(electro_id: str, name: str, tipo: str, node_id: str = "",
                   node_name: str = "", show_on_floor: bool = False,
                   floor_icon: str = "") -> dict | None:
    if tipo not in TIPOS_ELECTRO:
        raise ValueError("tipo de electrodoméstico inválido")
    current = next((x for x in _read()["electrodomesticos"]
                    if x["id"] == electro_id), None)
    return _update("electrodomesticos", electro_id, {
        "name": name.strip() or tipo.capitalize(), "tipo": tipo,
        "node_id": node_id, "node_name": node_name, "simulado": True,
        **floor_fields(show_on_floor, floor_icon or ICONOS_ELECTRO[tipo], current),
    })


def delete_electro(electro_id: str) -> None:
    _delete("electrodomesticos", electro_id)


def set_electro_estado(electro_id: str, estado: dict) -> dict | None:
    if not isinstance(estado, dict):
        raise ValueError("el estado del electrodoméstico debe ser un diccionario")
    return _update("electrodomesticos", electro_id, {"estado": estado})


def _hueco_libre(remote: dict) -> tuple[str, str]:
    """(pos_top, pos_left) del primer sitio libre del cuerpo.

    Se busca DENTRO del cuerpo actual en vez de agrandarlo: cambiar el tamaño
    del mando obliga a recalcular el % de todas las teclas, y eso movería de
    sitio a las que ya estaban colocadas. Añadir un botón no puede tocar a los
    demás."""
    ancho = int(remote.get("body_w") or 300)
    alto = int(remote.get("body_h") or 820)
    ocupados = [
        (_porcentaje(b.get("pos_left"), ancho), _porcentaje(b.get("pos_top"), alto))
        for b in remote["buttons"]
    ]
    x, y = _primer_hueco(ocupados, ancho, alto)
    return f"{y / alto * 100:.2f}%", f"{x / ancho * 100:.2f}%"


def add_ir_button(remote_id: str, label: str, icon: str, code: str, *,
                  kind: str = "ir") -> dict | None:
    """Añade un botón configurado al mando, en el primer hueco libre.

    ``kind="ir"`` conserva el camino de las señales IR/RF aprendidas;
    ``kind="webos"`` permite crear desde cero una tecla de red sin fingir una
    captura física y convertirla después en el editor.
    """
    via = "webos" if kind == "webos" else "ir"

    def _apply(data):
        for remote in data["ir_remotes"]:
            if remote["id"] == remote_id:
                pos_top, pos_left = _hueco_libre(remote)
                boton = {
                    "id": _new_id("btn"), "label": label, "icon": icon or "circle", "code": code,
                    "kind": via, "text": "", "color": "", "icon_size": "46%",
                    "pos_top": pos_top, "pos_left": pos_left,
                }
                remote["buttons"].append(boton)
                return boton
        return None

    return _mutate(_apply)


def set_ir_button_position(remote_id: str, button_id: str, top: str, left: str) -> dict | None:
    """Persiste la posición (%) de un botón tras arrastrarlo dentro del mando
    virtual — un botón suelto, ver set_ir_button_positions_bulk para varios
    de una vez (lo que usa "Guardar disposición")."""
    def _apply(data):
        for remote in data["ir_remotes"]:
            if remote["id"] != remote_id:
                continue
            for boton in remote["buttons"]:
                if boton["id"] == button_id:
                    boton["pos_top"] = top
                    boton["pos_left"] = left
                    return boton
        return None

    return _mutate(_apply)


# Lado de una tecla, para buscar huecos libres donde colocar un botón nuevo.
# El recorte del cuerpo y el tamaño con que se PINTA cada tecla se calculan
# aparte, al montar la vista (ver _remote_para_ui en state.py): aquí solo se
# guardan coordenadas.
_TECLA_PX = 44


def _porcentaje(valor: str, total: float) -> float:
    try:
        return float(str(valor).rstrip("%")) / 100 * total
    except (TypeError, ValueError):
        return 0.0


def set_ir_button_positions_bulk(remote_id: str, updates: list[dict]) -> None:
    """Guarda de una sola vez la posición de VARIOS botones tras una sesión de
    recolocación — mismo motivo que set_floor_positions_bulk: o se guarda toda
    la disposición nueva o no se guarda ninguna.

    Cada entrada de `updates`: {"id": ..., "top": ..., "left": ...}."""
    def _apply(data):
        for remote in data["ir_remotes"]:
            if remote["id"] != remote_id:
                continue
            pendientes = {u["id"]: u for u in updates}
            for boton in remote["buttons"]:
                u = pendientes.get(boton["id"])
                if u and u.get("top") and u.get("left"):
                    boton["pos_top"] = u["top"]
                    boton["pos_left"] = u["left"]

    _mutate(_apply)


def update_ir_button(remote_id: str, button_id: str, label: str, icon: str,
                      kind: str | None = None, code: str | None = None) -> dict | None:
    """Nombre/icono de un botón, y opcionalmente por dónde se manda (`kind`:
    "ir" o "webos") y su comando webOS (`code`). La señal INFRARROJA no se
    edita a mano nunca: se (re)aprende con set_ir_button_code."""
    def _apply(data):
        for remote in data["ir_remotes"]:
            if remote["id"] != remote_id:
                continue
            for boton in remote["buttons"]:
                if boton["id"] == button_id:
                    boton["label"] = label
                    boton["icon"] = icon or "circle"
                    if kind is not None:
                        boton["kind"] = kind
                    if code is not None:
                        boton["code"] = code
                    return boton
        return None

    return _mutate(_apply)


def set_ir_button_code(remote_id: str, button_id: str, code: str) -> dict | None:
    """Graba en un botón YA EXISTENTE la señal recién aprendida — es lo que
    convierte un botón de plantilla (sin señal) en uno funcional, y también lo
    que permite re-aprender uno que se capturó mal."""
    def _apply(data):
        for remote in data["ir_remotes"]:
            if remote["id"] != remote_id:
                continue
            for boton in remote["buttons"]:
                if boton["id"] == button_id:
                    boton["code"] = code
                    boton["kind"] = "ir"
                    return boton
        return None

    return _mutate(_apply)


def delete_ir_button(remote_id: str, button_id: str) -> None:
    def _apply(data):
        for remote in data["ir_remotes"]:
            if remote["id"] == remote_id:
                remote["buttons"] = [b for b in remote["buttons"] if b["id"] != button_id]

    _mutate(_apply)


def delete_ir_button_by_id(button_id: str) -> bool:
    """Elimina una tecla con su id global, sin que el llamador conozca el mando.

    El id de la tecla es único dentro del fichero; resolver su padre aquí hace
    que el borrado desde Inventario siga el mismo contrato que el resto.
    """
    def _apply(data):
        for remote in data["ir_remotes"]:
            antes = len(remote["buttons"])
            remote["buttons"] = [b for b in remote["buttons"]
                                 if b.get("id") != button_id]
            if len(remote["buttons"]) != antes:
                return True
        return False

    return bool(_mutate(_apply))


# ── Widgets del Resumen ("Centro de Control") ────────────────────────────────
# La pestaña Resumen es completamente configurable: el usuario elige qué
# widgets ver (contadores o accesos rápidos) y en qué orden. label/icon se
# guardan denormalizados en el propio widget (igual que node_name en
# sensores/luces) para no depender de cruzar listas con una Var reactiva al
# pintar — si el grupo/cámara/luz/puerta referenciado se renombra después, el
# widget se queda con el nombre de cuando se añadió, hasta que se borre y
# vuelva a añadir.
def get_all_widgets() -> list[dict]:
    return sorted(_read()["overview_widgets"], key=lambda w: w.get("order", 0))


def add_widget(kind: str, target_id: str, label: str, icon: str) -> dict:
    def _apply(data):
        item = {
            "id": _new_id("widget"), "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "kind": kind, "target_id": target_id, "label": label, "icon": icon,
            "order": len(data["overview_widgets"]),
        }
        data["overview_widgets"].append(item)
        return item

    return _mutate(_apply)


def delete_widget(widget_id: str) -> None:
    def _apply(data):
        data["overview_widgets"] = [w for w in data["overview_widgets"] if w["id"] != widget_id]
        for i, w in enumerate(sorted(data["overview_widgets"], key=lambda w: w.get("order", 0))):
            w["order"] = i

    _mutate(_apply)


# A qué grupo visual pertenece cada acceso rápido — Alarma, Luces, Puertas...
# Es lo que permite pintarlos agrupados por familia en el Resumen (en vez de
# una única lista donde una puerta, una luz y una cámara van intercaladas sin
# ningún orden) Y es lo que usa move_widget para saber con qué vecino
# intercambiar un widget al moverlo: si no se supiera la familia, "mover" un
# acceso de Puertas podría intercambiarlo con uno de Luces que esté al lado en
# el orden global, y como cada familia se pinta en su propia sección, el botón
# parecería no hacer nada.
# (id, etiqueta, icono) — orden en el que se pintan las secciones de accesos
# rápidos del Resumen. "otros" va el último a propósito: es el cajón de sastre
# (ir a una pestaña, ver registros, enviar un aviso), lo menos "acción física
# sobre la casa" de todas.
ACTION_FAMILIES = (
    ("alarma", "Alarma y grupos", "shield"),
    ("luces", "Luces", "lightbulb"),
    ("accesorios", "Accesorios", "toggle-right"),
    ("puertas", "Puertas", "door-open"),
    ("camaras", "Cámaras", "video"),
    ("mandos", "Mandos", "gamepad-2"),
    ("equipos", "Equipos", "server"),
    ("otros", "Otros", "layout-grid"),
)

FAMILIA_ACCION = {
    "action_arm": "alarma", "action_group": "alarma",
    "action_light": "luces",
    "action_door": "puertas",
    "action_camera": "camaras",
    "action_ir_button": "mandos", "action_ir_remote": "mandos",
    "action_rdp": "equipos", "action_host_button": "equipos",
    "action_host_shutdown": "equipos", "action_host_wol": "equipos",
    "action_view": "otros", "action_logs": "otros", "action_notify": "otros",
}


def familia_de(kind: str) -> str:
    """Familia de un widget cualquiera. Los contadores ("stat_*") siguen
    siendo UNA sola familia — no se pintan agrupados por sub-tipo, así que
    basta con que no se mezclen con los accesos rápidos.

    OJO: "action_light" cae aquí en Luces, pero un accesorio (la tele, el
    ventilador) usa ese mismo kind y tiene que ir a Accesorios. Eso no se puede
    decidir solo con el kind —hace falta saber A QUÉ apunta—, así que lo afina
    NodesState.actions_by_family, que sí tiene las fichas delante."""
    if kind.startswith("stat_"):
        return "stat"
    return FAMILIA_ACCION.get(kind, "otros")


# ── Paneles de la pestaña Métricas ───────────────────────────────────────────
# Mismo patrón que los widgets del Resumen: una colección de fichas que el
# usuario añade, quita y ordena, y la pantalla pinta lo que haya. La diferencia
# es que aquí cada ficha lleva además QUÉ mide y en qué forma, porque la gracia
# de esta pantalla es que la monte cada uno con lo que le interese.
#
# La presentación, el intervalo y la operación se guardan por separado. Las
# fichas anteriores siguen funcionando sin escribir una migración en el JSON:
# normalizar_panel completa sus opciones al leerlas.
FORMAS_PANEL = ("linea", "area", "barras", "donut", "circular",
                "barras_hora", "barras_dia")
COLORES_PANEL = ("accent", "warning", "purple", "success", "danger")
AGRUPACIONES_PANEL = ("dia", "hora", "hora_dia", "intervalo")
OPERACIONES_PANEL = ("media", "minimo", "maximo", "ultimo", "conteo")
PERIODOS_PANEL = ("relativo", "personalizado")
ANCHOS_PANEL = ("normal", "amplio")
OPCIONES_PANEL = ("agrupacion", "intervalo_minutos", "operacion", "periodo",
                  "desde", "hasta", "franja", "hora_desde", "hora_hasta", "ancho")
_ENUMS_PANEL = {
    "forma": FORMAS_PANEL, "color": COLORES_PANEL,
    "agrupacion": AGRUPACIONES_PANEL, "operacion": OPERACIONES_PANEL,
    "periodo": PERIODOS_PANEL, "ancho": ANCHOS_PANEL,
}


def _fecha_panel(valor) -> str:
    """Los datetime-local del formulario no llevan zona: rige el reloj local."""
    try:
        fecha = datetime.fromisoformat(str(valor))
        return fecha.isoformat(timespec="minutes") if fecha.tzinfo is None else ""
    except (ValueError, TypeError):
        return ""


def _hora_panel(valor) -> str:
    texto = str(valor)
    return texto if re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", texto) else "00:00"


def normalizar_panel(panel: dict) -> dict:
    """Completa una ficha, incluida la antigua, sin modificarla ni escribir disco."""
    salida = dict(panel)
    forma = panel.get("forma", "barras_dia")
    salida["forma"] = forma if forma in FORMAS_PANEL else "barras_dia"
    serie = str(panel.get("medida", "")).startswith("serie:")
    agrupacion = ("hora" if serie else
                  "hora_dia" if forma == "barras_hora" else "dia")
    defaults = {
        "color": "accent", "agrupacion": agrupacion,
        "operacion": "media" if serie else "conteo",
        "periodo": "relativo", "ancho": "normal",
    }
    for campo, defecto in defaults.items():
        valor = panel.get(campo, defecto)
        salida[campo] = valor if valor in _ENUMS_PANEL[campo] else defecto
    salida["dias"] = min(365, _entero(panel.get("dias", 7), por_defecto=7, minimo=1))
    salida["intervalo_minutos"] = min(1440, _entero(
        panel.get("intervalo_minutos", 60), por_defecto=60, minimo=5))
    salida["franja"] = panel.get("franja") is True
    for campo in ("desde", "hasta"):
        salida[campo] = _fecha_panel(panel.get(campo, ""))
    for campo in ("hora_desde", "hora_hasta"):
        salida[campo] = _hora_panel(panel.get(campo, "00:00"))
    return salida


def list_paneles() -> list[dict]:
    return [normalizar_panel(panel) for panel in
            sorted(_read()["metricas_paneles"], key=lambda p: p.get("orden", 0))]


def add_panel(titulo: str, forma: str, medida: str, dias: int = 7,
              color: str = "accent", **opciones) -> dict:
    def _apply(data):
        item = normalizar_panel({
            "id": _new_id("panel"),
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "titulo": titulo.strip() or "Sin título",
            "forma": forma,
            "medida": medida,
            "dias": dias,
            "color": color,
            "orden": len(data["metricas_paneles"]),
            **{k: v for k, v in opciones.items() if k in OPCIONES_PANEL},
        })
        data["metricas_paneles"].append(item)
        return item

    return _mutate(_apply)


def update_panel(panel_id: str, campos: dict) -> dict | None:
    """Actualiza solo campos conocidos y conserva las elecciones no editadas."""
    permitidos = {"titulo", "forma", "medida", "dias", "color", *OPCIONES_PANEL}

    def _apply(data):
        for panel in data["metricas_paneles"]:
            if panel["id"] != panel_id:
                continue
            actual = normalizar_panel(panel)
            for clave, valor in campos.items():
                if clave not in permitidos:
                    continue
                if clave in _ENUMS_PANEL and valor not in _ENUMS_PANEL[clave]:
                    continue
                if clave == "titulo":
                    valor = str(valor).strip() or actual["titulo"]
                elif clave == "medida":
                    valor = str(valor)
                actual[clave] = valor
            panel.update(normalizar_panel(actual))
            return panel
        return None

    return _mutate(_apply)


def delete_panel(panel_id: str) -> None:
    def _apply(data):
        data["metricas_paneles"] = [p for p in data["metricas_paneles"]
                                    if p["id"] != panel_id]
        # Se renumera para que el orden no acumule huecos al borrar.
        for i, p in enumerate(sorted(data["metricas_paneles"],
                                     key=lambda p: p.get("orden", 0))):
            p["orden"] = i

    _mutate(_apply)


def move_panel(panel_id: str, direccion: int) -> None:
    """direccion: -1 sube, +1 baja. Intercambia con el vecino."""
    def _apply(data):
        items = sorted(data["metricas_paneles"], key=lambda p: p.get("orden", 0))
        actual = next((p for p in items if p["id"] == panel_id), None)
        if actual is None:
            return
        i = items.index(actual)
        j = i + direccion
        if not (0 <= j < len(items)):
            return
        items[i]["orden"], items[j]["orden"] = items[j]["orden"], items[i]["orden"]

    _mutate(_apply)


# ── Planos: alta, baja, renombrado y cuál es el principal ────────────────────
def list_planos() -> list[dict]:
    return sorted(_read()["planos"], key=lambda p: p.get("orden", 0))


def add_plano(nombre: str, imagen: str, ancho: int, alto: int) -> dict:
    """Añade un plano. El primero que entra manda: si no hay ninguno, se queda
    como principal, porque un panel sin plano principal no pinta nada."""
    def _apply(data):
        item = {
            "id": _new_id("plano"),
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "nombre": nombre.strip() or f"Plano {len(data['planos']) + 1}",
            "imagen": imagen,
            "ancho": _entero(ancho, por_defecto=0, minimo=0),
            "alto": _entero(alto, por_defecto=0, minimo=0),
            "orden": len(data["planos"]),
            "principal": not data["planos"],
        }
        data["planos"].append(item)
        return item

    return _mutate(_apply)


def rename_plano(plano_id: str, nombre: str) -> dict | None:
    def _apply(data):
        for p in data["planos"]:
            if p["id"] == plano_id:
                p["nombre"] = nombre.strip() or p["nombre"]
                return p
        return None

    return _mutate(_apply)


def set_plano_baldosas(plano_id: str, refs: list[str] | None) -> dict | None:
    """Qué sale en «Luces y aparatos» bajo ESE plano: lista de refs
    ("lights:<id>", "doors:<id>") en su orden. None = lo de partida (lo que
    está colocado en el plano), que es lo que había antes de poder elegirlo."""
    def _apply(data):
        for p in data["planos"]:
            if p["id"] == plano_id:
                if refs is None:
                    p.pop("baldosas", None)
                else:
                    p["baldosas"] = list(dict.fromkeys(
                        r for r in refs if isinstance(r, str) and ":" in r))
                return p
        return None

    return _mutate(_apply)


def set_plano_principal(plano_id: str) -> bool:
    """Marca uno y desmarca los demás. Exactamente uno, siempre."""
    def _apply(data):
        if not any(p["id"] == plano_id for p in data["planos"]):
            return False
        for p in data["planos"]:
            p["principal"] = p["id"] == plano_id
        return True

    return bool(_mutate(_apply))


def delete_plano(plano_id: str) -> str:
    """Borra el plano y devuelve el nombre de su imagen, para que quien llama
    decida si borra el fichero (no se hace aquí: este módulo no toca imágenes).

    NO se borra el último que queda si hay elementos colocados: dejar la casa sin
    ningún plano y con las posiciones apuntando a la nada es más fácil de hacer
    que de deshacer. Devuelve "" si no se ha borrado.

    Las posiciones que apuntaban a él las limpia _sincronizar_planos, que se
    ejecuta dentro de esta misma escritura."""
    def _apply(data):
        planos = data["planos"]
        objetivo = next((p for p in planos if p["id"] == plano_id), None)
        if objetivo is None or len(planos) <= 1:
            return ""
        imagen = objetivo.get("imagen", "")
        data["planos"] = [p for p in planos if p["id"] != plano_id]
        for i, p in enumerate(sorted(data["planos"], key=lambda p: p.get("orden", 0))):
            p["orden"] = i
        # Si el que se va era el principal, el primero de los que quedan lo
        # hereda — de eso se encarga _sincronizar_planos, que exige que haya uno.
        return imagen

    return _mutate(_apply) or ""


def elementos_de_plano(plano_id: str) -> list[dict]:
    """Qué hay colocado en ese plano: [{"ref", "top", "left"}].

    `ref` es "<colección>:<id>", el mismo apaño que usa el catálogo del plano,
    para que la interfaz no tenga que saber de qué colección viene cada cosa."""
    data = _read()
    salida = []
    for coleccion in COLECCIONES_EN_PLANO:
        for item in data[coleccion]:
            sitio = (item.get("posiciones") or {}).get(plano_id)
            if sitio:
                salida.append({
                    "ref": f"{coleccion}:{item['id']}",
                    "id": item["id"],
                    "nombre": item.get("name", item["id"]),
                    "top": sitio["top"],
                    "left": sitio["left"],
                })
    return salida


# ── Comandos de voz: una frase atada a una acción ────────────────────────────
# Existen porque el reconocimiento por parecido no es suficiente para una casa
# que abre puertas: «buenas noches» no se parece a ningún comando del catálogo,
# y aun así es lo que uno le dice al altavoz. Con esto la frase la elige el
# usuario y la correspondencia es EXACTA, no adivinada.
#
# Una ficha: {"id", "frase", "comando", "creado"}. `comando` es el id del
# catálogo (ver devices/comandos.py) — se guarda el id y no el paso entero para
# que renombrar una luz no deje el comando de voz apuntando a un nombre viejo.
def list_comandos_voz() -> list[dict]:
    return sorted(_read()["comandos_voz"], key=lambda c: c.get("frase", ""))


def add_comando_voz(frase: str, comando: str) -> dict | None:
    """Nuevo. Devuelve None si la frase ya estaba: dos frases iguales apuntando a
    dos acciones distintas es una moneda al aire cada vez que se dicen."""
    limpia = " ".join(frase.strip().lower().split())
    if not limpia or not comando:
        return None

    def _apply(data):
        if any(c["frase"] == limpia for c in data["comandos_voz"]):
            return None
        item = {
            "id": _new_id("voz"),
            "creado": time.strftime("%Y-%m-%d %H:%M:%S"),
            "frase": limpia,
            "comando": comando,
        }
        data["comandos_voz"].append(item)
        return item

    return _mutate(_apply)


def update_comando_voz(voz_id: str, frase: str = "", comando: str = "") -> dict | None:
    def _apply(data):
        for c in data["comandos_voz"]:
            if c["id"] != voz_id:
                continue
            if frase.strip():
                c["frase"] = " ".join(frase.strip().lower().split())
            if comando:
                c["comando"] = comando
            return c
        return None

    return _mutate(_apply)


def delete_comando_voz(voz_id: str) -> None:
    def _apply(data):
        data["comandos_voz"] = [c for c in data["comandos_voz"]
                                if c["id"] != voz_id]

    _mutate(_apply)


def toggle_equipo_en_metricas(host_id: str) -> bool:
    """Enciende o apaga el guardado del histórico de ESE equipo. Devuelve cómo
    se ha quedado."""
    def _apply(data):
        for host in data["hosts"]:
            if host["id"] == host_id:
                host["en_metricas"] = not host.get("en_metricas", False)
                return host["en_metricas"]
        return False

    return bool(_mutate(_apply))


def equipos_en_metricas() -> list[dict]:
    """Los equipos cuyo estado se guarda, con su id y nombre."""
    return [{"id": h["id"], "name": h["name"]}
            for h in _read()["hosts"] if h.get("en_metricas")]


def move_widget(widget_id: str, direction: int) -> None:
    """direction: -1 mueve a la izquierda/arriba, +1 a la derecha/abajo.

    El intercambio es con el vecino de su MISMA familia (ver familia_de), no
    con el vecino del orden global: cada familia se pinta en su propio
    contenedor del Resumen, así que intercambiar con algo de otra familia no
    movería nada en pantalla y el botón parecería estropeado."""
    def _apply(data):
        items = sorted(data["overview_widgets"], key=lambda w: w.get("order", 0))
        target = next((w for w in items if w["id"] == widget_id), None)
        if target is None:
            return
        family = familia_de(target["kind"])
        same_family = [w for w in items if familia_de(w["kind"]) == family]
        idx = same_family.index(target)
        new_idx = idx + direction
        if not (0 <= new_idx < len(same_family)):
            return
        neighbour = same_family[new_idx]
        target["order"], neighbour["order"] = neighbour["order"], target["order"]

    _mutate(_apply)


# ── Mural de cámaras de una estancia (tablet de pared) ───────────────────────
# Cada estancia recuerda su propio reparto y qué cámara va en cada hueco, dentro
# de su ficha (`mural`). Es independiente del Mural del panel: cambiarlo desde
# la tablet no toca el de la app. Repartos: n.º de huecos. `activo` es si el
# panel del mural está desplegado junto al plano.
MURAL_ESTANCIA_REPARTOS = ("1", "2", "4", "6", "8")


def get_room_mural(room_id: str) -> dict:
    sala = next((r for r in _read()["rooms"] if r.get("id") == room_id), None)
    guardado = (sala or {}).get("mural") or {}
    reparto = guardado.get("layout")
    if reparto not in MURAL_ESTANCIA_REPARTOS:
        reparto = "4"
    huecos = {
        str(k): v for k, v in (guardado.get("slots") or {}).items()
        if str(k).isdigit() and int(k) < int(reparto) and isinstance(v, str)
    }
    return {"layout": reparto, "slots": huecos, "activo": bool(guardado.get("activo"))}


def set_room_mural(room_id: str, layout: str, slots: dict[str, str],
                   activo: bool = False) -> None:
    if layout not in MURAL_ESTANCIA_REPARTOS:
        return

    def _apply(data):
        for sala in data["rooms"]:
            if sala.get("id") == room_id:
                sala["mural"] = {
                    "layout": layout,
                    "activo": bool(activo),
                    "slots": {k: v for k, v in slots.items()
                              if k.isdigit() and int(k) < int(layout)},
                }

    _mutate(_apply)


# ── Sirena de la tablet de una estancia ──────────────────────────────────────
# La tablet suena mientras haya una alerta de alarma sin confirmar. Qué suena y
# a qué volumen se guarda en la ficha de la estancia (`sirena`). El sonido lo
# genera el navegador (assets/nx.js), así que aquí solo van los nombres.
SIRENA_SONIDOS = ("sirena", "pitido", "alarma", "timbre")
SIRENA_VOLUMENES = ("25", "50", "75", "100")


def get_room_sirena(room_id: str) -> dict:
    sala = next((r for r in _read()["rooms"] if r.get("id") == room_id), None)
    g = (sala or {}).get("sirena") or {}
    return {
        "activa": bool(g.get("activa")),
        "sonido": g.get("sonido") if g.get("sonido") in SIRENA_SONIDOS else "sirena",
        "volumen": g.get("volumen") if g.get("volumen") in SIRENA_VOLUMENES else "75",
    }


def set_room_sirena(room_id: str, activa: bool, sonido: str, volumen: str) -> None:
    if sonido not in SIRENA_SONIDOS or volumen not in SIRENA_VOLUMENES:
        return

    def _apply(data):
        for sala in data["rooms"]:
            if sala.get("id") == room_id:
                sala["sirena"] = {"activa": bool(activa), "sonido": sonido,
                                  "volumen": volumen}

    _mutate(_apply)


# ── Personalización de una estancia (pestaña «Estancias») ────────────────────
# Todo vive en la ficha de la estancia: `pantalla` (qué muestra su tablet),
# `personalizado` (por miembro: oculto y etiqueta) y `orden` (refs en el orden
# en que se pintan). Ocultar un miembro NO lo saca de la estancia: sigue siendo
# suyo (y la tablet puede actuar sobre él), solo deja de pintarse.
ESTANCIA_PANTALLA = {"plano": True, "camaras": True, "sirena": True,
                     "hora": True, "baldosas": "normales"}
ESTANCIA_BALDOSAS = ("compactas", "normales", "grandes")


def get_room_pantalla(room_id: str) -> dict:
    sala = next((r for r in _read()["rooms"] if r.get("id") == room_id), None)
    guardado = (sala or {}).get("pantalla") or {}
    out = dict(ESTANCIA_PANTALLA)
    for clave, defecto in ESTANCIA_PANTALLA.items():
        valor = guardado.get(clave, defecto)
        if clave == "baldosas":
            out[clave] = valor if valor in ESTANCIA_BALDOSAS else defecto
        else:
            out[clave] = bool(valor)
    return out


def set_room_pantalla(room_id: str, clave: str, valor) -> None:
    if clave not in ESTANCIA_PANTALLA:
        return
    if clave == "baldosas":
        if valor not in ESTANCIA_BALDOSAS:
            return
    else:
        valor = bool(valor)

    def _apply(data):
        for sala in data["rooms"]:
            if sala.get("id") == room_id:
                sala.setdefault("pantalla", {})[clave] = valor

    _mutate(_apply)


def set_room_miembro(room_id: str, ref: str, oculto: bool | None = None,
                     etiqueta: str | None = None) -> None:
    """Oculta o renombra un miembro SOLO en la pantalla de esa estancia."""
    if ":" not in ref:
        return

    def _apply(data):
        for sala in data["rooms"]:
            if sala.get("id") != room_id:
                continue
            ficha = sala.setdefault("personalizado", {}).setdefault(ref, {})
            if oculto is not None:
                ficha["oculto"] = bool(oculto)
            if etiqueta is not None:
                limpia = " ".join(str(etiqueta).split())[:40]
                if limpia:
                    ficha["etiqueta"] = limpia
                else:
                    ficha.pop("etiqueta", None)
            if not ficha.get("oculto") and not ficha.get("etiqueta"):
                sala["personalizado"].pop(ref, None)

    _mutate(_apply)


def set_room_orden(room_id: str, refs: list[str]) -> None:
    limpias = [r for r in dict.fromkeys(refs) if isinstance(r, str) and ":" in r]

    def _apply(data):
        for sala in data["rooms"]:
            if sala.get("id") == room_id:
                sala["orden"] = limpias

    _mutate(_apply)


def probar_sirena(room_id: str) -> None:
    """Pide a la tablet de esa estancia que suene unos segundos. La tablet lo
    nota porque cambia este número (assets/nx.js, data-prueba); al cargar la
    página el valor que ya había no suena."""
    def _apply(data):
        for sala in data["rooms"]:
            if sala.get("id") == room_id:
                sala["sirena_prueba"] = int(time.time() * 1000)

    _mutate(_apply)
