"""
Simulación de presencia: repetir los horarios REALES de la casa cuando no hay
nadie, en vez de encender una luz a una hora fija.

Una luz que se enciende a las 21:00 en punto todos los días delata que no hay
nadie igual que una casa a oscuras. Aquí el patrón se aprende del histórico
(que lleva semanas guardándose, ver logs_store) y cada día se genera un plan
distinto dentro de ese patrón.

QUÉ SE APRENDE Y DE QUÉ
No solo de las luces: cuenta como señal de gente cualquier cosa que solo pasa
si hay alguien —desarmar, abrir la puerta, usar un mando, un equipo que se
enciende—. Son muchas más señales que los encendidos de luz, y para saber a qué
HORAS hay vida en la casa da igual de dónde venga la señal. Lo que sí sale solo
de las luces es QUÉ encender, porque es lo único que esto puede accionar.

DÍAS QUE NO CUENTAN
Se descartan los días de pruebas, que si no arrastran el patrón entero: el
26/07/2026 hay 25 armados y 25 desarmados dentro de la misma hora, de una
migración. Dos criterios, ver `_dias_a_descartar`: densidad muy por encima de la
mediana, y ráfagas de la misma acción repetida en una hora.

LO QUE NO HACE
Nada de esto acciona luces por su cuenta: aquí se aprende y se decide, y el plan
lo ejecuta presencia_state. Separado a propósito — así el patrón se puede mirar
y probar sin que se encienda nada en la casa.
"""
import random
import statistics
import time

from . import logs_store

# Cosas que solo pasan si hay alguien en casa. EQUIPO_* entra aunque tenga algo
# de ruido de red (ver infra/state: ya viene estabilizado) porque un PC o una
# tele encendiéndose es la mejor señal de actividad que hay en este histórico.
SENALES_DE_GENTE = (
    "LUZ_ENCENDIDA", "LUZ_APAGADA",
    "DESARMADO", "ARMADO",
    "PUERTA_ABIERTA", "ELEMENTO_ABIERTO",
    "MANDO_IR_BOTON_ENVIADO",
    "EQUIPO_CONECTADO", "EQUIPO_DESCONECTADO",
)

ACCIONES_LUZ = ("LUZ_ENCENDIDA", "LUZ_APAGADA")

# Para detectar días de pruebas solo se miran las acciones que una persona hace
# de una en una. EQUIPO_* y ELEMENTO_* se repiten muchas veces por hora en un día
# perfectamente normal (un equipo que va y viene por wifi, una puerta que se
# abre y se cierra), y contarlas hacía que se descartaran 8 de 23 días.
ACCIONES_DELIBERADAS = (
    "LUZ_ENCENDIDA", "LUZ_APAGADA", "DESARMADO", "ARMADO",
    "MANDO_IR_BOTON_ENVIADO",
)

# Horas en las que una luz encendida dice «hay alguien». Fuera de aquí no se
# simula nada: a las cuatro de la mañana una luz llama la atención, y a mediodía
# no se ve desde la calle, así que solo gastaría. Se cruza con lo aprendido, no
# lo sustituye.
VENTANA_LUZ = tuple(range(19, 24)) + (7, 8)

# Cuánto histórico se mira. Mes y medio: suficiente para tener varias veces cada
# día de la semana sin arrastrar costumbres de otra estación del año.
DIAS_POR_DEFECTO = 45

# A partir de cuántas veces sobre los días observados se considera que esa hora
# es de estar despierto. 0.30 = uno de cada tres días.
UMBRAL = 0.30

# Con menos días que esto de un día de la semana concreto no hay nada que
# aprender de él y se cae a las franjas de reserva.
MINIMO_DIAS = 2

# Franjas de reserva, para cuando no hay histórico suficiente. Es lo que haría
# cualquiera a mano, y solo se usa mientras no haya datos de verdad.
RESERVA_HORAS = (20, 21, 22)

# Cuánto dura un encendido, en minutos. Se sortea dentro de esto.
DURACION_MIN, DURACION_MAX = 18, 95


def _dias_a_descartar(por_dia: dict[str, int],
                      rafagas: dict[str, int]) -> set[str]:
    """Los días que no representan la vida normal de la casa.

    Dos motivos, y basta con uno:
      · densidad: más de cuatro veces la mediana de eventos por día;
      · ráfaga: más de veinte veces la misma acción DELIBERADA dentro de una
        misma hora. Veinte y no diez porque el caso que hay que cazar es el del
        26/07 (25 armados seguidos de una migración) y con diez se llevaba por
        delante días normales; y solo acciones deliberadas, ver
        ACCIONES_DELIBERADAS.
    """
    fuera = {fecha for fecha, n in rafagas.items() if n > 20}
    if len(por_dia) >= 4:
        mediana = statistics.median(por_dia.values())
        if mediana > 0:
            fuera |= {f for f, n in por_dia.items() if n > mediana * 4}
    return fuera


def aprender(dias: int = DIAS_POR_DEFECTO, ahora: float | None = None) -> dict:
    """Mira el histórico y devuelve el patrón de la casa.

    {
      "horas":   {dia_semana: {hora: probabilidad}},   0 = lunes
      "luces":   {id: {"veces": n, "horas": {hora: n}}},
      "dias":    {dia_semana: cuantos dias distintos se han visto},
      "descartados": [fechas que no se han contado],
      "total_eventos": n,
    }
    """
    ahora = time.time() if ahora is None else ahora
    desde = ahora - dias * 86400

    # (fecha, dow, hora) -> visto; y los contadores para descartar días.
    vistos: set[tuple[str, int, int]] = set()
    dias_por_dow: dict[int, set[str]] = {}
    eventos_por_dia: dict[str, int] = {}
    rafaga: dict[tuple[str, str, int], int] = {}
    luces: dict[str, dict] = {}
    total = 0

    for ev in logs_store.recorrer(desde=desde):
        accion = ev["accion"]
        if accion not in SENALES_DE_GENTE:
            continue
        marca = ev["ts"]
        if not marca:
            continue
        t = time.localtime(marca)
        fecha = time.strftime("%Y-%m-%d", t)
        dow, hora = t.tm_wday, t.tm_hour

        total += 1
        eventos_por_dia[fecha] = eventos_por_dia.get(fecha, 0) + 1
        if accion in ACCIONES_DELIBERADAS:
            clave_rafaga = (fecha, accion, hora)
            rafaga[clave_rafaga] = rafaga.get(clave_rafaga, 0) + 1
        vistos.add((fecha, dow, hora))
        dias_por_dow.setdefault(dow, set()).add(fecha)

        if accion in ACCIONES_LUZ and ev["entidad"]:
            ficha = luces.setdefault(ev["entidad"], {"veces": 0, "horas": {}})
            ficha["veces"] += 1
            ficha["horas"][hora] = ficha["horas"].get(hora, 0) + 1

    # Las ráfagas se resumen por día antes de decidir.
    peor_rafaga: dict[str, int] = {}
    for (fecha, _, _), n in rafaga.items():
        peor_rafaga[fecha] = max(peor_rafaga.get(fecha, 0), n)
    fuera = _dias_a_descartar(eventos_por_dia, peor_rafaga)

    # Y ahora, ya sin esos días, cuántos días distintos de cada día de la semana
    # tuvieron actividad en cada hora.
    conteo: dict[int, dict[int, int]] = {}
    for fecha, dow, hora in vistos:
        if fecha in fuera:
            continue
        conteo.setdefault(dow, {})
        conteo[dow][hora] = conteo[dow].get(hora, 0) + 1

    dias_limpios = {d: len(f - fuera) for d, f in dias_por_dow.items()}
    horas = {
        dow: {h: round(n / dias_limpios[dow], 3)
              for h, n in por_hora.items() if dias_limpios.get(dow)}
        for dow, por_hora in conteo.items()
    }

    for luz in luces.values():
        luz["horas"] = dict(sorted(luz["horas"].items()))

    return {
        "horas": horas,
        "luces": luces,
        "dias": dias_limpios,
        "descartados": sorted(fuera),
        "total_eventos": total,
    }


def horas_activas(patron: dict, dow: int) -> list[int]:
    """Las horas en las que ese día de la semana suele haber gente despierta.

    Siempre dentro de VENTANA_LUZ: de lo aprendido solo interesa la parte en la
    que encender una luz significa algo. Cae a RESERVA_HORAS cuando no hay días
    suficientes de ese día de la semana, o cuando lo aprendido no cruza con la
    ventana: más vale una luz a una hora razonable que ninguna.
    """
    if patron["dias"].get(dow, 0) < MINIMO_DIAS:
        return list(RESERVA_HORAS)
    activas = sorted(h for h, p in patron["horas"].get(dow, {}).items()
                     if p >= UMBRAL and h in VENTANA_LUZ)
    return activas or list(RESERVA_HORAS)


def luces_utiles(patron: dict, permitidas: list[str] | None = None) -> list[str]:
    """Las luces que de verdad se usan, de más usada a menos.

    `permitidas` es la lista que el usuario haya elegido en la pantalla: si está
    puesta, manda ella — una luz puede ser la más usada de la casa y ser
    justamente la del dormitorio, que no se quiere encender sola.
    """
    usadas = sorted(patron["luces"], key=lambda i: -patron["luces"][i]["veces"])
    if permitidas is None:
        return usadas
    orden = [i for i in usadas if i in permitidas]
    # Las permitidas que no aparecen en el histórico van detrás: sirven igual,
    # simplemente no hay constancia de a qué hora se usan.
    return orden + [i for i in permitidas if i not in orden]


def plan_del_dia(patron: dict, dow: int, permitidas: list[str] | None = None,
                 semilla: int | None = None) -> list[dict]:
    """El guion de hoy: qué luz se enciende, a qué minuto y cuánto dura.

    Devuelve una lista ordenada de {"minuto", "luz", "encender"}, con el minuto
    contado desde medianoche. El minuto exacto se sortea dentro de la hora, así
    que dos días seguidos no se parecen; con `semilla` sale siempre el mismo
    plan, que es lo que permite probarlo y también enseñarlo en la pantalla
    antes de que ocurra.
    """
    azar = random.Random(semilla)
    luces = luces_utiles(patron, permitidas)
    if not luces:
        return []

    acciones: list[dict] = []
    ocupada_hasta: dict[str, int] = {}

    for hora in horas_activas(patron, dow):
        # Se prefiere una luz que ya se haya usado a esta hora; si ninguna, la
        # más usada en general. Así una casa que enciende la cocina a las 8 y el
        # salón a las 22 no acaba encendiendo el salón a las 8.
        candidatas = [i for i in luces
                      if hora in patron["luces"].get(i, {}).get("horas", {})]
        luz = azar.choice(candidatas) if candidatas else luces[0]

        inicio = hora * 60 + azar.randint(0, 59)
        if inicio < ocupada_hasta.get(luz, -1):
            continue  # esa luz ya está encendida en ese momento
        fin = min(inicio + azar.randint(DURACION_MIN, DURACION_MAX), 24 * 60 - 1)
        ocupada_hasta[luz] = fin
        acciones.append({"minuto": inicio, "luz": luz, "encender": True})
        acciones.append({"minuto": fin, "luz": luz, "encender": False})

    acciones.sort(key=lambda a: (a["minuto"], a["encender"]))
    return acciones


def resumen(patron: dict) -> str:
    """Una línea para la pantalla, en lenguaje de persona."""
    dias = sum(patron["dias"].values())
    if not dias:
        return ("Todavía no hay histórico suficiente: se usarán las franjas de "
                "reserva (de 20 a 23) hasta que lo haya.")
    luces = len(patron["luces"])
    fuera = len(patron["descartados"])
    texto = (f"Aprendido de {dias} día(s) y {patron['total_eventos']} señal(es), "
             f"con {luces} luz/luces con historial")
    if fuera:
        texto += f"; {fuera} día(s) descartado(s) por parecer pruebas"
    return texto + "."
