"""
Registro de eventos de TODO el sistema. Funciones planas — no necesitan ser
reactivas; los States las envuelven donde hace falta actualizar la UI.

Este módulo es el VOCABULARIO del registro: qué familias hay, cómo se llama
cada acción en castellano y cómo se interpretan las entradas de las épocas
anteriores. Guardarlas y buscarlas es de logs_store.py (SQLite en modo WAL),
que es donde está explicado por qué ya no es un JSON.

Cada entrada lleva una `categoria` para poder filtrar por familia en la
pestaña Registros. El registro nació guardando solo alarma (armar/desarmar/
tampers) y por eso las entradas antiguas no la traen: se les asigna al
importarlas, deduciéndola de la acción (ver _categoria_heredada), así que el
histórico que ya había sigue apareciendo y encajado en su sitio.

Quién hizo cada cosa sale de la identidad push de la pestaña (el nombre del
dispositivo suscrito: "iPhone Ana", "Mac Bea"...). Lo resuelve
security/audit.py, que es por dónde deberían pasar los States: aquí no se
puede, porque para saberlo hace falta el State de la sesión.
"""
from . import logs_store

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
    "SENSOR_CAMARA_PUESTA": "Cámara asignada al elemento",
    "SENSOR_CAMARA_QUITADA": "Cámara quitada del elemento",
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
    "PRESENCIA_LUZ": "Luz movida por la simulación de presencia",
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
    "MANDO_IR_BOTON_FALLIDO": "Botón que no se pudo enviar",
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
    # Sesiones, roles e invitaciones (domains/auth). Van con tildes puestas a
    # mano como el resto: el nombre de la acción viaja sin ellas.
    "ACCESO_DENEGADO": "Acceso denegado",
    "DISPOSITIVO_IDENTIFICADO": "Dispositivo identificado",
    "DISPOSITIVO_RECONOCIDO": "Dispositivo reconocido por sus avisos",
    "DISPOSITIVO_NUEVO": "Dispositivo nuevo sin acceso",
    "DISPOSITIVO_ELIMINADO": "Dispositivo eliminado",
    "ROL_CAMBIADO": "Permisos cambiados",
    "INVITACION_CREADA": "Invitación creada",
    "INVITACION_USADA": "Invitación usada",
    "INVITACION_REVOCADA": "Invitación revocada",
    "ARMADO_CON_EXCLUSIONES": "Armado dejando algo fuera",
    "ARMADO_AL_CERRAR": "Se armará al cerrar",
    "ARMADO_EN_ESPERA": "Armado que estaba en espera",
    "ARMADO_CANCELADO": "Armado cancelado",
    "SALIDA_EN_CURSO": "Cuenta atrás para salir",
    "ENTRADA_EN_CURSO": "Tiempo para desarmar",
    "ALERTA_REPETIDA": "Alerta repetida sin confirmar",
    "ALERTA_CONFIRMADA": "Alerta confirmada",
    "ALERTA_SILENCIADA": "Alerta silenciada",
    "MODO_CAMBIADO": "Modo de la casa",
    "MODO_EDITADO": "Modo editado",
    "MODO_BORRADO": "Modo borrado",
    "INVENTARIO_EDITADO": "Ficha del inventario editada",
    "INVENTARIO_ANADIDO": "Elemento añadido al inventario",
    # Tablero de métricas: los paneles y qué equipos guardan histórico.
    "PANEL_METRICA_CREADO": "Panel de métricas creado",
    "PANEL_METRICA_EDITADO": "Panel de métricas editado",
    "PANEL_METRICA_ELIMINADO": "Panel de métricas eliminado",
    "EQUIPO_EN_METRICAS": "Equipo añadido al histórico",
    "EQUIPO_FUERA_DE_METRICAS": "Equipo quitado del histórico",
}


# Qué cuenta como "se ha abierto algo", para las gráficas de aperturas por hora
# y por día. Vive aquí porque es vocabulario: este módulo es el que sabe lo que
# significa cada acción. logs_store solo sabe contar lo que se le diga.
#
# Están las cuatro formas que ha tenido el mismo hecho a lo largo del tiempo:
# ELEMENTO_ABIERTO es la de ahora, PUERTA_ABIERTA la de cuando el contacto de la
# entrada tenía acción propia, _ARMADA la que salta con el sistema armado y
# _MANDO la apertura mandada desde el panel. Contar solo la de ahora daría una
# gráfica que empieza el día que se renombró la acción.
#
# NO están los cierres ni los tampers: una gráfica de "aperturas" que incluyera
# el cierre contaría cada paso por la puerta dos veces.
ACCIONES_APERTURA = (
    "ELEMENTO_ABIERTO",
    "PUERTA_ABIERTA",
    "PUERTA_ABIERTA_ARMADA",
    "PUERTA_ABIERTA_MANDO",
)


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


def normalizar_heredada(entrada: dict) -> dict:
    """Una entrada del logs.json de antes, con las claves de ahora.

    El fichero mezclaba entradas de tres épocas (sin `grupo`, sin `categoria`, y
    las de ahora), y hasta ahora esto se aplicaba en CADA lectura para que la
    vista no pidiera una clave que en unas filas está y en otras no. Ahora se
    aplica una sola vez, al importar el fichero a la base de datos
    (logs_store._importar): lo que se guarda ya está interpretado, y lo que sale
    de una consulta tiene siempre las mismas columnas por definición."""
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


def leer_logs(limite: int | None = None) -> list[dict]:
    """Del más antiguo al más reciente, como devolvía el fichero.

    `limite` acota a los N más RECIENTES (devueltos igualmente de antiguo a
    reciente). Pedirlo sin límite trae el histórico entero, que ya no tiene tope
    de 1.500 entradas: quien pinta una lista debe acotar."""
    return logs_store.leer(limite)


def ultimo_log_puerta() -> str:
    return logs_store.ultima_accion(
        ("PUERTA_ABIERTA", "PUERTA_ABIERTA_ARMADA", "PUERTA_CERRADA"))


def registrar(categoria: str, accion: str, usuario: str = "sistema",
              detalle: str = "", grupo: str = "", entidad: str = "") -> int:
    """Apunta un evento. Devuelve su id, o 0 si no se guardó (repetido, o fallo).

    Casi nadie mira el id: hace falta para poder colgarle algo al evento
    después, como el fotograma de la cámara (ver logs_store.adjuntar_foto).

    detalle: el SUJETO primero y los añadidos detrás, separados por " · "
    ("Habitación · Raspberry pin 5"). El listado parte por ahí para enseñar el
    nombre en grande y lo demás en pequeño, así que respetar el orden es lo que
    hace que se lea de un vistazo.

    grupo: solo lo usan los eventos de armado por grupo (ARMADO_GRUPO/
    DESARMADO_GRUPO) — "TOTAL" si es el grupo principal, o el nombre del
    grupo si es parcial. Se guarda aparte de `detalle` porque `detalle` para
    estos eventos lleva el resumen "Armado con abiertos: ..." (mismo formato
    que el armado clásico), y hacen falta las dos cosas a la vez en el log.

    Los fallos se tragan y se imprimen, como siempre: apuntar un evento es
    SIEMPRE lo secundario de la acción que lo provoca. Que no se pueda escribir
    el registro no puede impedir que se abra una puerta ni que se arme la
    alarma."""
    if categoria not in IDS_CATEGORIAS:
        categoria = SISTEMA
    try:
        return logs_store.registrar(categoria, accion, usuario, detalle, grupo,
                                    entidad)
    except Exception as e:
        print(f"❌ Error escribiendo log: {e}")
        return 0


def registrar_log(accion: str, usuario: str, detalle: str = "", grupo: str = "") -> int:
    """Forma anterior, sin categoría — se deduce. La siguen usando los avisos
    que emite el propio sistema (sensores por MQTT), que son todos de alarma."""
    return registrar(_categoria_heredada(accion), accion, usuario, detalle, grupo)
