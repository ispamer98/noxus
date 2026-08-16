"""
Registro de eventos de TODO el sistema (logs.json). Funciones planas — no
necesitan ser reactivas; los States las envuelven donde hace falta actualizar
la UI.

Cada entrada lleva una `categoria` para poder filtrar por familia en la
pestaña Registros. Nació guardando solo alarma (armar/desarmar/tampers) y por
eso las entradas antiguas no la traen: se les asigna al leer, deduciéndola de
la acción (ver _categoria_heredada), así que el histórico que ya había sigue
apareciendo y encajado en su sitio sin tener que migrar el fichero.

Quién hizo cada cosa sale de la identidad push de la pestaña (el nombre del
dispositivo suscrito: "iPhone Ruben", "Mac Gaby"...). Lo resuelve
security/audit.py, que es por dónde deberían pasar los States: aquí no se
puede, porque para saberlo hace falta el State de la sesión.
"""
import fcntl
import json
import os
import time

ARCHIVO = "logs.json"
MAX_ENTRIES = 1500

# (id, etiqueta, icono) — este orden es el de los filtros de la pestaña
# Registros, así que va de lo más "de seguridad" a lo más administrativo.
CATEGORIAS = (
    ("alarma", "Alarma", "siren"),
    ("grupos", "Grupos", "layers"),
    ("puertas", "Puertas", "door-open"),
    ("luces", "Luces", "lightbulb"),
    ("sensores", "Sensores", "radar"),
    ("cctv", "CCTV", "video"),
    ("accesos", "Accesos", "key-round"),
    ("equipos", "Equipos", "server"),
    ("sistema", "Sistema", "settings"),
    ("automatizaciones", "Automatizaciones", "workflow"),
)
IDS_CATEGORIAS = tuple(c[0] for c in CATEGORIAS)

# Constantes para los sitios que registran, para no repartir literales sueltos
# por todos los States (una errata en uno dejaría eventos en una categoría
# fantasma que ningún filtro enseña).
(ALARMA, GRUPOS, PUERTAS, LUCES, SENSORES, CCTV, ACCESOS, EQUIPOS, SISTEMA,
 AUTOMATIZACIONES) = IDS_CATEGORIAS

# Acciones de antes de que existieran las categorías. El orden importa:
# ARMADO_GRUPO empieza por "ARMADO", así que los de grupo van primero.
# Ojo con PUERTA_ABIERTA/PUERTA_CERRADA: son de cuando el contacto magnético de
# la entrada tenía acción propia, y describen que la puerta ESTÁ abierta, no que
# se haya mandado abrir. Por eso caen en Alarma como todo lo demás y no en
# Puertas, que es solo el reflejo del control de accesos.
_HEREDADAS = (
    ("ARMADO_GRUPO", GRUPOS),
    ("DESARMADO_GRUPO", GRUPOS),
    ("TAMPER", ALARMA),
)


# Texto legible de cada acción. Solo hacen falta las que no quedan claras
# solas: las que no estén aquí se muestran con el nombre en minúsculas y sin
# guiones bajos (ver etiqueta_accion), que para "LUZ_ENCENDIDA" o
# "GRUPO_CREADO" ya se lee perfectamente. Así añadir un evento nuevo no obliga
# a acordarse de venir aquí.
_ETIQUETAS = {
    "ARMADO": "Sistema armado",
    "DESARMADO": "Sistema desarmado",
    "ARMADO_GRUPO": "Grupo armado",
    "DESARMADO_GRUPO": "Grupo desarmado",
    # Estas son de cuando el contacto de la entrada tenía acción propia. Van
    # con la misma palabra suelta que las de ahora: el nombre del elemento ya
    # va delante, y "Puerta · Puerta abierta" repetía el sustantivo.
    "PUERTA_ABIERTA": "Abierto",
    "PUERTA_CERRADA": "Cerrado",
    "PUERTA_ABIERTA_ARMADA": "¡Abierto con el sistema armado!",
    "PUERTA_ABIERTA_MANDO": "Puerta abierta desde el panel",
    "PUERTA_PULSO_CORTADO": "Pulso de puerta cortado",
    "COMANDO_SSH": "Comando SSH ejecutado",
    "ESCRITORIO_REMOTO_ABIERTO": "Escritorio remoto abierto",
    "ESCRITORIO_REMOTO_DESCARGADO": "Acceso remoto descargado",
    "TEMPERATURA_CONSULTADA": "Temperatura consultada",
    "EQUIPO_ENCENDIDO_WOL": "Encendido por red",
    "SENSOR_AISLADO": "Sensor aislado de la alarma",
    "SENSOR_REINTEGRADO": "Sensor devuelto a la alarma",
    "GRUPO_PRINCIPAL_CAMBIADO": "Grupo principal cambiado",
    "PLANO_ELEMENTO_COLOCADO": "Elemento colocado en el plano",
    "PLANO_ELEMENTO_QUITADO": "Elemento quitado del plano",
    # Junto al nombre y con el icono de puerta abierta/cerrada delante, una
    # sola palabra basta: "Puerta · Abierto" se lee mejor que "Puerta ·
    # Elemento abierto".
    "ELEMENTO_ABIERTO": "Abierto",
    "ELEMENTO_CERRADO": "Cerrado",
    # Las tildes hay que ponerlas a mano: el nombre de la acción va sin ellas.
    "CAMARA_CREADA": "Cámara creada",
    "CAMARA_EDITADA": "Cámara editada",
    "CAMARA_ELIMINADA": "Cámara eliminada",
    "CAMARA_SIRENA": "Sirena de la cámara",
    "CAMARA_PRIVACIDAD_ON": "Privacidad activada",
    "CAMARA_PRIVACIDAD_OFF": "Privacidad desactivada",
    "LUZ_CAMBIADA_DE_ESTANCIA": "Luz cambiada de estancia",
    "SENSOR_AÑADIDO_A_GRUPO": "Sensor añadido al grupo",
    "SENSOR_QUITADO_DE_GRUPO": "Sensor quitado del grupo",
    "PUERTA_AÑADIDA_A_NIVEL": "Puerta añadida al nivel",
    "PUERTA_QUITADA_DE_NIVEL": "Puerta quitada del nivel",
    "WIDGET_AÑADIDO": "Widget añadido al resumen",
    "WIDGET_QUITADO": "Widget quitado del resumen",
    "MANDO_IR_CREADO": "Mando IR creado",
    "MANDO_IR_EDITADO": "Mando IR editado",
    "MANDO_IR_ELIMINADO": "Mando IR eliminado",
    "MANDO_IR_BOTON_APRENDIDO": "Botón aprendido",
    "MANDO_IR_BOTON_ELIMINADO": "Botón eliminado",
    "MANDO_IR_BOTON_ENVIADO": "Botón enviado",
    # Automatizaciones. Con tilde a mano, como las de arriba.
    "AUTOMATIZACION_EJECUTADA": "Automatización ejecutada",
    "AUTOMATIZACION_FALLIDA": "Automatización fallida",
    "AUTOMATIZACION_PARCIAL": "Automatización ejecutada con fallos",
    "AUTOMATIZACION_DESACTIVADA": "Automatización desactivada sola",
    "AUTOMATIZACION_CREADA": "Automatización creada",
    "AUTOMATIZACION_EDITADA": "Automatización editada",
    "AUTOMATIZACION_ELIMINADA": "Automatización eliminada",
    "AUTOMATIZACION_ACTIVADA_MANUAL": "Automatización activada",
    "AUTOMATIZACION_DESACTIVADA_MANUAL": "Automatización desactivada",
    "NOTA": "Nota de una automatización",
}


def etiqueta_accion(accion: str) -> str:
    etiqueta = _ETIQUETAS.get(accion)
    if etiqueta:
        return etiqueta
    return accion.replace("_", " ").capitalize()


def _categoria_heredada(accion: str) -> str:
    for prefijo, categoria in _HEREDADAS:
        if accion.startswith(prefijo):
            return categoria
    return ALARMA


# Palabras de estado que las entradas viejas guardaban en el campo de detalle.
# Entonces el nombre del elemento iba en el campo de usuario, así que el
# listado acababa leyéndose "ABIERTA · Puerta abierta": el estado dos veces y
# el nombre en ninguna. Ver _reubicar_nombre.
_ESTADOS_VIEJOS = {"ABIERTA", "ABIERTO", "CERRADA", "CERRADO"}


def _reubicar_nombre(entrada: dict) -> tuple[str, str]:
    """(usuario, detalle) de una entrada de apertura/cierre.

    Las de ahora ya vienen bien —el nombre en el detalle y "sistema" como
    autor—, así que solo se toca lo antiguo: si el detalle es una palabra de
    estado suelta, el nombre está en el campo de usuario y se cambian de sitio.
    Y el autor pasa a "sistema", que es la verdad: un contacto que se abre no lo
    ha pulsado nadie.

    Se hace al LEER y no migrando el fichero para que el histórico no dependa
    de que una migración se ejecutara alguna vez."""
    usuario = entrada.get("usuario") or "sistema"
    detalle = entrada.get("detalle") or ""
    if detalle.strip().upper() in _ESTADOS_VIEJOS:
        return "sistema", usuario
    return usuario, detalle


def _normalizar(entrada: dict) -> dict:
    """Toda entrada sale de aquí con las mismas claves. Hace falta porque el
    fichero mezcla entradas de tres épocas (sin `grupo`, sin `categoria`, y las
    de ahora): sin esto, la vista pediría una clave que en unas filas está y en
    otras no, y en el navegador eso se pinta como "undefined"."""
    accion = entrada.get("accion", "")
    usuario, detalle = _reubicar_nombre(entrada)
    return {
        "timestamp": entrada.get("timestamp", ""),
        "categoria": entrada.get("categoria") or _categoria_heredada(accion),
        "accion": accion,
        "usuario": usuario,
        "detalle": detalle,
        "grupo": entrada.get("grupo") or "",
        # Id del elemento al que se refiere el evento, cuando lo hay. No es
        # para buscar: es para que el listado pueda pintar SU icono y SU color
        # (el de la luz en el plano, el del equipo que se ha caído) en vez de
        # uno genérico por familia. Se resuelve al pintar, no se copia aquí,
        # para que renombrar o recolorear algo se refleje también en su
        # histórico.
        "entidad": entrada.get("entidad") or "",
    }


def leer_logs() -> list[dict]:
    if not os.path.exists(ARCHIVO):
        return []
    try:
        with open(ARCHIVO, "r") as f:
            content = f.read().strip()
        return [_normalizar(e) for e in (json.loads(content) if content else [])]
    except Exception:
        return []


def ultimo_log_puerta() -> str:
    for log in reversed(leer_logs()):
        accion = log.get("accion", "")
        if accion in ("PUERTA_ABIERTA", "PUERTA_ABIERTA_ARMADA", "PUERTA_CERRADA"):
            return accion
    return ""


def registrar(categoria: str, accion: str, usuario: str = "sistema",
              detalle: str = "", grupo: str = "", entidad: str = "") -> None:
    """Apunta un evento.

    detalle: el SUJETO primero y los añadidos detrás, separados por " · "
    ("Habitación · Raspberry pin 5"). El listado parte por ahí para enseñar el
    nombre en grande y lo demás en pequeño, así que respetar el orden es lo que
    hace que se lea de un vistazo.

    grupo: solo lo usan los eventos de armado por grupo (ARMADO_GRUPO/
    DESARMADO_GRUPO) — "TOTAL" si es el grupo principal, o el nombre del
    grupo si es parcial. Se guarda aparte de `detalle` porque `detalle` para
    estos eventos lleva el resumen "Armado con abiertos: ..." (mismo formato
    que el armado clásico), y hacen falta las dos cosas a la vez en el log."""
    if categoria not in IDS_CATEGORIAS:
        categoria = SISTEMA
    try:
        with open(ARCHIVO, "a+" if os.path.exists(ARCHIVO) else "w+") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            f.seek(0)
            content = f.read().strip()
            logs = []
            if content:
                try:
                    logs = json.loads(content)
                except Exception:
                    logs = []
            # Repetido exacto e inmediato = ruido (un sensor que rebota, un
            # botón pulsado dos veces). No se filtra nada más antiguo: dos
            # eventos iguales separados en el tiempo son dos hechos distintos y
            # un registro que se los come deja de servir para lo que sirve.
            if logs:
                ultimo = logs[-1]
                if (ultimo.get("accion") == accion and ultimo.get("detalle") == detalle
                        and ultimo.get("grupo") == grupo):
                    return
            logs.append({
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "categoria": categoria,
                "accion": accion,
                "usuario": usuario or "sistema",
                "detalle": detalle,
                "grupo": grupo,
                "entidad": entidad,
            })
            if len(logs) > MAX_ENTRIES:
                logs = logs[-MAX_ENTRIES:]
            f.seek(0)
            f.truncate()
            json.dump(logs, f, indent=2, ensure_ascii=False)
            f.flush()
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except Exception as e:
        print(f"❌ Error escribiendo log: {e}")


def registrar_log(accion: str, usuario: str, detalle: str = "", grupo: str = "") -> None:
    """Forma anterior, sin categoría — se deduce. La siguen usando los avisos
    que emite el propio sistema (sensores por MQTT), que son todos de alarma."""
    registrar(_categoria_heredada(accion), accion, usuario, detalle, grupo)
