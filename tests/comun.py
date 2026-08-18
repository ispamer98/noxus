"""
Andamiaje mínimo de las pruebas. Sin pytest a propósito: este panel corre en
producción con su propio venv y no merece una dependencia más para esto.

REGLA QUE NO SE SALTA NINGUNA PRUEBA: nada de lo que se prueba aquí puede llegar
al hardware de la casa. Aislar los JSON con variables de entorno NO BASTA —el
MQTT y el SSH no son ficheros—, así que aquí solo entra lo que DECIDE (resolver
un comando, calcular un retardo, elegir un plan, comprobar un permiso) y nunca
lo que EJECUTA. Probando el endpoint de voz una vez se apagó el PC del usuario,
se abrió la puerta de la calle y se encendió una luz.

Cada módulo de prueba expone `ejecutar()` y devuelve la lista de fallos.
"""
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


class Caso:
    """Un contador de comprobaciones con nombre, para que el resumen final diga
    qué ha fallado y no solo cuántas."""

    def __init__(self, titulo: str):
        self.titulo = titulo
        self.fallos: list[str] = []
        self.hechas = 0
        print(f"── {titulo}")

    def revisar(self, que: str, obtenido, esperado) -> bool:
        self.hechas += 1
        ok = obtenido == esperado
        print(f"   [{'ok' if ok else 'FALLA'}] {que}")
        if not ok:
            print(f"          obtenido: {obtenido!r}")
            print(f"          esperado: {esperado!r}")
            self.fallos.append(f"{self.titulo}: {que}")
        return ok

    def cierto(self, que: str, obtenido) -> bool:
        return self.revisar(que, bool(obtenido), True)


class CasaDePruebas:
    """Una casa de mentira: copia de los ficheros de la casa real en un
    directorio temporal, con las variables de entorno apuntando ahí.

    Se COPIA en vez de inventarse los datos para que las pruebas se ejecuten
    contra la forma real de los ficheros de esta instalación —que es donde
    aparecen los campos que el código de verdad se encuentra—, pero sin poder
    escribir en ellos.
    """

    FICHEROS = {
        "NODOS_FILE": "nodos_dinamicos.json",
        "DISPOSITIVOS_FILE": "dispositivos.json",
        "ESTADO_FILE": "estado_seguridad.json",
        "GRUPOS_FILE": "grupos_armado.json",
        "RETARDOS_FILE": "retardos.json",
        "MODOS_FILE": "modos.json",
        "ALERTAS_FILE": "alertas.json",
        "PRESENCIA_FILE": "presencia.json",
        "MOVIMIENTO_FILE": "movimiento.json",
        "AUTOMATIZACIONES_FILE": "automatizaciones.json",
    }

    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="noxus_pruebas_"))
        self._antes: dict[str, str | None] = {}

    def __enter__(self):
        for var, nombre in self.FICHEROS.items():
            destino = self.dir / nombre
            origen = RAIZ / nombre
            if origen.exists():
                shutil.copy2(origen, destino)
            self._poner(var, str(destino))

        # El histórico se copia con VACUUM INTO, que es como lo hace el propio
        # panel: da una base coherente aunque el WAL esté a medias.
        hist = RAIZ / "historico.db"
        copia = self.dir / "historico.db"
        if hist.exists():
            cx = sqlite3.connect(f"file:{hist}?mode=ro", uri=True)
            try:
                cx.execute("VACUUM INTO ?", (str(copia),))
            finally:
                cx.close()
        self._poner("HISTORICO_DB", str(copia))
        self._poner("FOTOGRAMAS_DIR", str(self.dir / "fotogramas"))
        self._poner("PLANOS_DIR", str(self.dir / "planos"))
        return self

    def _poner(self, var: str, valor: str) -> None:
        self._antes[var] = os.environ.get(var)
        os.environ[var] = valor

    def __exit__(self, *_):
        for var, antes in self._antes.items():
            if antes is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = antes
        shutil.rmtree(self.dir, ignore_errors=True)
        return False
