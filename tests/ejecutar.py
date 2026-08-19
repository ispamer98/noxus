"""
Lanza todas las pruebas:

    .venv/bin/python tests/ejecutar.py

IMPORTANTE, y es la razón de que este fichero exista en vez de un `import` suelto
arriba de cada prueba: los módulos del panel leen su fichero de la variable de
entorno EN EL MOMENTO DE IMPORTARSE (`ARCHIVO = Path(os.getenv(...))` a nivel de
módulo). Así que la casa de pruebas tiene que estar montada ANTES del primer
import del panel. Por eso los módulos de prueba se importan aquí dentro del
`with` y no en la cabecera.

Ninguna prueba toca el hardware de la casa: ver la regla en comun.py.
"""
import importlib
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from tests.comun import CasaDePruebas  # noqa: E402

PRUEBAS = (
    "tests.test_nucleo",       # escritura atómica, permisos y retardos
    "tests.test_sesiones",     # que los bucles de fondo mueran con su sesión
    "tests.test_bus",         # que despierten por aviso y no por sondeo
    "tests.test_instalador",   # descubrimiento MQTT y la salvaguarda del topic
    "tests.test_presencia",    # patrón aprendido y plan del día
    "tests.test_accesorios",     # luces y aparatos que se encienden por mando
    "tests.test_movimiento",   # comparación de fotogramas de cámara
    "tests.test_claves",       # que una clave de voz no sea una sesión
)


def main() -> int:
    fallos: list[str] = []
    hechas = 0
    with CasaDePruebas() as casa:
        print(f"Casa de pruebas en {casa.dir}\n")
        for nombre in PRUEBAS:
            modulo = importlib.import_module(nombre)
            for caso in modulo.ejecutar():
                fallos += caso.fallos
                hechas += caso.hechas
            print()

    print("─" * 60)
    if fallos:
        print(f"{len(fallos)} FALLO(S) de {hechas} comprobación(es):")
        for f in fallos:
            print(f"  · {f}")
        return 1
    print(f"TODO BIEN — {hechas} comprobaciones")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
