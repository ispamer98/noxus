"""
El catálogo de comandos de la casa: la lista de todo lo que se puede hacer, ya
concreto y con nombre.

Lo usan TRES sitios y por eso vive aquí y no dentro de ninguno de ellos:

  - La paleta de comandos del panel (Ctrl+K).
  - El endpoint de voz para Siri y Alexa (devices/voz.py).
  - Y cualquier cosa que venga después que necesite «haz esto».

Ninguno de los tres tiene ejecutor propio: todos acaban en
`automations.actions.dispatch`, el mismo despachador que usan las
automatizaciones y los modos de casa. Un segundo camino que hiciera lo mismo por
su cuenta es como acaban divergiendo dos comportamientos que deberían ser uno.

Los comandos son YA CONCRETOS («Encender Salón», «Apagar Salón»), no acciones con
parámetros a rellenar: es lo que permite que valgan igual para una lista que se
filtra escribiendo y para una frase dictada a un altavoz.
"""
import re
import unicodedata

from ..auth import permisos
from ..nodes import store as nodes_store
from ..modes import store as modes_store
from ..automations import store as automations_store
from ..security import groups_store

# Cuántos se pintan. Con la lista entera de una casa grande, el diálogo se
# convierte en una pantalla de scroll y deja de servir para ir rápido.
TOPE = 40


def plano(texto: str) -> str:
    """Sin tildes y en minúsculas, para que «salon» encuentre «Salón». Escribir
    con tildes en un buscador es justo lo que nadie hace."""
    return "".join(
        c for c in unicodedata.normalize("NFD", (texto or "").lower())
        if unicodedata.category(c) != "Mn"
    )


# Las vistas a las que se puede ir, con el nombre con el que se buscan. Se
# escriben aquí y no se sacan de VIEW_TITLES para no atar el dominio a la
# interfaz: es al revés de como debe ir la dependencia.
_VISTAS = (
    ("overview", "Resumen", "layout-dashboard"),
    ("alarm", "Alarma", "siren"),
    ("groups", "Grupos de armado", "layers"),
    ("floor_plan", "Plano", "map"),
    ("video_wall", "Mural de vídeo", "grid-2x2"),
    ("cctv", "CCTV", "video"),
    ("access", "Control de accesos", "door-open"),
    ("lights", "Luces", "lightbulb"),
    ("ir_remotes", "Mandos", "gamepad-2"),
    ("automations", "Automatizaciones", "workflow"),
    ("equipment", "Equipos", "server"),
    ("logs", "Registros", "clipboard-list"),
    ("metricas", "Métricas", "chart-line"),
    ("settings_hub", "Ajustes", "settings"),
)


# Acciones que Amazon admite como control doméstico sin abrir una vía lateral
# hacia accesos o seguridad. Esta política se usa tanto al construir el
# catálogo oficial como al guardar una secuencia creada desde el editor Alexa:
# una sola lista, una sola decisión.
_TIPOS_ALEXA_SEGUROS = {
    "light.set", "ir_button.press", "host_button.run", "host.action",
    "host.wol", "notify", "log", "wait",
}


def paso_permitido_alexa(
        paso: dict, *, reglas: list[dict] | None = None,
        modos: list[dict] | None = None,
        visitadas: set[str] | None = None) -> bool:
    """Si un paso puede publicarse en la Skill oficial de Alexa.

    Las referencias a reglas y modos se revisan recursivamente. Así no basta
    con esconder una apertura de puerta dentro de «Rutina noche» para saltarse
    la exclusión de accesos y alarma. ``rule.enable`` tampoco se permite: una
    orden de voz que habilitase una regla insegura sería el mismo bypass, solo
    que diferido hasta su siguiente disparo.
    """
    tipo = str(paso.get("type") or "")
    visitadas = set() if visitadas is None else set(visitadas)

    if reglas is None:
        try:
            reglas = automations_store.read_all()
        except automations_store.ArchivoCorrupto:
            reglas = []
    if modos is None:
        modos = modes_store.leer().get("modos", [])

    reglas_por_id = {regla["id"]: regla for regla in reglas}
    modos_por_id = {modo["id"]: modo for modo in modos}

    if tipo == "rule.run":
        regla_id = str(paso.get("target", "")).removeprefix("rule:")
        if not regla_id or regla_id in visitadas:
            return False
        regla = reglas_por_id.get(regla_id)
        if regla is None:
            return False
        visitadas.add(regla_id)
        return all(
            paso_permitido_alexa(
                accion, reglas=reglas, modos=modos, visitadas=visitadas)
            for accion in regla.get("actions", [])
        )

    if tipo == "modo":
        modo = modos_por_id.get(str(paso.get("target", "")))
        return bool(modo is not None and all(
            paso_permitido_alexa(
                {"type": "rule.run", "target": f"rule:{regla_id}"},
                reglas=reglas, modos=modos, visitadas=visitadas)
            for regla_id in modo.get("reglas", [])
        ))

    return tipo in _TIPOS_ALEXA_SEGUROS


def comandos() -> list[dict]:
    """Todo lo que se puede hacer, ya concreto.

    Cada uno: id, etiqueta, familia, icono, y qué ejecutar — un `tipo` de paso de
    `actions` con su objetivo y sus parámetros ya puestos, o "vista"/"modo" para
    los dos que no son acciones del despachador."""
    datos = nodes_store.read_all()
    salida: list[dict] = []

    def add(id_, etiqueta, familia, icono, paso):
        salida.append({"id": id_, "etiqueta": etiqueta, "familia": familia,
                       "icono": icono, "paso": paso})

    for vista, nombre, icono in _VISTAS:
        add(f"vista:{vista}", f"Ir a {nombre}", "Ir a", icono,
            {"type": "vista", "target": vista})

    modos = modes_store.leer()["modos"]
    for modo in sorted(modos, key=lambda m: m.get("orden", 0)):
        add(f"modo:{modo['id']}", f"Poner la casa en «{modo['nombre']}»", "Modos",
            modo.get("icono") or "house", {"type": "modo", "target": modo["id"]})

    for luz in datos["lights"]:
        for valor, verbo in (("on", "Encender"), ("off", "Apagar")):
            add(f"luz:{luz['id']}:{valor}", f"{verbo} {luz['name']}", "Luces",
                "lightbulb",
                {"type": "light.set", "target": f"light:{luz['id']}",
                 "params": {"on": valor}})

    for puerta in datos["doors"]:
        add(f"puerta:{puerta['id']}", f"Abrir {puerta['name']}", "Puertas",
            "door-open",
            {"type": "door.pulse", "target": f"door:{puerta['id']}",
             "params": {"seconds": 0}})

    for mando in datos["ir_remotes"]:
        for boton in mando.get("buttons", []):
            add(f"ir:{mando['id']}:{boton['id']}",
                f"{mando['name']}: {boton.get('label') or boton['id']}", "Mandos",
                mando.get("icon") or "tv",
                {"type": "ir_button.press",
                 "target": f"ir_button:{mando['id']}:{boton['id']}"})

    for equipo in datos["hosts"]:
        add(f"wol:{equipo['id']}", f"Encender {equipo['name']}", "Equipos", "zap",
            {"type": "host.wol", "target": f"host:{equipo['id']}"})
        for accion, verbo in (("apagar", "Apagar"), ("reiniciar", "Reiniciar")):
            add(f"host:{equipo['id']}:{accion}", f"{verbo} {equipo['name']}",
                "Equipos", "power",
                {"type": "host.action", "target": f"host:{equipo['id']}",
                 "params": {"accion": accion}})

    nombres_equipos = {equipo["id"]: equipo["name"] for equipo in datos["hosts"]}
    for boton in datos.get("host_buttons", []):
        equipo = nombres_equipos.get(boton.get("host_id"), boton.get("host_id", ""))
        add(f"host_button:{boton['id']}",
            f"{equipo}: {boton.get('label') or boton['id']}", "Equipos",
            "square-mouse-pointer",
            {"type": "host_button.run", "target": f"host_button:{boton['id']}"})

    try:
        reglas = automations_store.read_all()
    except automations_store.ArchivoCorrupto as error:
        # La paleta y la voz siguen ofreciendo el resto; una regla corrupta no
        # puede convertir en inutilizables luces, mandos y equipos.
        print(f"⚠️ Catálogo de comandos sin automatizaciones: {error}")
        reglas = []
    for regla in reglas:
        add(f"regla:{regla['id']}",
            f"Ejecutar la automatización «{regla.get('name') or regla['id']}»",
            "Automatizaciones", regla.get("icon") or "workflow",
            {"type": "rule.run", "target": f"rule:{regla['id']}"})

    for valor, verbo in (("on", "Armar"), ("off", "Desarmar")):
        add(f"sistema:{valor}", f"{verbo} el sistema", "Alarma", "shield",
            {"type": "system.arm", "target": "", "params": {"armed": valor}})
    for grupo in groups_store.read_all():
        for valor, verbo in (("on", "Armar"), ("off", "Desarmar")):
            # «el grupo» va en el texto y no sobra: hay un grupo de armado
            # llamado «PC» y un equipo llamado «PC», así que sin esto la lista
            # ofrecía «Armar PC» justo al lado de «Apagar PC». En una paleta que
            # se usa escribiendo dos letras y pulsando Enter, eso es un armado
            # accidental de la casa.
            add(f"grupo:{grupo['id']}:{valor}",
                f"{verbo} el grupo {grupo['name']}",
                "Alarma", "layers",
                {"type": "group.arm", "target": f"group:{grupo['id']}",
                 "params": {"armed": valor}})

    for comando in salida:
        comando["alexa_allowed"] = paso_permitido_alexa(
            comando["paso"], reglas=reglas, modos=modos)
    return salida


# Qué permiso pide cada familia de acción. Es el mismo criterio que usan las
# pestañas: las luces son luces, las puertas son accesos, y todo lo que toca el
# armado pide ARMAR. Lo de fuera de la tabla pide AJUSTES, que es el más
# restrictivo: si mañana se añade una acción y nadie se acuerda de ponerla aquí,
# el fallo es que no la puede usar nadie salvo un administrador — nunca al revés.
CAPACIDAD = {
    "light.set": permisos.LUCES,
    "door.pulse": permisos.PUERTAS,
    "ir_button.press": permisos.EQUIPOS,
    "host.wol": permisos.EQUIPOS,
    "host.action": permisos.EQUIPOS,
    "host_button.run": permisos.EQUIPOS,
    "system.arm": permisos.ARMAR,
    "group.arm": permisos.ARMAR,
    # Poner un modo puede armar la casa de un toque: mismo permiso que armar.
    "modo": permisos.ARMAR,
}


# Palabras que no distinguen nada y sobran al buscar. Sin quitarlas, «apaga el
# pc» no encuentra «Apagar PC» porque «el» no aparece en ningún comando.
_RELLENO = {
    "el", "la", "los", "las", "un", "una", "de", "del", "en", "al", "a", "y",
    "por", "para", "que", "me", "mi", "casa", "favor", "porfavor",
}

# Cómo se dice cada cosa de verdad. La clave es lo que se escribe o se dicta y el
# valor son las formas con las que puede estar escrito el comando.
#
# Hace falta porque los comandos están en INFINITIVO («Encender Habitación») y
# nadie habla en infinitivo: se dice «enciende la habitación». Y porque a un
# altavoz se le dicen las cosas de varias maneras que significan lo mismo
# («apaga», «quita», «cierra»).
#
# Es una tabla y no una búsqueda difusa a propósito: en un panel que abre puertas
# y arma alarmas, «se parece bastante» no es un criterio aceptable. Lo que no está
# en la tabla no se adivina.
_VARIANTES = {
    "enciende": ("encender",), "encender": ("encender",),
    "pon": ("encender", "poner"), "poner": ("poner", "encender"),
    "activa": ("encender", "activar"), "arranca": ("encender",),
    "apaga": ("apagar",), "apagar": ("apagar",),
    "quita": ("apagar", "quitar"), "corta": ("apagar",),
    "abre": ("abrir",), "abrir": ("abrir",),
    "arma": ("armar",), "armar": ("armar",),
    "desarma": ("desarmar",), "desarmar": ("desarmar",),
    "reinicia": ("reiniciar",), "reiniciar": ("reiniciar",),
    "vete": ("ir",), "ve": ("ir",), "abreme": ("abrir",),
}


def _variantes(palabra: str) -> tuple[str, ...]:
    """Las formas con las que esa palabra puede aparecer en un comando. Siempre
    incluye la palabra tal cual, que es lo que hace que escribir «enc» siga
    encontrando «Encender» en la paleta."""
    return (palabra, *_VARIANTES.get(palabra, ()))


def buscar(texto: str, todos: list[dict] | None = None) -> list[dict]:
    """Los comandos que casan con lo escrito o dictado.

    Todas las palabras que aporten algo tienen que aparecer, en cualquier orden y
    sin tildes, admitiendo la forma en que se habla («enciende» encuentra
    «Encender»). Es lo que hace que la misma función valga para una lista que se
    filtra a mano y para una frase que ha transcrito un altavoz, que nunca viene
    escrita como uno espera."""
    palabras = [p for p in plano(texto).split() if p not in _RELLENO]
    if not palabras:
        return []
    lista = todos if todos is not None else comandos()
    salida = []
    for c in lista:
        objetivo = plano(f"{c['familia']} {c['etiqueta']}")
        if all(any(v in objetivo for v in _variantes(p)) for p in palabras):
            salida.append((_puntos(c, palabras), c))
    # De mejor a peor coincidencia. Importa de verdad para la voz: «arma la casa»
    # casaba con «Ir a Alarma» —porque «arma» está dentro de «alarma»— igual que
    # con «Armar el sistema», y el primero de la lista es el que se ejecuta.
    salida.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in salida]


def _puntos(comando: dict, palabras: list[str]) -> tuple:
    """Lo bien que casa un comando, para ordenar. Más alto es mejor.

    Cuenta las palabras que casan al PRINCIPIO de una palabra del comando
    («arma» puntúa en «Armar el sistema» y no en «Alarma») y penaliza la familia
    «Ir a», que son comandos de navegación: quien le habla a un altavoz quiere que
    pasen cosas en la casa, no cambiar de pestaña."""
    etiqueta = plano(comando["etiqueta"])
    exactas = sum(
        1 for p in palabras
        if any(re.search(rf"\b{re.escape(v)}", etiqueta) for v in _variantes(p))
    )
    navegar = comando["familia"] == "Ir a"
    return (exactas, not navegar, -len(etiqueta))


def por_frase_guardada(texto: str, todos: list[dict] | None = None) -> dict | None:
    """El comando atado a esa frase EXACTA por el usuario, si lo hay.

    Se mira antes que la búsqueda por parecido, y es lo que hace el
    reconocimiento predecible: «buenas noches» no se parece a nada del catálogo,
    pero si alguien la ató a «Poner la casa en Noche», eso es lo que hace y no hay
    nada que adivinar. Ver nodes_store.list_comandos_voz.

    La comparación normaliza igual que el buscador (sin tildes, sin dobles
    espacios, en minúsculas) porque un altavoz transcribe como le parece."""
    buscada = plano(" ".join(texto.split()))
    if not buscada:
        return None
    for guardado in nodes_store.list_comandos_voz():
        if plano(guardado.get("frase", "")) != buscada:
            continue
        lista = todos if todos is not None else comandos()
        return next((c for c in lista if c["id"] == guardado.get("comando")), None)
    return None


def elegir(texto: str, todos: list[dict] | None = None) -> tuple[dict | None, list[dict]]:
    """(el comando elegido, las alternativas) para una frase.

    Devuelve `(None, alternativas)` cuando la frase NO distingue: si el segundo
    candidato puntúa igual que el primero, no hay ganador y quien llama tiene que
    preguntar en vez de elegir por su cuenta.

    Existe aparte de `buscar` porque la ambigüedad solo se puede medir con las
    palabras de la consulta delante, y es justo lo que hay que medir para la voz:
    «apaga» a secas casa con apagar la luz, apagar el PC y apagar el servidor, y
    ejecutar el primero de los tres es una moneda al aire con el PC de alguien.
    """
    palabras = [p for p in plano(texto).split() if p not in _RELLENO]
    encontrados = buscar(texto, todos)
    if not encontrados:
        return None, []
    if len(encontrados) == 1:
        return encontrados[0], encontrados
    # Se comparan solo las DOS primeras cifras de la puntuación: cuántas palabras
    # casan de verdad y si es un comando de navegación. La tercera es el desempate
    # por longitud del nombre, y meterla aquí hacía que nunca hubiera empate —
    # «apaga» elegía «Apagar PC» por ser el nombre más corto de los cinco, que no
    # es un criterio, es un sorteo.
    if (_puntos(encontrados[0], palabras)[:2]
            == _puntos(encontrados[1], palabras)[:2]):
        return None, encontrados
    return encontrados[0], encontrados
