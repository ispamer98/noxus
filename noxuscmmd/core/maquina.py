"""
Lo que se puede medir de ESTA máquina: temperatura, CPU, memoria y disco.

Se lee de /proc y de /sys y no de una biblioteca. No es purismo: instalar algo
como psutil para leer cuatro ficheros de texto es una dependencia más que
mantener en un servidor que sostiene la casa, y estos ficheros llevan
décadas con el mismo formato.

Todo devuelve None cuando no se puede medir, y NUNCA un cero. Es el mismo
criterio que la temperatura de la Raspberry (ver infra/metricas.py): un hueco en
la gráfica es la verdad —«esto no se pudo leer»—, mientras que un cero es una
mentira que además arrastra la media hacia abajo y hace pensar que la máquina
se enfrió de golpe.
"""
import os
from pathlib import Path

_TERMICAS = Path("/sys/class/thermal")

# Zonas térmicas que SÍ son la CPU. La lista importa: esta máquina expone
# también `iwlwifi_1`, que es la tarjeta wifi y marca su propia temperatura —
# guardar esa creyendo que es la del procesador daría una gráfica que sube
# cuando hay tráfico de red, no cuando hay trabajo.
_TIPOS_CPU = ("x86_pkg_temp", "coretemp", "cpu_thermal", "cpu-thermal",
              "soc_thermal", "k10temp", "acpitz")

# Última lectura de /proc/stat, para poder sacar el porcentaje de uso: ese
# fichero da tiempo ACUMULADO desde que arrancó la máquina, así que un valor
# suelto no dice nada. El porcentaje sale de la diferencia entre dos lecturas,
# y aquí eso significa «desde la muestra anterior» — con muestras cada cinco
# minutos, el uso medio de esos cinco minutos.
_ANTERIOR: tuple[float, float] | None = None


def temperatura_cpu() -> float | None:
    """Grados de la CPU, o None si esta máquina no lo dice."""
    try:
        zonas = sorted(_TERMICAS.glob("thermal_zone*"))
    except Exception:
        return None
    for zona in zonas:
        try:
            tipo = (zona / "type").read_text().strip()
            if not any(tipo.startswith(t) for t in _TIPOS_CPU):
                continue
            crudo = int((zona / "temp").read_text().strip())
        except Exception:
            continue
        grados = crudo / 1000.0
        # Un valor fuera de lo posible es un sensor mal leído, no un dato.
        if 0 < grados < 150:
            return round(grados, 1)
    return None


def uso_cpu() -> float | None:
    """Porcentaje de CPU usado DESDE LA LLAMADA ANTERIOR, o None la primera vez.

    La primera vez devuelve None a propósito y no un cero: todavía no hay dos
    lecturas que restar, y un cero ahí sería inventarse que la máquina estuvo
    parada.
    """
    global _ANTERIOR
    try:
        primera = Path("/proc/stat").read_text().split("\n")[0].split()
    except Exception:
        return None
    if not primera or primera[0] != "cpu":
        return None
    try:
        campos = [float(x) for x in primera[1:]]
    except ValueError:
        return None
    total = sum(campos)
    # El cuarto campo es "idle" y el quinto "iowait": esperar al disco no es
    # estar trabajando, así que cuenta como tiempo parado.
    parado = campos[3] + (campos[4] if len(campos) > 4 else 0.0)

    anterior, _ANTERIOR = _ANTERIOR, (total, parado)
    if anterior is None:
        return None
    d_total = total - anterior[0]
    d_parado = parado - anterior[1]
    if d_total <= 0:
        return None
    usado = 100.0 * (1.0 - d_parado / d_total)
    return round(max(0.0, min(100.0, usado)), 1)


def uso_ram() -> float | None:
    """Porcentaje de memoria EN USO.

    Se calcula con MemAvailable y no con MemFree: en Linux la memoria «libre»
    casi siempre es poca porque el sistema usa lo que sobra de caché de disco, y
    pintar eso diría que el servidor está al 90 % cuando no le falta memoria a
    nadie. MemAvailable es lo que el kernel dice que puede dar sin penalizar.
    """
    try:
        datos = {}
        for linea in Path("/proc/meminfo").read_text().split("\n"):
            partes = linea.split(":")
            if len(partes) == 2:
                datos[partes[0]] = float(partes[1].strip().split()[0])
    except Exception:
        return None
    total = datos.get("MemTotal", 0.0)
    disponible = datos.get("MemAvailable")
    if not total or disponible is None:
        return None
    return round(100.0 * (total - disponible) / total, 1)


def uso_disco(punto: str = "/") -> float | None:
    """Porcentaje ocupado del disco donde vive el sistema."""
    try:
        st = os.statvfs(punto)
    except Exception:
        return None
    total = st.f_blocks * st.f_frsize
    if total <= 0:
        return None
    # f_bavail y no f_bfree: hay un porcentaje reservado para root que un
    # usuario normal no puede usar, así que contarlo como libre engaña.
    libre = st.f_bavail * st.f_frsize
    return round(100.0 * (total - libre) / total, 1)


def encendida_desde() -> float | None:
    """Segundos que lleva encendida la máquina."""
    try:
        return float(Path("/proc/uptime").read_text().split()[0])
    except Exception:
        return None


def _reiniciar_para_pruebas() -> None:
    """Olvida la lectura anterior de /proc/stat. Solo lo usan las pruebas."""
    global _ANTERIOR
    _ANTERIOR = None
