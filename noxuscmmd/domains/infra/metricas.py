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
from ..nodes import store as nodes_store
from ..security import logs_store
from ...core.connectivity import NetUtils
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


def clave_de_equipo(host_id: str) -> str:
    return f"{PREFIJO_EQUIPO}{host_id}"


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
    for nombre, tarea in (("temperatura", _temperatura), ("equipos", _equipos)):
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
