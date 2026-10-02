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
    "tests.test_entidades",    # inventario y bajas comunes de toda configuración
    "tests.test_alexa",        # comandos Hue como pulsadores de un solo uso
    "tests.test_alexa_cloud",  # contrato Smart Home y OAuth sin tocar Amazon
    "tests.test_metricas",      # analíticas configurables con histórico aislado
    "tests.test_avisos",       # qué categoría de aviso tiene cada dispositivo
    "tests.test_n8n",          # el puente con n8n: qué sale y qué se deja entrar
    "tests.test_entrada",      # arranque agrupado sin encolar viajes al backend
    "tests.test_conexion",     # ping normal y comprobación de puerto (los Echo)
    "tests.test_portero",      # el filtro de eventos por rol (tablet, sin acceso, resto)
    "tests.test_kiosco",       # la tablet de habitación: miembros, rol y confinamiento
    "tests.test_porton",       # un pulso o dos: mantener, abrir para pasar y el plano
    "tests.test_electro",      # electrodomésticos simulados: órdenes, cuenta atrás y temporizadores
    "tests.test_pruebas",      # Pruebas: valores forzados, caducidad y separación de lo real
    "tests.test_acceso_app",   # visitantes efímeros y auditoría de entrada
    "tests.test_despliegue",   # terminal del servicio: permisos, estado y caché
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
