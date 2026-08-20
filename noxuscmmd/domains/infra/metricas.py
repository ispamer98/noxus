"""
Muestrea unos pocos números cada rato para poder pintarlos luego.

Las gráficas de la fase 5.3 son de tres cosas, y solo dos necesitan que alguien
las apunte:

  - Las APERTURAS por hora y por día NO se muestrean. Ya están en el registro de
    eventos desde siempre, así que se cuentan con una consulta
    (logs_store.conteo_por_hora_del_dia). Guardar un contador aparte sería tener
    el mismo dato dos veces y con dos formas de equivocarse.
  - La TEMPERATURA de la Raspberry y los EQUIPOS EN LÍNEA sí, porque hasta ahora
    se leían para pintarlas en el momento y se tiraban. Sin guardarlas no hay
    forma de saber si hoy hace más calor que ayer.

POR QUÉ ESTO PINGA POR SU CUENTA en vez de leer `host_online` de
nodos_dinamicos.json, que ya lo tiene: porque ese fichero lo escribe el bucle de
`InfraState.actualizar_estados`, que es un manejador de SESIÓN. Solo pinga el
primer bucle del proceso, y si nadie tiene el panel abierto no pinga nadie: el
fichero se queda con la última foto que hubiera. Una métrica que se congela por
la noche —justo cuando nadie mira el panel— y luego se pinta como una línea
plana es peor que no tener la métrica, porque parece un dato. Un ping cada cinco
minutos no le cuesta nada a nadie y esto queda independiente de que haya
pestañas abiertas.

Es una tarea del CICLO DE VIDA del proceso, por lo mismo que el vigilante de la
alarma y las copias: un histórico que solo se rellena cuando alguien tiene la web
abierta no es un histórico.
"""
import asyncio
import os
import time

from ..devices import registry
from ..nodes import operations, store as nodes_store
from ..security import logs_store
from ...core.connectivity import NetUtils
from ...core import maquina
from ...core.sensors import Sensors

# Cada cuánto se toma una muestra. Cinco minutos dan 288 al día por serie: de
# sobra para ver la forma de un día y poco para el disco (unos 6 MB al año las
# dos series juntas).
INTERVALO = float(os.getenv("METRICAS_INTERVALO", "300"))

# Cuánto se conserva. Un año, igual que los fotogramas.
MAX_DIAS = int(os.getenv("METRICAS_MAX_DIAS", "365"))

# Nombres de las series. Con punto, para que se ordenen por familia si algún día
# hay muchas.
TEMP_CPU = "cpu.temp"
EQUIPOS_EN_LINEA = "equipos.en_linea"
EQUIPOS_TOTAL = "equipos.total"

# Serie de UN equipo concreto: 1 en línea, 0 caído. Solo se guarda de los que
# están marcados en su ficha (`en_metricas`), porque son 288 muestras al día por
# equipo y guardarlas de los once para luego mirar dos es engordar la base por
# nada. Se marcan desde la pestaña Métricas.
PREFIJO_EQUIPO = "equipo."

# El propio servidor. Es la máquina donde corre todo esto —el panel, la alarma,
# las automatizaciones—, así que si se queda sin disco o se calienta, no falla
# una cosa: fallan todas. Se lee de /proc y /sys, sin SSH y sin coste (ver
# core/maquina.py).
SERVIDOR_TEMP = "servidor.temp"
SERVIDOR_CPU = "servidor.cpu"
SERVIDOR_RAM = "servidor.ram"
SERVIDOR_DISCO = "servidor.disco"

# Temperatura de UN equipo por SSH: `temp.<host_id>`. Igual que la serie de
# arriba, solo de los marcados en métricas, y solo si están respondiendo — a un
# equipo apagado no se le abre una sesión SSH cada cinco minutos para nada.
PREFIJO_TEMP_EQUIPO = "temp."

# Equipos que YA tienen su propia serie de temperatura y a los que por tanto no
# se les pregunta otra vez por SSH — dos series de lo mismo saldrían en el
# catálogo como dos cosas distintas:
#
#   raspberry  la tiene desde antes de que esto midiera temperaturas de
#              cualquier equipo (TEMP_CPU), y con meses de histórico detrás.
#   server     es ESTA máquina. Se lee de /sys directamente y sin coste
#              (SERVIDOR_TEMP); abrirse una sesión SSH a uno mismo para
#              preguntarse la temperatura no tiene ningún sentido.
EQUIPOS_CON_SERIE_PROPIA = ("raspberry", "server")


def clave_de_equipo(host_id: str) -> str:
    return f"{PREFIJO_EQUIPO}{host_id}"


def clave_de_temperatura(host_id: str) -> str:
    return f"{PREFIJO_TEMP_EQUIPO}{host_id}"


async def _servidor() -> None:
    """Las cuatro del propio servidor. Cada una por su lado: que no se pueda
    leer la temperatura no puede dejarnos sin el disco, que es la que avisa con
    tiempo de que esto se va a parar."""
    for clave, medir in (
        (SERVIDOR_TEMP, maquina.temperatura_cpu),
        (SERVIDOR_CPU, maquina.uso_cpu),
        (SERVIDOR_RAM, maquina.uso_ram),
        (SERVIDOR_DISCO, maquina.uso_disco),
    ):
        try:
            valor = await asyncio.to_thread(medir)
        except Exception as e:
            print(f"⚠️ Métrica {clave}: {e}")
            continue
        # None es «no se pudo medir»: se deja el hueco. Ver core/maquina.py.
        if valor is not None:
            await asyncio.to_thread(logs_store.anotar, clave, float(valor))


async def _temperaturas_de_equipos() -> None:
    """Temperatura por SSH de los equipos marcados en métricas.

    Solo a los que están respondiendo, y eso se sabe sin pingar otra vez: lo
    acaba de dejar escrito el ping del proceso (infra/ping_motor.py). Abrirle
    una sesión SSH a un equipo apagado es esperar a que expire el temporizador
    para nada, cinco minutos después otra vez.
    """
    marcados = await asyncio.to_thread(nodes_store.equipos_en_metricas)
    if not marcados:
        return
    en_linea = await asyncio.to_thread(nodes_store.get_all_host_online)
    fichas = registry.hosts()
    for equipo in marcados:
        host_id = equipo["id"]
        if host_id in EQUIPOS_CON_SERIE_PROPIA or not en_linea.get(host_id):
            continue
        # Solo a quien PUEDE contestar. En esta casa están marcados en métricas
        # todos los equipos —también los iPhones y la tablet, porque interesa
        # ver cuándo están en casa—, y a un móvil no se le abre una sesión SSH
        # cada cinco minutos para preguntarle la temperatura: no la tiene, no
        # hay usuario con el que entrar, y la espera se paga igual.
        ssh = getattr(fichas.get(host_id), "ssh", None)
        if not getattr(ssh, "user", ""):
            continue
        try:
            grados = await operations.read_host_temperature(host_id)
        except Exception:
            continue  # ese equipo no sabe darla; no es un fallo del muestreo
        if grados is not None and 0 < grados < 150:
            await asyncio.to_thread(logs_store.anotar,
                                    clave_de_temperatura(host_id), float(grados))


async def _temperatura() -> None:
    """La de la Raspberry, por SSH (ver core/sensors.py).

    El cero NO se guarda: `get_cpu_temp_async` devuelve 0.0 cuando el SSH falla,
    y una muestra de cero grados pintaría una gráfica que dice que la Raspberry
    se congeló. Un hueco en la línea es la verdad; un cero es una mentira que
    encima arrastra la media hacia abajo."""
    grados = await Sensors.get_cpu_temp_async()
    if grados <= 0:
        return
    await asyncio.to_thread(logs_store.anotar, TEMP_CPU, grados)


async def _equipos() -> None:
    """Cuántos equipos responden al ping, y cuántos hay dados de alta.

    Se guardan los dos: «3 en línea» no dice nada si no se sabe si hay 4 o 12, y
    el total cambia cuando se da de alta o se quita un equipo, así que no se
    puede deducir después mirando la ficha de hoy."""
    equipos = list(registry.hosts().items())
    if not equipos:
        return
    resultados = await NetUtils.ping_all(
        [(h.ssh.host, h.ping_retries) for _, h in equipos]
    )
    await asyncio.to_thread(logs_store.anotar, EQUIPOS_EN_LINEA,
                            float(sum(1 for x in resultados if x)))
    await asyncio.to_thread(logs_store.anotar, EQUIPOS_TOTAL, float(len(equipos)))

    # Y el estado de cada equipo marcado, con el MISMO ping que el recuento: dos
    # rondas separadas darían dos fotos de instantes distintos y podría salir
    # «3 en línea» junto a cuatro equipos marcados como caídos.
    marcados = {e["id"] for e in await asyncio.to_thread(nodes_store.equipos_en_metricas)}
    for (host_id, _), online in zip(equipos, resultados):
        if host_id in marcados:
            await asyncio.to_thread(logs_store.anotar,
                                    clave_de_equipo(host_id), 1.0 if online else 0.0)


async def muestrear() -> None:
    """Una ronda. Cada serie va en su propio try: que el SSH de la temperatura
    esté caído no puede dejarnos sin el recuento de equipos."""
    for nombre, tarea in (("temperatura", _temperatura), ("equipos", _equipos),
                          ("servidor", _servidor),
                          ("temperaturas de equipos", _temperaturas_de_equipos)):
        try:
            await tarea()
        except Exception as e:
            print(f"⚠️ Métrica de {nombre}: {e}")


async def run_forever() -> None:
    """Bucle de muestreo, colgado del proceso (register_lifespan_task).

    Empieza esperando: al arrancar, el panel está compilando y la Raspberry
    puede no tener todavía la conexión SSH en pie, así que la primera muestra
    saldría mala. Y no se acumula deriva porque se descuenta lo que tardó la
    ronda: sin eso, con rondas de 12 s las muestras se irían separando cada vez
    más y los tramos por hora dejarían de tener el mismo peso."""
    await asyncio.sleep(30)
    while True:
        arranque = time.monotonic()
        try:
            await muestrear()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"⚠️ Error muestreando métricas: {e}")
        await asyncio.sleep(max(5.0, INTERVALO - (time.monotonic() - arranque)))
