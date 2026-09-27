"""Analíticas configurables sobre un histórico y unas fichas inventadas.

Las rutas se aíslan ANTES de importar el panel y también se sustituyen en los
módulos ya cargados por el arnés. No se lee logs.json, no se muestrea hardware
y nunca se escribe en los JSON ni en la base de la casa.
"""
import asyncio
import importlib
import json
import os
import sqlite3
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from tests.comun import Caso


def _ts(fecha: str) -> float:
    return datetime.fromisoformat(fecha).timestamp()


@contextmanager
def _almacenes_temporales():
    with tempfile.TemporaryDirectory(prefix="noxus_metricas_") as temporal:
        raiz = Path(temporal)
        nodos = raiz / "nodos.json"
        historico = raiz / "historico.db"
        heredado = raiz / "no_existe.json"
        nodos.write_text("{}", encoding="utf-8")
        with patch.dict(os.environ, {
            "NODOS_FILE": str(nodos), "HISTORICO_DB": str(historico),
            "LOGS_FILE": str(heredado),
        }):
            store = importlib.import_module("noxuscmmd.domains.nodes.store")
            logs = importlib.import_module("noxuscmmd.domains.security.logs_store")
            with patch.object(store, "ARCHIVO", nodos), patch.multiple(
                logs, RUTA=historico, JSON_HEREDADO=heredado, _preparada=False,
            ):
                logs.preparar()
                yield store, logs


def _insertar_eventos(logs, filas: list[tuple[str, str, str]]) -> None:
    # Fixture directa: evita tanto el reloj como la deduplicación de sensores.
    with sqlite3.connect(logs.RUTA) as conexion:
        conexion.executemany(
            "INSERT INTO eventos(ts,timestamp,categoria,accion,usuario) "
            "VALUES(?,?,?,?,?)",
            [(int(_ts(fecha)), fecha.replace("T", " "), categoria, accion,
              "prueba") for fecha, categoria, accion in filas],
        )


def _series(logs) -> Caso:
    c = Caso("Métricas: agregación, límites y huecos")
    clave = "prueba.ponderada"
    for fecha, valor in (
        ("2025-01-09T23:59:59", 900),
        ("2025-01-10T00:00:00", 10),
        ("2025-01-10T00:30:00", 20),
        ("2025-01-10T01:10:00", 60),
        ("2025-01-10T03:00:00", 999),
    ):
        logs.anotar(clave, valor, _ts(fecha))
    desde, hasta = _ts("2025-01-10T00:00"), _ts("2025-01-10T03:00")
    horas = logs.consultar_metricas(clave, desde, hasta)
    c.revisar("el rango incluye desde y excluye hasta",
              [f["valor"] for f in horas], [15.0, 60.0, None])
    c.revisar("cada tramo conserva el número de lecturas",
              [f["muestras"] for f in horas], [2, 1, 0])
    c.revisar("las horas ausentes conservan su posición",
              [f["bucket"] for f in horas],
              ["2025-01-10 00:00", "2025-01-10 01:00", "2025-01-10 02:00"])
    c.revisar("media diaria ponderada por muestras, no por horas",
              logs.consultar_metricas(clave, desde, hasta,
                                      agrupacion="dia")[0]["valor"], 30.0)
    for operacion, esperado in (
        ("minimo", [10.0, 60.0, None]),
        ("maximo", [20.0, 60.0, None]),
        ("ultimo", [20.0, 60.0, None]),
        ("conteo", [2, 1, 0]),
    ):
        filas = logs.consultar_metricas(clave, desde, hasta,
                                        operacion=operacion)
        c.revisar(f"operación {operacion}",
                  [f["valor"] for f in filas], esperado)
    c.revisar("el resumen conserva mínimos y máximos reales",
              [(f["minimo"], f["maximo"]) for f in horas],
              [(10.0, 20.0), (60.0, 60.0), (None, None)])
    c.revisar("una serie inexistente no finge cero grados",
              [f["valor"] for f in logs.consultar_metricas(
                  "prueba.ausente", desde, hasta)], [None, None, None])
    c.revisar("contar muestras ausentes sí da cero",
              [f["valor"] for f in logs.consultar_metricas(
                  "prueba.ausente", desde, hasta, operacion="conteo")], [0, 0, 0])
    return c


def _eventos(logs) -> Caso:
    c = Caso("Métricas: conteos diarios y franjas horarias")
    categoria, accion = "prueba_analytics", "PRUEBA_ANALYTICS"
    _insertar_eventos(logs, [
        ("2025-02-02T23:59:59", categoria, accion),
        ("2025-02-03T00:00:00", categoria, accion),
        ("2025-02-03T06:00:00", categoria, "PRUEBA_OTRA"),
        ("2025-02-03T06:45:00", categoria, accion),
        ("2025-02-03T07:00:00", categoria, accion),
        ("2025-02-03T22:00:00", categoria, accion),
        ("2025-02-03T23:59:59", categoria, accion),
        ("2025-02-04T05:59:59", categoria, accion),
        ("2025-02-04T06:00:00", categoria, accion),
        ("2025-02-04T14:00:00", "otra_categoria", "OTRO_EVENTO"),
        ("2025-02-06T00:00:00", categoria, accion),
    ])
    desde, hasta = _ts("2025-02-03T00:00"), _ts("2025-02-06T00:00")
    diario = logs.consultar_eventos(desde, hasta, categorias=(categoria,))
    c.revisar("categoría suma todas sus acciones y rellena días vacíos",
              [f["valor"] for f in diario], [6, 2, 0])
    c.revisar("el filtro de una acción no incluye otras acciones",
              [f["valor"] for f in logs.consultar_eventos(
                  desde, hasta, acciones=(accion,))], [5, 2, 0])
    c.revisar("hora concreta: 06:00 incluida, 07:00 excluida",
              [f["valor"] for f in logs.consultar_eventos(
                  desde, hasta, categorias=(categoria,),
                  hora_desde="06:00", hora_hasta="07:00")], [2, 1, 0])
    c.revisar("franja nocturna cruza medianoche sin perder eventos",
              [f["valor"] for f in logs.consultar_eventos(
                  desde, hasta, categorias=(categoria,),
                  hora_desde="22:00", hora_hasta="06:00")], [3, 1, 0])
    horas = logs.consultar_eventos(desde, hasta, categorias=(categoria,),
                                  agrupacion="hora_dia")
    c.revisar("perfil horario devuelve las 24 horas", len(horas), 24)
    c.revisar("perfil horario reúne la misma hora de días distintos",
              {f["bucket"]: f["valor"] for f in horas if f["valor"]},
              {"00": 1, "05": 1, "06": 3, "07": 1, "22": 1, "23": 1})
    c.revisar("una acción sin sucesos muestra ceros",
              [f["valor"] for f in logs.consultar_eventos(
                  desde, hasta, acciones=("ACCION_INEXISTENTE",))], [0, 0, 0])
    c.revisar("sin fuente reconocida no se cuenta toda la casa",
              [f["valor"] for f in logs.consultar_eventos(desde, hasta)], [0, 0, 0])
    c.revisar("acciones y categorías combinadas cuentan la unión una sola vez",
              [f["valor"] for f in logs.consultar_eventos(
                  desde, hasta, acciones=(accion,), categorias=(categoria,))], [6, 2, 0])
    c.revisar("dos extremos horarios iguales representan las 24 horas",
              [f["valor"] for f in logs.consultar_eventos(
                  desde, hasta, categorias=(categoria,),
                  hora_desde="06:00", hora_hasta="06:00")], [6, 2, 0])
    hora_parcial = logs.consultar_eventos(
        desde, hasta, categorias=(categoria,), agrupacion="hora_dia",
        hora_desde="06:30", hora_hasta="07:15",
    )
    c.revisar("una franja parcial conserva solo las horas solapadas",
              [(f["bucket"], f["valor"]) for f in hora_parcial],
              [("06", 1), ("07", 1)])
    return c


def _intervalos(logs) -> Caso:
    c = Caso("Métricas: intervalo personalizado y protecciones")
    clave = "prueba.intervalo"
    for hora, valor in (("00:05", 5), ("01:29", 15),
                        ("01:30", 30), ("02:59", 50), ("03:00", 999)):
        logs.anotar(clave, valor, _ts(f"2025-01-11T{hora}"))
    desde, hasta = _ts("2025-01-11T00:00"), _ts("2025-01-11T03:00")
    filas = logs.consultar_metricas(clave, desde, hasta,
                                    agrupacion="intervalo", intervalo_minutos=90)
    c.revisar("intervalos de 90 minutos anclados a medianoche",
              [(f["bucket"], f["valor"]) for f in filas],
              [("2025-01-11 00:00", 10.0), ("2025-01-11 01:30", 40.0)])
    parcial = logs.consultar_metricas(
        clave, _ts("2025-01-11T00:10"), hasta,
        agrupacion="intervalo", intervalo_minutos=90,
    )
    c.revisar("un inicio parcial no filtra por el inicio del bucket",
              [f["valor"] for f in parcial], [15.0, 40.0])
    for nombre, argumentos in (
        ("rango invertido", {"desde": hasta, "hasta": desde}),
        ("rango vacío", {"desde": desde, "hasta": desde}),
        ("exceso de puntos", {"desde": _ts("2024-01-01T00:00"),
                              "hasta": _ts("2025-01-01T00:00"),
                              "agrupacion": "intervalo", "intervalo_minutos": 5}),
    ):
        rechazado = False
        try:
            logs.consultar_metricas(clave, **argumentos)
        except ValueError:
            rechazado = True
        c.cierto(f"se rechaza {nombre}", rechazado)
    c.revisar("un rango fuera de la franja no inventa un tramo vacío",
              logs.consultar_metricas(
                  clave, _ts("2025-01-11T14:30"), _ts("2025-01-11T14:45"),
                  hora_desde="14:00", hora_hasta="14:15"), [])
    return c


def _persistencia(store) -> Caso:
    c = Caso("Métricas: compatibilidad y personalización persistente")
    antiguos = [
        {"id": "legacy_linea", "titulo": "CPU", "forma": "linea",
         "medida": "serie:cpu.temp", "dias": 7, "color": "warning", "orden": 0},
        {"id": "legacy_horas", "titulo": "Aperturas", "forma": "barras_hora",
         "medida": "grupo:aperturas", "dias": 30, "color": "accent", "orden": 1},
        {"id": "legacy_dias", "titulo": "Diario", "forma": "barras_dia",
         "medida": "accion:PRUEBA", "dias": 1, "color": "purple", "orden": 2},
    ]
    store.ARCHIVO.write_text(json.dumps({"metricas_paneles": antiguos}),
                             encoding="utf-8")
    antes = store.ARCHIVO.read_bytes()
    paneles = store.list_paneles()
    c.revisar("los paneles antiguos conservan id, forma, medida y color",
              [[p[k] for k in ("id", "forma", "medida", "color")] for p in paneles],
              [[p[k] for k in ("id", "forma", "medida", "color")] for p in antiguos])
    c.revisar("la migración conserva la intención temporal de cada panel",
              [p["agrupacion"] for p in paneles], ["hora", "hora_dia", "dia"])
    c.revisar("mediciones antiguas promedian y eventos cuentan",
              [p["operacion"] for p in paneles], ["media", "conteo", "conteo"])
    c.revisar("leer fichas antiguas no escribe en el fichero",
              store.ARCHIVO.read_bytes(), antes)
    opciones = {
        "agrupacion": "intervalo", "intervalo_minutos": 90,
        "operacion": "maximo", "periodo": "personalizado",
        "desde": "2025-01-10T00:00", "hasta": "2025-01-12T00:00",
        "franja": True, "hora_desde": "22:00", "hora_hasta": "06:00",
        "ancho": "amplio",
    }
    nuevo = store.add_panel("  CPU nocturna  ", "donut", "serie:cpu.temp",
                             30, "warning", **opciones)
    guardado = next(p for p in store.list_paneles() if p["id"] == nuevo["id"])
    c.revisar("el título se limpia", guardado["titulo"], "CPU nocturna")
    c.revisar("se conservan todas las opciones al crear y releer",
              {k: guardado[k] for k in opciones}, opciones)
    modificado = store.update_panel(nuevo["id"], {
        "forma": "circular", "intervalo_minutos": 15, "operacion": "minimo",
        "ancho": "normal", "campo_inventado": "no guardar",
    })
    c.revisar("editar actualiza forma, operación, intervalo y tamaño",
              [modificado[k] for k in ("forma", "intervalo_minutos", "operacion", "ancho")],
              ["circular", 15, "minimo", "normal"])
    c.revisar("editar conserva las opciones no modificadas",
              [modificado[k] for k in ("desde", "hasta", "hora_desde", "hora_hasta")],
              [opciones[k] for k in ("desde", "hasta", "hora_desde", "hora_hasta")])
    c.revisar("campos ajenos al contrato no se persisten",
              "campo_inventado" in modificado, False)
    for forma in ("linea", "area", "barras", "donut", "circular"):
        panel = store.add_panel(forma, forma, "serie:cpu.temp")
        c.revisar(f"forma {forma} guardada", panel["forma"], forma)
    deshacer = importlib.import_module("noxuscmmd.domains.infra.deshacer")
    store.delete_panel(nuevo["id"])
    deshacer._reponer_panel({"panel": modificado})
    repuesto = [p for p in store.list_paneles() if p["titulo"] == "CPU nocturna"][0]
    c.revisar("deshacer repone también toda la personalización",
              {k: repuesto[k] for k in store.OPCIONES_PANEL},
              {k: modificado[k] for k in store.OPCIONES_PANEL})
    c.cierto("deshacer da una nueva identidad al panel",
              repuesto["id"] != nuevo["id"])
    return c



def _distribuciones(logs) -> Caso:
    c = Caso("Métricas: sectores circulares cuentan muestras")
    clave = "prueba.bandas"
    for hora, valor in (("00:00", 20), ("00:05", 30), ("00:10", 39),
                        ("01:00", 40), ("01:05", 50), ("02:00", 60)):
        logs.anotar(clave, valor, _ts(f"2025-01-12T{hora}"))
    desde, hasta = _ts("2025-01-12T00:00"), _ts("2025-01-12T02:00")
    c.revisar("cada límite pertenece a la banda que empieza en él",
              logs.distribucion_metricas(clave, desde, hasta, (30, 40, 50)),
              [1, 2, 1, 1])
    c.revisar("las bandas respetan también la franja horaria",
              logs.distribucion_metricas(clave, desde, hasta, (30, 40, 50),
                                        hora_desde="01:00", hora_hasta="02:00"),
              [0, 0, 1, 1])
    c.revisar("un histograma vacío no inventa sectores",
              logs.distribucion_metricas("prueba.ausente", desde, hasta, (30,)),
              [0, 0])
    c.revisar("sin límites una banda conserva todas las muestras",
              logs.distribucion_metricas(clave, desde, hasta, ()), [5])
    rechazado = False
    try:
        logs.distribucion_metricas(clave, desde, hasta, (40, 30))
    except ValueError:
        rechazado = True
    c.cierto("no se aceptan bandas desordenadas", rechazado)
    return c


def _cambio_horario(logs) -> Caso:
    c = Caso("Métricas: cambios de hora de Europe/Madrid")
    # El histórico usa hora local: las dos horas otoñales con el mismo nombre
    # se agrupan juntas, sin perder ninguna muestra ni crear una hora de marzo.
    try:
        with patch.dict(os.environ, {"TZ": "Europe/Madrid"}):
            time.tzset()
            for dia, siguiente, cantidad in (
                ("2025-03-30", "2025-03-31", 92),
                ("2025-10-26", "2025-10-27", 100),
            ):
                desde, hasta = _ts(f"{dia}T00:00"), _ts(f"{siguiente}T00:00")
                clave = f"prueba.cambio.{dia}"
                for instante in range(int(desde), int(hasta), 900):
                    logs.anotar(clave, 1, instante)
                diario = logs.consultar_metricas(clave, desde, hasta,
                                                 agrupacion="dia", operacion="conteo")
                c.revisar(f"{dia}: día completo conserva sus lecturas",
                          diario[0]["valor"], cantidad)
                horario = logs.consultar_metricas(clave, desde, hasta,
                                                  operacion="conteo")
                c.revisar(f"{dia}: agrupar por hora no pierde lecturas",
                          sum(f["valor"] for f in horario), cantidad)
                por_hora = {f["bucket"]: f["valor"] for f in horario}
                if dia == "2025-03-30":
                    c.revisar("primavera no inventa la hora que no existió",
                              f"{dia} 02:00" in por_hora, False)
                else:
                    c.revisar("otoño reúne las dos 02:00 con sus ocho lecturas",
                              por_hora.get(f"{dia} 02:00"), 8)
    finally:
        time.tzset()
    return c


def _estado_y_circulares(store, logs, modulo) -> Caso:
    c = Caso("Métricas: resumen y gráficas fieles al histórico")
    for fecha, valor in (
        ("2025-01-10T00:00", 10), ("2025-01-10T00:30", 20),
        ("2025-01-10T01:10", 60),
    ):
        logs.anotar("cpu.temp", valor, _ts(fecha))
    ficha = {
        "id": "prueba_pintar", "titulo": "CPU de pruebas", "forma": "area",
        "medida": "serie:cpu.temp", "agrupacion": "hora", "operacion": "media",
        "periodo": "personalizado", "desde": "2025-01-10T00:00",
        "hasta": "2025-01-10T03:00",
    }
    vista = SimpleNamespace(catalogo=[{"id": "serie:cpu.temp", "nombre": "CPU"}],
                           rango_global="panel")
    pintar = lambda panel: modulo.MetricasState._pintar(vista, panel)
    panel = pintar(ficha)
    c.revisar("la tarjeta muestra la media ponderada de todas las muestras",
              panel["valor_texto"], "30 °C")
    c.revisar("la tarjeta mantiene el mínimo, máximo y última lectura",
              [panel[k] for k in ("minimo_texto", "maximo_texto", "ultimo_texto")],
              ["10 °C", "60 °C", "60 °C"])
    c.revisar("la gráfica conserva el hueco de la última hora",
              [f["y"] for f in panel["datos"]], [15.0, 60.0, None])
    c.revisar("la gráfica declara grados para una temperatura",
              panel["unidad_grafica"], " °C")
    c.revisar("la última lectura del gráfico mantiene su fecha completa",
              panel["ultima_lectura_texto"], "10/01/2025 · 01:10:00")
    c.revisar("valor y unidad se pueden presentar sin repetir contenido",
              (panel["principal_numero"], panel["principal_unidad"]), ("30", " °C"))
    c.revisar("la fuente repetida se omite cuando ya es el título",
              pintar({**ficha, "titulo": "CPU"})["fuente_secundaria"], "")
    for clave, unidad in (
        ("servidor.temp", " °C"), ("temp.equipo_prueba", " °C"),
        ("servidor.cpu", " %"), ("servidor.ram", " %"),
        ("servidor.disco", " %"), ("equipos.en_linea", ""),
    ):
        c.revisar(f"unidad de {clave}", modulo._unidad_de_serie(clave), unidad)
    donut = pintar({**ficha, "forma": "donut"})
    c.revisar("anillo de temperatura cuenta muestras y no suma grados",
              sorted(f["y"] for f in donut["datos_circulares"]), [1, 2])
    c.revisar("la distribución conserva todas las muestras",
              sum(f["y"] for f in donut["datos_circulares"]), 3)
    c.revisar("cada muestra tiene el mismo peso en el porcentaje",
              sorted(f["porcentaje"] for f in donut["datos_circulares"]),
              [33.3, 66.7])
    c.revisar("sectores no usan grados como unidad del tamaño",
              donut["unidad_grafica"], "")
    conteo = pintar({**ficha, "operacion": "conteo"})
    c.revisar("contar lecturas no se etiqueta como temperatura",
              (conteo["valor_texto"], conteo["unidad_grafica"]), ("3", ""))
    ausente = pintar({**ficha, "medida": "serie:prueba.sin_datos"})
    c.revisar("una medición ausente tiene estado vacío y valor desconocido",
              (ausente["vacio"], ausente["valor_texto"]), (True, "—"))
    c.revisar("un rango inválido se explica sin romper el dashboard",
              bool(pintar({**ficha, "hasta": "2025-01-09T00:00"})["error"]), True)
    eventos = pintar({
        **ficha, "forma": "circular", "medida": "categoria:prueba_analytics",
        "agrupacion": "dia", "desde": "2025-02-03T00:00",
        "hasta": "2025-02-06T00:00",
    })
    c.revisar("circular de eventos conserva su total",
              (eventos["valor_texto"], sum(f["y"] for f in eventos["datos_circulares"])),
              ("8", 8))
    muchos = [{"x": str(i), "y": i} for i in range(1, 12)]
    sectores = modulo._agrupar_circulares(muchos)
    c.revisar("muchos tramos se limitan a ocho sectores", len(sectores), 8)
    c.revisar("Otros tramos conserva el total original",
              sum(f["y"] for f in sectores), 66)
    c.cierto("agrupar los sectores no modifica los datos de la serie",
              all("porcentaje" not in fila for fila in muchos))
    for operacion, esperado in (
        ("minimo", "10 °C"), ("maximo", "60 °C"), ("ultimo", "60 °C"),
    ):
        c.revisar(f"el indicador principal respeta el cálculo {operacion}",
                  pintar({**ficha, "operacion": operacion})["valor_texto"], esperado)
    for hora, valor in (("00:00", 1), ("00:30", 1), ("01:00", 1)):
        logs.anotar("equipo.prueba_constante", valor, _ts(f"2025-01-10T{hora}"))
    constante = pintar({**ficha, "forma": "donut",
                        "medida": "serie:equipo.prueba_constante"})
    c.revisar("un equipo siempre disponible muestra una categoría legible",
              [(f["x"], f["y"]) for f in constante["datos_circulares"]],
              [("En línea", 3)])
    for fecha, valor in (
        ("2025-01-20T22:00", 90), ("2025-01-21T06:00", 40),
    ):
        logs.anotar("temp.prueba_ultima", valor, _ts(fecha))
    perfil = pintar({
        **ficha, "medida": "serie:temp.prueba_ultima", "agrupacion": "hora_dia",
        "operacion": "ultimo", "desde": "2025-01-20T00:00",
        "hasta": "2025-01-22T00:00",
    })
    c.revisar("el último valor sigue la fecha y no el orden del perfil horario",
              perfil["valor_texto"], "40 °C")
    return c


def _rangos_y_editor(store, modulo) -> Caso:
    c = Caso("Métricas: períodos, validación y vista previa")
    ahora = _ts("2025-02-10T12:00")
    desde, hasta, _ = modulo._rango_panel({"dias": 7}, ahora=ahora)
    c.revisar("el período relativo termina en el momento de la consulta",
              (hasta, hasta - desde), (ahora, 7 * 86400))
    ficha = {
        "titulo": "Editor de pruebas", "forma": "donut", "medida": "serie:cpu.temp",
        "dias": 30, "color": "purple", "agrupacion": "intervalo",
        "intervalo_minutos": 90, "operacion": "maximo", "periodo": "personalizado",
        "desde": "2025-01-10T00:00", "hasta": "2025-01-10T03:00",
        "franja": True, "hora_desde": "22:00", "hora_hasta": "06:00",
        "ancho": "amplio",
    }
    inicio, final, _ = modulo._rango_panel(ficha, ahora=ahora)
    c.revisar("el período personalizado respeta los dos extremos",
              (inicio, final), (_ts(ficha["desde"]), _ts(ficha["hasta"])))
    global_desde, global_hasta, _ = modulo._rango_panel(ficha, "1", ahora=ahora)
    c.revisar("el rango global es temporal y no cambia la ficha guardada",
              (global_hasta - global_desde, ficha["periodo"], ficha["dias"]),
              (86400, "personalizado", 30))
    estado = modulo.MetricasState(_reflex_internal_init=True)
    estado.catalogo = [{"id": "serie:cpu.temp", "nombre": "CPU"}]
    estado.rango_global = "1"
    estado._cargar_editor(store.normalizar_panel(ficha))
    c.revisar("la vista previa usa las fechas del editor aunque haya rango global",
              estado.preview["muestras_texto"], "3 muestras")
    c.revisar("una franja nocturna es válida en el editor",
              estado._validar_editor(), "")
    for campo, invalido in (
        ("ed_intervalo_minutos", 4), ("ed_hasta", "2025-01-09T00:00"),
        ("ed_hora_desde", "25:00"), ("ed_medida", ""),
    ):
        original = getattr(estado, campo)
        setattr(estado, campo, invalido)
        c.cierto(f"se explica el valor inválido de {campo}",
                  estado._validar_editor())
        setattr(estado, campo, original)
    estado.ed_medida = "accion:PRUEBA_ANALYTICS"
    estado.ed_operacion = "media"
    c.revisar("al guardar eventos el cálculo es siempre conteo",
              estado._ficha_editor()["operacion"], "conteo")
    estado.ed_medida = "serie:cpu.temp"
    estado.ed_operacion = "maximo"
    estado.set_ed_titulo("Nuevo título")
    c.cierto("cambiar un ajuste marca la vista previa como pendiente",
              estado.preview_desactualizada)
    estado.actualizar_preview()
    c.revisar("actualizar la vista previa aplica y confirma los ajustes",
              (estado.preview_desactualizada, estado.preview["titulo"]),
              (False, "Nuevo título"))
    estado.alternar_preview_movil()
    c.cierto("la vista previa móvil se puede abrir bajo demanda",
              estado.preview_movil_abierta)
    estado._cargar_editor(store.normalizar_panel(ficha))
    c.revisar("abrir otro panel no impone una vista previa móvil expandida",
              estado.preview_movil_abierta, False)
    return c


def _acciones_del_editor(store, modulo) -> Caso:
    c = Caso("Métricas: permisos, guardado y duplicado desde el editor")
    estado = modulo.MetricasState(_reflex_internal_init=True)
    estado.catalogo = [{"id": "serie:cpu.temp", "nombre": "CPU"}]
    ficha = store.normalizar_panel({
        "titulo": "Guardado desde el editor", "forma": "circular",
        "medida": "serie:cpu.temp", "agrupacion": "intervalo",
        "intervalo_minutos": 30, "operacion": "minimo", "periodo": "personalizado",
        "desde": "2025-01-10T00:00", "hasta": "2025-01-10T03:00",
        "franja": True, "hora_desde": "22:00", "hora_hasta": "06:00",
        "ancho": "amplio",
    })
    estado._cargar_editor(ficha)
    estado.panel_en_edicion = "nuevo"
    antes = store.ARCHIVO.read_bytes()
    with patch.object(modulo.permisos, "denegar", AsyncMock(return_value="denegado")), \
            patch.object(modulo.audit, "registrar", AsyncMock()) as registrar:
        for metodo, argumentos in (
            ("guardar_panel", ()), ("duplicar_panel", ("legacy_linea",)),
            ("borrar_panel", ("legacy_linea",)), ("mover_panel", ("legacy_linea", 1)),
            ("crear_dashboard_base", ()), ("alternar_equipo", ("equipo_prueba",)),
        ):
            resultado = asyncio.run(getattr(estado, metodo)(*argumentos))
            c.revisar(f"{metodo} requiere permiso de ajustes", resultado, "denegado")
        c.revisar("denegar no produce una auditoría de éxito", registrar.await_count, 0)
    c.revisar("denegar todas las mutaciones deja la configuración intacta",
              store.ARCHIVO.read_bytes(), antes)
    with patch.object(modulo.permisos, "denegar", AsyncMock(return_value=None)), \
            patch.object(modulo.audit, "registrar", AsyncMock()):
        ids_antes = {p["id"] for p in store.list_paneles()}
        asyncio.run(estado.guardar_panel())
        guardado = next(p for p in store.list_paneles() if p["id"] not in ids_antes)
        c.revisar("guardar desde el editor conserva toda la personalización",
                  {k: guardado[k] for k in store.OPCIONES_PANEL},
                  {k: ficha[k] for k in store.OPCIONES_PANEL})
        c.revisar("guardar correctamente cierra el editor", estado.panel_en_edicion, "")
        asyncio.run(estado.duplicar_panel(guardado["id"]))
        copia = next(p for p in store.list_paneles()
                     if p["titulo"] == "Guardado desde el editor · copia")
        c.revisar("duplicar conserva opciones y crea otra identidad",
                  ({k: copia[k] for k in store.OPCIONES_PANEL},
                   copia["id"] != guardado["id"]),
                  ({k: guardado[k] for k in store.OPCIONES_PANEL}, True))
        estado.editar_panel(guardado["id"])
        estado.ed_hasta = "2025-01-09T00:00"
        antes_error = store.ARCHIVO.read_bytes()
        asyncio.run(estado.guardar_panel())
        c.cierto("un rango inválido mantiene el error visible", estado.ed_error)
        c.revisar("el formulario inválido no modifica el panel guardado",
                  store.ARCHIVO.read_bytes(), antes_error)
        estado.editar_panel("legacy_horas")
        c.revisar("las barras heredadas abren una forma visible en el editor",
                  (estado.ed_forma, estado.ed_agrupacion), ("barras", "hora_dia"))
        asyncio.run(estado.guardar_panel())
        heredado = next(p for p in store.list_paneles() if p["id"] == "legacy_horas")
        c.revisar("guardar un panel heredado mantiene el perfil por hora del día",
                  (heredado["forma"], heredado["agrupacion"]), ("barras", "hora_dia"))
        estado.catalogo = [
            {"id": "serie:servidor.temp", "nombre": "Servidor"},
            {"id": "serie:cpu.temp", "nombre": "CPU"},
            {"id": "grupo:aperturas", "nombre": "Aperturas"},
        ]
        asyncio.run(estado.crear_dashboard_base())
        ids_base = {p["id"] for p in store.list_paneles()}
        asyncio.run(estado.crear_dashboard_base())
        c.revisar("el dashboard base no duplica paneles al repetirlo",
                  {p["id"] for p in store.list_paneles()}, ids_base)
    return c



def _ultimas_lecturas(logs) -> Caso:
    c = Caso("Métricas: última lectura determinista y sin valores inventados")
    instante = _ts("2025-04-15T12:00")
    clave = "prueba.ultima"
    logs.anotar(clave, 10, instante)
    logs.anotar(clave, 20, instante)
    logs.anotar(clave, 99, instante - 60)
    obtenidas = logs.ultimas_metricas((clave, clave, "prueba.desconocida"))
    c.revisar("la lectura más reciente desempata por orden de inserción",
              obtenidas.get(clave), {"valor": 20.0, "ts": instante})
    c.revisar("las claves repetidas no duplican indicadores",
              list(obtenidas), [clave])
    c.revisar("las fuentes desconocidas no aparentan tener una lectura",
              "prueba.desconocida" in obtenidas, False)
    # SQLite admite infinitos y texto en una columna REAL. Una lectura nueva
    # corrupta no debe hacer pasar la muestra anterior por una lectura actual.
    with sqlite3.connect(logs.RUTA) as conexion:
        conexion.executemany("INSERT INTO metricas(ts,clave,valor) VALUES(?,?,?)", [
            (instante, "prueba.no_finita", 25),
            (instante + 60, "prueba.no_finita", float("inf")),
            (instante, "prueba.no_numerica", 25),
            (instante + 60, "prueba.no_numerica", "desconocido"),
        ])
    c.revisar("una última lectura infinita no rescata una anterior",
              logs.ultimas_metricas(("prueba.no_finita",)), {})
    c.revisar("una última lectura no numérica no rescata una anterior",
              logs.ultimas_metricas(("prueba.no_numerica",)), {})
    with patch.object(logs, "_conectar", side_effect=AssertionError("Consulta innecesaria")):
        c.revisar("sin fuentes no se abre la base de datos",
                  logs.ultimas_metricas(()), {})
    return c



def _indicadores_reales(modulo) -> Caso:
    c = Caso("Métricas: indicadores relevantes, fechados y sin falsa frescura")
    ahora = _ts("2025-04-15T12:00:00")
    ultimas = {
        "servidor.temp": {"valor": 52.3, "ts": ahora - 60},
        "servidor.cpu": {"valor": 14, "ts": ahora - 1201},
        "servidor.ram": {"valor": 0, "ts": ahora},
        "servidor.disco": {"valor": 82, "ts": ahora + 61},
        "cpu.temp": {"valor": 41, "ts": ahora},
        "equipos.en_linea": {"valor": 3, "ts": ahora},
    }
    tarjetas = modulo._indicadores_de_salud(ultimas, [], ahora=ahora)
    c.revisar("el resumen muestra como máximo cuatro fuentes prioritarias",
              [t["id"] for t in tarjetas],
              ["servidor.temp", "servidor.cpu", "servidor.ram", "servidor.disco"])
    por_id = {t["id"]: t for t in tarjetas}
    c.revisar("una temperatura muestra su última lectura y unidad real",
              (por_id["servidor.temp"]["valor"], por_id["servidor.temp"]["unidad"]),
              ("52,3", "°C"))
    c.revisar("la fecha incluye día, año y segundo de la lectura original",
              por_id["servidor.temp"]["detalle"], "15/04/2025 · 11:59:00")
    c.revisar("cero sigue siendo una lectura disponible, no un dato ausente",
              (por_id["servidor.ram"]["valor"], por_id["servidor.ram"]["disponible"],
               por_id["servidor.ram"]["porcentaje"]), ("0", True, 0))
    c.revisar("las lecturas antiguas no se presentan como actuales",
              (por_id["servidor.cpu"]["obsoleto"], por_id["servidor.cpu"]["valor"]),
              (True, "14"))
    c.revisar("un reloj adelantado se avisa sin inventar una edad negativa",
              (por_id["servidor.disco"]["obsoleto"],
               por_id["servidor.disco"]["lectura_corta"]), (True, "Revisar reloj"))
    for diferencia, esperado in ((-1200, False), (-1201, True), (60, False), (61, True)):
        tarjeta = modulo._indicadores_de_salud({
            "servidor.temp": {"valor": 35, "ts": ahora + diferencia},
        }, [], ahora=ahora)[0]
        c.revisar(f"frescura con diferencia de {diferencia} segundos",
                  tarjeta["obsoleto"], esperado)
    catalogo = [{"id": "serie:servidor.temp"}, {"id": "serie:servidor.cpu"}]
    faltantes = modulo._indicadores_de_salud({}, catalogo, ahora=ahora)
    c.revisar("una fuente conocida sin muestras dice que falta el dato",
              [(t["valor"], t["disponible"], t["detalle"]) for t in faltantes],
              [("—", False, "Sin muestras"), ("—", False, "Sin muestras")])
    c.revisar("sin fuentes conocidas no se inventan cuatro indicadores",
              modulo._indicadores_de_salud({}, [], ahora=ahora), [])
    alternativas = modulo._indicadores_de_salud({
        "cpu.temp": {"valor": 42, "ts": ahora},
        "equipos.en_linea": {"valor": 2, "ts": ahora},
    }, [], ahora=ahora)
    c.revisar("las alternativas disponibles ocupan solo los huecos necesarios",
              [t["id"] for t in alternativas], ["cpu.temp", "equipos.en_linea"])
    invalida = modulo._indicadores_de_salud({
        "servidor.temp": {"valor": float("inf"), "ts": ahora},
        "servidor.cpu": {"valor": 35, "ts": float("inf")},
    }, catalogo, ahora=ahora)
    c.revisar("valores o fechas inválidos no se muestran como indicadores reales",
              [(t["valor"], t["disponible"]) for t in invalida],
              [("—", False), ("—", False)])
    excesivo = modulo._indicadores_de_salud({
        "servidor.cpu": {"valor": 103, "ts": ahora},
    }, [], ahora=ahora)[0]
    c.revisar("un porcentaje fuera de rango no se maquilla para dibujar la barra",
              (excesivo["valor"], excesivo["porcentaje"]), ("103", None))
    c.revisar("un timestamp no representable no rompe la tarjeta",
              modulo._texto_fecha_lectura(1e308), "")
    return c


def _categorias_y_revelado(store, modulo) -> Caso:
    c = Caso("Métricas: categorías y revelado progresivo sin alterar paneles")
    medidas = [
        "serie:cpu.temp", "serie:servidor.cpu", "serie:equipo.pc",
        "accion:PRUEBA_ANALYTICS", "serie:temp.gpu", "serie:servidor.ram",
        "serie:equipos.en_linea", "categoria:prueba_analytics", "serie:servidor.temp",
        "serie:temp.extra1", "serie:temp.extra2", "serie:temp.extra3",
    ]
    categorias = [
        "temperatura", "recursos", "disponibilidad", "actividad", "temperatura",
        "recursos", "disponibilidad", "actividad", "temperatura",
        "temperatura", "temperatura", "temperatura",
    ]
    c.revisar("cada familia de medidas tiene una categoría útil",
              [modulo._categoria_de_medida(m) for m in medidas], categorias)
    # El orden guardado difiere a propósito del orden físico en el JSON.
    ordenes = [9, 1, 7, 3, 0, 8, 4, 6, 2, 5, 11, 10]
    fichas = [
        {"id": f"categoria_{i}", "titulo": f"Panel {i}", "medida": medida,
         "forma": "linea", "orden": orden, "periodo": "personalizado",
         "desde": "2025-01-10T00:00", "hasta": "2025-01-10T03:00"}
        for i, (medida, orden) in enumerate(zip(medidas, ordenes))
    ]
    store.ARCHIVO.write_text(json.dumps({"metricas_paneles": fichas}), encoding="utf-8")
    antes = store.ARCHIVO.read_bytes()
    orden_guardado = [f["id"] for f in sorted(fichas, key=lambda f: f["orden"])]
    estado = modulo.MetricasState(_reflex_internal_init=True)
    estado._recargar()
    c.revisar("cargar el dashboard conserva todos los paneles y su orden",
              [p["id"] for p in estado.paneles], orden_guardado)
    c.revisar("la primera vista presenta solo cuatro paneles",
              [p["id"] for p in estado.paneles_visibles], orden_guardado[:4])
    c.cierto("la primera vista permite descubrir el resto", estado.hay_mas_paneles)
    estado.mostrar_mas_paneles()
    c.revisar("mostrar más amplía de cuatro en cuatro",
              [p["id"] for p in estado.paneles_visibles], orden_guardado[:8])
    estado.mostrar_mas_paneles()
    c.revisar("revelar todo no cambia ni duplica paneles",
              [p["id"] for p in estado.paneles_visibles], orden_guardado)
    c.revisar("al llegar al final desaparece la opción de ampliar",
              estado.hay_mas_paneles, False)
    conteos = {f["id"]: f["cuantos"] for f in estado.categorias_paneles}
    c.revisar("los contadores incluyen también los paneles aún ocultos",
              conteos, {"todos": 12, "temperatura": 6, "recursos": 2,
                        "disponibilidad": 2, "actividad": 2})
    estado.set_filtro_paneles("temperatura")
    esperados = [f["id"] for f in sorted(fichas, key=lambda f: f["orden"])
                 if categorias[int(f["id"].split("_")[-1])] == "temperatura"]
    c.revisar("cambiar de categoría reinicia la vista breve conservando el orden",
              [p["id"] for p in estado.paneles_visibles], esperados[:4])
    c.revisar("el filtro mantiene el total real de paneles de su categoría",
              estado.paneles_filtrados_count, 6)
    estado.mostrar_mas_paneles()
    c.revisar("se pueden recuperar todos los paneles de una categoría",
              [p["id"] for p in estado.paneles_visibles], esperados)
    c.revisar("filtrar no quita paneles del conjunto original",
              [p["id"] for p in estado.paneles], orden_guardado)
    estado.set_filtro_paneles("todos")
    estado.alternar_edicion()
    c.revisar("en edición todos los paneles están disponibles para ordenar",
              [p["id"] for p in estado.paneles_visibles], orden_guardado)
    c.revisar("en edición no hay un botón de ampliar innecesario",
              estado.hay_mas_paneles, False)
    estado.alternar_edicion()
    c.revisar("salir de edición recupera la lectura breve",
              [p["id"] for p in estado.paneles_visibles], orden_guardado[:4])
    estado.set_filtro_paneles("categoria_desconocida")
    c.revisar("un filtro desconocido no oculta el dashboard",
              estado.filtro_paneles, "todos")
    c.revisar("filtrar, mostrar más y editar no escriben preferencias en disco",
              store.ARCHIVO.read_bytes(), antes)
    estado.paneles = []
    c.revisar("no aparecen filtros de categorías sin paneles",
              [f["id"] for f in estado.categorias_paneles], ["todos"])
    return c


def ejecutar() -> list[Caso]:
    with _almacenes_temporales() as (store, logs):
        modulo = importlib.import_module("noxuscmmd.domains.infra.metricas_state")
        return [
            _series(logs), _eventos(logs), _intervalos(logs), _persistencia(store),
            _distribuciones(logs), _cambio_horario(logs), _ultimas_lecturas(logs),
            _estado_y_circulares(store, logs, modulo), _rangos_y_editor(store, modulo),
            _acciones_del_editor(store, modulo), _indicadores_reales(modulo),
            _categorias_y_revelado(store, modulo),
        ]


