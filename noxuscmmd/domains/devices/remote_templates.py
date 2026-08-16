"""
Plantillas de mando: el juego COMPLETO de botones de un mando físico real, ya
colocados imitando su disposición, para no tener que crearlos de uno en uno.

Cada botón nace SIN señal (`code` vacío): la plantilla pone el nombre, el
icono/rótulo y el sitio; la señal se aprende después botón a botón desde el
propio mando virtual (ver NodesState.learn_into_button). Así el mando se ve
completo desde el primer momento y se va "rellenando" a medida que se le
enseñan las señales.

Cada plantilla trae TRES cosas:

1. El cuerpo (body_w x body_h). No es un detalle estético: el mando de la TV
   es alargado y estrecho y el del ventilador apaisado — con un cuerpo único
   uno de los dos sale siempre deformado. Las coordenadas de los botones son
   % sobre ESE cuerpo.
2. Los grupos: las placas y hundidos que el mando real tiene serigrafiados
   debajo de las teclas — el balancín del volumen, el aro de la rueda, la
   tira de colores, la plancha de las apps, el pad circular de la luz. Son
   decorativos (no se pulsan) pero son lo que hace que el mando virtual se
   reconozca de un vistazo como el de verdad, en vez de como una nube de
   círculos sueltos.
3. Los botones.

Campos de cada botón:
  label     nombre que se ve al pasar por encima
  icon      icono del botón
  text      rótulo impreso EN el botón, cuando un icono no sirve: los números
            (con icono serían diez círculos idénticos), las apps (con su
            inicial, porque sus logos no se pueden reproducir) y los ON/OFF.
  color     tinte del botón — las cuatro teclas de color de la TV y los
            colores de marca de las apps. Vacío = aspecto normal de tecla.
  kind      por dónde se manda: "ir" (Broadlink, infrarrojos o RF) o "webos"
            (API de red de la TV LG — ver webos_bus.py), para los botones que
            el Magic Remote NO manda por infrarrojos (Home, micro, apps) y que
            por tanto el Broadlink no puede aprender. En esos, `code` es el
            comando webOS, no una señal capturada.
  top/left  posición en % sobre el cuerpo de SU plantilla.

Las teclas miden 44px (_TECLA), así que dos botones necesitan al menos esos
44px de separación real en cada eje. Sobre el cuerpo de la TV (300x820) eso
son 14.7% en horizontal y 5.4% en vertical; sobre el del ventilador (520x300),
8.5% y 14.7%. Apretarlos más los solapa.
"""

# Tamaño del cuerpo de cada mando, en px. La UI lo lee de aquí (no al revés)
# para que cambiar la forma de un mando no obligue a tocar la vista.
CUERPO_TV = (300, 820)
CUERPO_VENTILADOR = (280, 580)

_TECLA = 44


# Tamaño del icono dentro de la tecla. Sirve para los pares "más / menos" que
# el mando distingue SOLO por el tamaño del dibujo (los dos soles de la luz,
# las dos aspas de la velocidad): con los dos iconos iguales no hay forma de
# saber cuál sube y cuál baja.
ICO_GRANDE = "62%"
ICO_NORMAL = "46%"
ICO_PEQUENO = "32%"


def _b(label, icon, top, left, *, text="", color="", kind="ir", code="", ico=ICO_NORMAL):
    return {
        "label": label, "icon": icon, "text": text, "color": color,
        "kind": kind, "code": code, "icon_size": ico,
        "pos_top": top, "pos_left": left,
    }


def _g(miembros, radius="14px", tono="placa"):
    """Una placa de grupo, definida por QUÉ TECLAS agrupa (por su nombre), no
    por unas coordenadas propias.

    Es a propósito: su rectángulo se calcula al pintar, a partir de dónde
    estén sus teclas en ese momento (ver _remote_para_ui en
    domains/nodes/state.py). Así arrastrar una tecla estira la placa con ella
    y borrarlas todas la hace desaparecer, en vez de quedarse un marco suelto
    en medio del mando rodeando un hueco vacío."""
    return {"members": list(miembros), "radius": radius, "tono": tono}


def _fila(items, top, columnas):
    """Una fila de botones repartidos por las columnas dadas."""
    return [_b(**{**item, "top": top, "left": columnas[i]}) for i, item in enumerate(items)]


def _n(digito):
    """Tecla numérica: el número se imprime, no se dibuja."""
    return {"label": digito, "icon": "circle", "text": digito}


# ── LG Magic Remote ──────────────────────────────────────────────────────────
# De arriba abajo, como el mando real: encendido y fuente; teclado numérico de
# 3 columnas con LIST/0/⋯ debajo; anterior-guía-siguiente; los dos balancines
# (volumen a la izquierda, canal a la derecha) con silencio y subtítulos entre
# ellos; la rueda con OK; atrás-Home-ajustes; la tira de las cuatro teclas de
# color; la plancha de accesos a apps; y abajo los dos asistentes con el
# micrófono en medio.
_C3 = ("20%", "50%", "80%")          # teclado y filas de tres
_C4 = ("14%", "38%", "62%", "86%")   # colores y apps
_LADOS = ("16%", "84%")              # balancines, pegados a los bordes

_LG_GRUPOS = [
    # Balancines de volumen y canal: en el mando son dos piezas alargadas de
    # una sola tecla basculante, no dos botones sueltos.
    _g(["Volumen +", "Volumen −"], radius="999px"),
    _g(["Canal +", "Canal −"], radius="999px"),
    # Aro hundido de la rueda de navegación.
    _g(["Arriba", "Abajo", "Izquierda", "Derecha", "OK"], radius="50%", tono="hundido"),
    # Tira de las teclas de color y plancha de los accesos a apps.
    _g(["Rojo", "Verde", "Amarillo", "Azul"], radius="999px"),
    _g(["Netflix", "Prime Video", "Disney+", "Rakuten TV"], radius="12px"),
]

_LG_MAGIC = [
    _b("Encender", "power", "3.5%", "22%"),
    _b("Entrada", "monitor", "3.5%", "78%"),
    *_fila([_n("1"), _n("2"), _n("3")], "10%", _C3),
    *_fila([_n("4"), _n("5"), _n("6")], "16.5%", _C3),
    *_fila([_n("7"), _n("8"), _n("9")], "23%", _C3),
    *_fila([
        {"label": "Lista", "icon": "list"},
        _n("0"),
        {"label": "Más (...)", "icon": "ellipsis"},
    ], "29.5%", _C3),
    *_fila([
        {"label": "Anterior", "icon": "chevron-left"},
        {"label": "Guía", "icon": "calendar"},
        {"label": "Siguiente", "icon": "chevron-right"},
    ], "36.5%", _C3),
    _b("Volumen +", "volume-2", "43.5%", _LADOS[0]),
    _b("Silencio", "volume-x", "43.5%", "50%"),
    _b("Canal +", "chevron-up", "43.5%", _LADOS[1]),
    _b("Volumen −", "volume-1", "50%", _LADOS[0]),
    _b("Subtítulos", "captions", "50%", "50%"),
    _b("Canal −", "chevron-down", "50%", _LADOS[1]),
    _b("Arriba", "chevron-up", "57%", "50%"),
    _b("Izquierda", "chevron-left", "63.5%", "24%"),
    _b("OK", "check", "63.5%", "50%"),
    _b("Derecha", "chevron-right", "63.5%", "76%"),
    _b("Abajo", "chevron-down", "70%", "50%"),
    *_fila([
        {"label": "Atrás", "icon": "corner-up-left"},
        {"label": "Home", "icon": "house", "kind": "webos", "code": "HOME"},
        {"label": "Ajustes", "icon": "settings"},
    ], "77%", _C3),
    *_fila([
        {"label": "Rojo", "icon": "circle", "color": "rojo"},
        {"label": "Verde", "icon": "circle", "color": "verde"},
        {"label": "Amarillo", "icon": "circle", "color": "amarillo"},
        {"label": "Azul", "icon": "circle", "color": "azul"},
    ], "83.5%", _C4),
    *_fila([
        {"label": "Netflix", "icon": "circle", "text": "N", "color": "netflix",
         "kind": "webos", "code": "netflix"},
        {"label": "Prime Video", "icon": "circle", "text": "P", "color": "prime",
         "kind": "webos", "code": "amazon"},
        {"label": "Disney+", "icon": "circle", "text": "D+", "color": "disney",
         "kind": "webos", "code": "disneyplus"},
        {"label": "Rakuten TV", "icon": "circle", "text": "R", "color": "rakuten",
         "kind": "webos", "code": "rakuten"},
    ], "90%", _C4),
    _b("Alexa", "circle", "96.5%", "25%", text="a", color="alexa", kind="webos"),
    _b("Micrófono", "mic", "96.5%", "50%", kind="webos"),
    _b("Google", "bot", "96.5%", "75%", color="google", kind="webos"),
]

# ── Mando de ventilador de techo con luz ─────────────────────────────────────
# OJO con la orientación: en la foto el mando está TUMBADO de lado (igual que
# el LG, que se ve con el logo girado). De pie es un mando vertical de tres
# columnas, no uno apaisado. Leerlo tal y como salía en la foto fue lo que
# hizo que la primera versión de esta plantilla no se pareciera a nada.
#
# De arriba abajo:
#   · ON / OFF de la LUZ, uno a cada lado.
#   · Velocidad, viento natural y temporizador.
#   · Pad circular hundido con todo lo de la luz: atenuar arriba, iluminar
#     abajo, fría y cálida a los lados, modo noche en el centro.
#   · Temporizador corto, favorito y modo brisa.
#   · La tira de tres teclas del ventilador (marcha, invierno/verano y giro),
#     que en el mando van juntas dentro de un mismo rebaje.
#
# Este mando es de infrarrojos, así que se aprende con "Aprender por IR" como
# el de la TV. (Ojo si algún día se cambia por otro: muchos mandos de
# ventilador de techo son de radiofrecuencia y esos necesitan "Aprender por
# RF" — se distinguen porque no tienen lucecita infrarroja al pulsarlos.)
_VENT_C3 = ("22%", "50%", "78%")

_VENTILADOR_GRUPOS = [
    # Pad circular de la luz, hundido en la carcasa
    _g(["Subir intensidad de la luz", "Luz fría", "Modo noche", "Luz cálida",
        "Bajar intensidad de la luz"], radius="50%", tono="hundido"),
    # Tira de las tres teclas del ventilador
    _g(["Bajar velocidad", "Giro invierno / verano", "Subir velocidad"], radius="999px"),
]

_VENTILADOR_TECHO = [
    # ON / OFF — son de la LUZ
    _b("Luz ON", "power", "9%", _VENT_C3[0], text="ON"),
    _b("Luz OFF", "power-off", "9%", _VENT_C3[2], text="OFF"),
    # Velocidad, viento natural y temporizador
    _b("Velocidad ventilador", "fan", "20%", _VENT_C3[0]),
    _b("Viento natural", "wind", "20%", _VENT_C3[1]),
    _b("Temporizador 1h/2h/4h", "timer", "20%", _VENT_C3[2]),
    # Pad circular — todo lo de la luz. Los dos soles son la intensidad, y se
    # distinguen por el tamaño del icono: arriba el grande (subir), abajo el
    # pequeño (bajar), igual que en el mando.
    _b("Subir intensidad de la luz", "sun", "33%", _VENT_C3[1], ico=ICO_GRANDE),
    _b("Luz fría", "snowflake", "44%", _VENT_C3[0]),
    _b("Modo noche", "moon-star", "44%", _VENT_C3[1]),
    _b("Luz cálida", "flame", "44%", _VENT_C3[2]),
    _b("Bajar intensidad de la luz", "sun", "55%", _VENT_C3[1], ico=ICO_PEQUENO),
    # Temporizador corto, favorito y brisa
    _b("Temporizador 60s", "timer", "70%", _VENT_C3[0]),
    _b("Favorito", "heart", "70%", _VENT_C3[1]),
    _b("Modo brisa", "wind", "70%", _VENT_C3[2]),
    # Tira del ventilador: las dos aspas son la velocidad (pequeña a la
    # izquierda = bajar, grande a la derecha = subir) y en medio el cambio de
    # giro invierno/verano.
    _b("Bajar velocidad", "fan", "84%", _VENT_C3[0], ico=ICO_PEQUENO),
    _b("Giro invierno / verano", "snowflake", "84%", _VENT_C3[1]),
    _b("Subir velocidad", "fan", "84%", _VENT_C3[2], ico=ICO_GRANDE),
]

# id -> (etiqueta del desplegable, icono del mando, cuerpo, grupos, botones)
PLANTILLAS = {
    "vacio": ("Vacío — lo monto yo botón a botón", "tv", CUERPO_TV, [], []),
    "lg_magic": (
        f"LG Magic Remote — {len(_LG_MAGIC)} botones", "tv", CUERPO_TV,
        _LG_GRUPOS, _LG_MAGIC,
    ),
    "ventilador_techo": (
        f"Ventilador de techo con luz — {len(_VENTILADOR_TECHO)} botones",
        "fan", CUERPO_VENTILADOR, _VENTILADOR_GRUPOS, _VENTILADOR_TECHO,
    ),
}

# Orden en que se ofrecen (los dicts conservan orden de inserción, pero
# dejarlo explícito evita que reordenar el dict cambie la UI sin querer).
IDS_PLANTILLAS = ("vacio", "lg_magic", "ventilador_techo")


def opciones() -> list[tuple[str, str]]:
    """[(id, etiqueta)] para el desplegable de "Nuevo mando"."""
    return [(pid, PLANTILLAS[pid][0]) for pid in IDS_PLANTILLAS]


def icono_sugerido(plantilla_id: str) -> str:
    return PLANTILLAS.get(plantilla_id, PLANTILLAS["vacio"])[1]


def cuerpo(plantilla_id: str) -> tuple[int, int]:
    """(ancho, alto) en px del cuerpo del mando de esa plantilla."""
    return PLANTILLAS.get(plantilla_id, PLANTILLAS["vacio"])[2]


def grupos(plantilla_id: str) -> list[dict]:
    """Las placas decorativas del mando."""
    return [dict(g) for g in PLANTILLAS.get(plantilla_id, PLANTILLAS["vacio"])[3]]


def botones(plantilla_id: str) -> list[dict]:
    """Los botones de una plantilla, ya con la forma que guarda el store."""
    return [dict(b) for b in PLANTILLAS.get(plantilla_id, PLANTILLAS["vacio"])[4]]
