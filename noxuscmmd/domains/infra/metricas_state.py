"""Analytics configurable de la casa: consultas, preferencias y presentación de datos.

Las series representan muestras reales; los eventos se cuentan. Las vistas
circulares muestran distribuciones de muestras o eventos, nunca sumas de
temperaturas ni puntuaciones de salud inventadas.
"""
import math
import sqlite3
import time
from datetime import datetime, timedelta

import reflex as rx

from . import metricas
from .deshacer import DeshacerState
from ..auth import permisos
from ..nodes import store as nodes_store
from ..security import audit, logs, logs_store

DIAS_POSIBLES = (1, 7, 30, 90, 365)
GRUPOS = {
    "aperturas": ("Aperturas (todas las formas)", logs.ACCIONES_APERTURA),
    "armados": ("Armados y desarmados",
                ("ARMADO", "DESARMADO", "ARMADO_GRUPO", "DESARMADO_GRUPO")),
    "alarmas": ("Alarmas disparadas",
                ("GRUPO_ALERTA", "ALARMA_DISPARADA", "PUERTA_ABIERTA_ARMADA")),
}
_ETIQUETAS_CATEGORIA = {cid: etiqueta for cid, etiqueta, _ in logs.CATEGORIAS}
_FORMAS = {
    "linea": "Línea", "area": "Área", "barras": "Barras",
    "donut": "Anillo", "circular": "Circular",
    "barras_dia": "Barras", "barras_hora": "Barras",
}
_AGRUPACIONES = {
    "dia": "Por día", "hora": "Por hora",
    "hora_dia": "Hora del día", "intervalo": "Intervalo personalizado",
}
_OPERACIONES = {
    "media": "Media", "minimo": "Mínimo", "maximo": "Máximo",
    "ultimo": "Última lectura", "conteo": "Número de muestras",
}
_CATEGORIAS_PANEL = {
    "todos": "Todos", "temperatura": "Temperatura", "recursos": "Recursos",
    "actividad": "Actividad", "disponibilidad": "Disponibilidad",
}
_INDICADORES_SALUD = (
    (metricas.SERVIDOR_TEMP, "Temperatura del servidor", "thermometer", "accent", "Temperatura"),
    (metricas.SERVIDOR_CPU, "CPU del servidor", "cpu", "purple", "CPU"),
    (metricas.SERVIDOR_RAM, "Memoria RAM", "memory-stick", "warning", "Memoria RAM"),
    (metricas.SERVIDOR_DISCO, "Disco del servidor", "hard-drive", "success", "Disco"),
    (metricas.TEMP_CPU, "Temperatura Raspberry", "thermometer", "accent", "Temp. Raspberry"),
    (metricas.EQUIPOS_EN_LINEA, "Equipos en línea", "network", "success", "En línea"),
)
_CAMPOS_PANEL = (
    "titulo", "forma", "medida", "dias", "color", "agrupacion",
    "intervalo_minutos", "operacion", "periodo", "desde", "hasta",
    "franja", "hora_desde", "hora_hasta", "ancho",
)


def _numero(valor: float | int | None, unidad: str = "") -> str:
    if valor is None or not math.isfinite(float(valor)):
        return "—"
    if float(valor).is_integer():
        texto = f"{int(valor):,}".replace(",", ".")
    else:
        texto = f"{valor:,.1f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{texto}{unidad}"


def _unidad_de_serie(clave: str) -> str:
    if clave in (metricas.TEMP_CPU, metricas.SERVIDOR_TEMP) or clave.startswith(
            metricas.PREFIJO_TEMP_EQUIPO):
        return " °C"
    if clave in (metricas.SERVIDOR_CPU, metricas.SERVIDOR_RAM, metricas.SERVIDOR_DISCO):
        return " %"
    return ""


def _nombre_de_serie(clave: str, equipos: dict[str, str]) -> str:
    fijos = {
        metricas.TEMP_CPU: "Temperatura de la Raspberry",
        metricas.EQUIPOS_EN_LINEA: "Equipos en línea",
        metricas.EQUIPOS_TOTAL: "Equipos dados de alta",
        metricas.SERVIDOR_TEMP: "Servidor: temperatura",
        metricas.SERVIDOR_CPU: "Servidor: uso de CPU",
        metricas.SERVIDOR_RAM: "Servidor: memoria usada",
        metricas.SERVIDOR_DISCO: "Servidor: disco ocupado",
    }
    if clave in fijos:
        return fijos[clave]
    if clave.startswith(metricas.PREFIJO_TEMP_EQUIPO):
        host_id = clave[len(metricas.PREFIJO_TEMP_EQUIPO):]
        return f"Temperatura: {equipos.get(host_id, host_id)}"
    if clave.startswith(metricas.PREFIJO_EQUIPO):
        host_id = clave[len(metricas.PREFIJO_EQUIPO):]
        return f"Equipo: {equipos.get(host_id, host_id)}"
    return clave


def _rango_panel(panel: dict, rango_global: str = "panel",
                 ahora: float | None = None) -> tuple[float, float, str]:
    """Un único intervalo [desde, hasta), en hora local del servidor."""
    hasta = time.time() if ahora is None else ahora
    if rango_global in ("1", "7", "30", "90"):
        dias = int(rango_global)
        return hasta - dias * 86400, hasta, f"Últimos {dias} días · vista global"
    if panel.get("periodo") == "personalizado":
        try:
            inicio = datetime.fromisoformat(panel.get("desde", ""))
            final = datetime.fromisoformat(panel.get("hasta", ""))
        except (ValueError, TypeError):
            raise ValueError("Completa las fechas de inicio y fin del período.") from None
        desde, hasta = inicio.timestamp(), final.timestamp()
        if desde >= hasta:
            raise ValueError("La fecha de fin debe ser posterior a la de inicio.")
        return desde, hasta, f"{inicio:%d/%m/%y %H:%M} — {final:%d/%m/%y %H:%M}"
    dias = int(panel.get("dias", 7))
    if not 1 <= dias <= 365:
        raise ValueError("Elige un período entre 1 y 365 días.")
    return hasta - dias * 86400, hasta, "Últimas 24 horas" if dias == 1 else f"Últimos {dias} días"


def _etiqueta_bucket(bucket: str, agrupacion: str) -> str:
    try:
        if agrupacion == "hora_dia":
            return f"{int(bucket):02d}:00"
        fecha = datetime.fromisoformat(bucket)
        if agrupacion == "dia":
            return fecha.strftime("%d/%m")
        return fecha.strftime("%d/%m %H:%M")
    except (ValueError, TypeError):
        return str(bucket)


def _agrupar_circulares(datos: list[dict]) -> list[dict]:
    """Como máximo ocho sectores, conservando el total en «Otros tramos»."""
    positivos = sorted((dict(d) for d in datos if d["y"] and d["y"] > 0),
                       key=lambda d: d["y"], reverse=True)
    if len(positivos) > 8:
        positivos = positivos[:7] + [
            {"x": "Otros tramos", "y": sum(d["y"] for d in positivos[7:])}]
    total = sum(d["y"] for d in positivos)
    return [
        {**d, "porcentaje": round(100 * d["y"] / total, 1),
         "porcentaje_texto": f"{100 * d['y'] / total:.1f}".replace(".", ",") + " %",
         "color_index": i}
        for i, d in enumerate(positivos)
    ] if total else []


def _distribucion_serie(clave: str, desde: float, hasta: float, minimo: float,
                        maximo: float, muestras: int, horario: dict) -> list[dict]:
    """Bandas de valor: el tamaño del sector es la cantidad de muestras."""
    if minimo == maximo:
        etiqueta = _numero(minimo, _unidad_de_serie(clave))
        if clave.startswith(metricas.PREFIJO_EQUIPO):
            etiqueta = "En línea" if minimo >= 0.5 else "Sin conexión"
        return _agrupar_circulares([{"x": etiqueta, "y": muestras}])
    unidad = _unidad_de_serie(clave)
    if clave.startswith(metricas.PREFIJO_EQUIPO):
        limites = (0.5,)
        etiquetas = ["Sin conexión", "En línea"]
    else:
        if unidad == " °C":
            limites = (30.0, 40.0, 50.0, 60.0, 70.0)
        elif unidad == " %":
            limites = (25.0, 50.0, 75.0)
        else:
            amplitud = (maximo - minimo) / 5
            limites = tuple(minimo + amplitud * i for i in range(1, 5))
        etiquetas = (
            [f"< {_numero(limites[0], unidad)}"]
            + [f"{_numero(a)} – < {_numero(b, unidad)}"
               for a, b in zip(limites, limites[1:])]
            + [f"≥ {_numero(limites[-1], unidad)}"]
        )
    conteos = logs_store.distribucion_metricas(
        clave, desde, hasta, limites, **horario)
    return _agrupar_circulares([
        {"x": etiqueta, "y": cuenta}
        for etiqueta, cuenta in zip(etiquetas, conteos)
    ])



def _categoria_de_medida(medida: str) -> str:
    clase, _, clave = medida.partition(":")
    if clase != "serie":
        return "actividad"
    if clave in (metricas.TEMP_CPU, metricas.SERVIDOR_TEMP) or clave.startswith(
            metricas.PREFIJO_TEMP_EQUIPO):
        return "temperatura"
    if clave.startswith((metricas.PREFIJO_EQUIPO, "equipos.")):
        return "disponibilidad"
    return "recursos"


def _texto_fecha_lectura(timestamp: float | int | None) -> str:
    if timestamp is None:
        return ""
    try:
        return datetime.fromtimestamp(timestamp).strftime("%d/%m/%Y · %H:%M:%S")
    except (ValueError, TypeError, OverflowError, OSError):
        return ""


def _indicadores_de_salud(ultimas: dict, catalogo: list[dict],
                          ahora: float | None = None) -> list[dict]:
    """Últimas lecturas, independientes de los filtros del tablero.

    Solo se ofrecen fuentes presentes. Las alternativas llenan huecos sin
    sustituir una lectura antigua por una apariencia de frescura.
    """
    ahora = time.time() if ahora is None else ahora
    conocidas = {c["id"].removeprefix("serie:") for c in catalogo
                 if c["id"].startswith("serie:")}
    validas = {}
    for clave, lectura in ultimas.items():
        try:
            valor, ts = float(lectura["valor"]), float(lectura["ts"])
            if math.isfinite(valor) and math.isfinite(ts) and _texto_fecha_lectura(ts):
                validas[clave] = {"valor": valor, "ts": ts}
        except (ValueError, TypeError, KeyError):
            continue
    candidatas = [f for f in _INDICADORES_SALUD if f[0] in validas]
    candidatas += [f for f in _INDICADORES_SALUD
                   if f[0] not in validas and f[0] in conocidas]
    salida = []
    for clave, label, icono, color, label_corto in candidatas[:4]:
        lectura = validas.get(clave)
        unidad = _unidad_de_serie(clave).strip()
        disponible = lectura is not None
        item = {
            "id": clave, "label": label, "label_corto": label_corto, "valor": "—", "unidad": unidad,
            "detalle": "Sin muestras", "lectura_corta": "Sin muestras",
            "icono": icono, "color": color, "obsoleto": False,
            "disponible": disponible, "porcentaje": None,
        }
        if disponible:
            valor, ts = lectura["valor"], lectura["ts"]
            edad = max(0, ahora - ts)
            reloj_futuro = ts > ahora + 60
            item.update(
                valor=_numero(valor), detalle=_texto_fecha_lectura(ts),
                obsoleto=edad > 20 * 60 or reloj_futuro,
                lectura_corta=f"Registrada {datetime.fromtimestamp(ts):%H:%M}",
                porcentaje=valor if unidad == "%" and 0 <= valor <= 100 else None,
            )
            if reloj_futuro:
                item["lectura_corta"] = "Revisar reloj"
                item["detalle"] += " · Revisar reloj"
            elif edad >= 86400:
                dias = int(edad // 86400)
                item["lectura_corta"] = f"Hace {dias} {'día' if dias == 1 else 'días'}"
            elif edad >= 3600:
                item["lectura_corta"] = f"Hace {int(edad // 3600)} h"
            elif item["obsoleto"]:
                item["lectura_corta"] = f"Hace {int(edad // 60)} min"
        salida.append(item)
    return salida


class MetricasState(rx.State):
    paneles: list[dict] = []
    catalogo: list[dict] = []
    equipos: list[dict] = []
    indicadores_salud: list[dict] = []
    filtro_paneles: str = "todos"
    limite_paneles: int = 4
    editando: bool = False
    rango_global: str = "panel"
    ultima_actualizacion: str = ""
    panel_en_edicion: str = ""
    ed_titulo: str = ""
    ed_medida: str = ""
    ed_forma: str = "area"
    ed_dias: int = 7
    ed_color: str = "accent"
    ed_agrupacion: str = "hora"
    ed_intervalo_minutos: int = 60
    ed_operacion: str = "media"
    ed_periodo: str = "relativo"
    ed_desde: str = ""
    ed_hasta: str = ""
    ed_franja: bool = False
    ed_hora_desde: str = "00:00"
    ed_hora_hasta: str = "00:00"
    ed_ancho: str = "normal"
    ed_error: str = ""
    preview: dict = {}
    preview_desactualizada: bool = False
    preview_movil_abierta: bool = False

    @rx.event
    def on_load(self):
        self._recargar()

    @rx.event
    def actualizar(self):
        self._recargar()

    @rx.event
    def set_rango_global(self, valor: str):
        if valor in ("panel", "1", "7", "30", "90"):
            self.rango_global = valor
            self._recargar()

    @rx.event
    def set_filtro_paneles(self, valor: str):
        if valor in _CATEGORIAS_PANEL:
            self.filtro_paneles = valor
            self.limite_paneles = 4

    @rx.event
    def mostrar_mas_paneles(self):
        self.limite_paneles += 4

    @rx.event
    def alternar_edicion(self):
        self.editando = not self.editando

    def _recargar(self) -> None:
        self.equipos = [
            {"id": h["id"], "nombre": h.get("name") or h["id"],
             "en_metricas": bool(h.get("en_metricas")),
             "estado": "guardando" if h.get("en_metricas") else "sin guardar"}
            for h in sorted(nodes_store.read_all()["hosts"],
                            key=lambda h: h.get("order", 0))
        ]
        self.catalogo = self._construir_catalogo()
        self.paneles = [self._pintar(p) for p in nodes_store.list_paneles()]
        if self.filtro_paneles != "todos" and not any(
                _categoria_de_medida(p["medida"]) == self.filtro_paneles
                for p in self.paneles):
            self.filtro_paneles = "todos"
            self.limite_paneles = 4
        try:
            ultimas = logs_store.ultimas_metricas(
                tuple(clave for clave, *_ in _INDICADORES_SALUD))
        except (sqlite3.Error, OSError):
            ultimas = {}
        self.indicadores_salud = _indicadores_de_salud(ultimas, self.catalogo)
        self.ultima_actualizacion = datetime.now().strftime("%H:%M")

    def _construir_catalogo(self) -> list[dict]:
        nombres = {h["id"]: h["nombre"] for h in self.equipos}
        salida = [
            {"id": f"serie:{clave}", "nombre": _nombre_de_serie(clave, nombres),
             "familia": "Series muestreadas", "forma_natural": "area",
             "detalle": "una muestra cada 5 min"}
            for clave in logs_store.claves_de_metricas()
        ]
        salida.extend(
            {"id": f"grupo:{nombre}", "nombre": etiqueta,
             "familia": "Grupos de eventos", "forma_natural": "barras",
             "detalle": "varias acciones juntas"}
            for nombre, (etiqueta, _) in GRUPOS.items()
        )
        salida.extend(
            {"id": f"categoria:{f['categoria']}",
             "nombre": f"Todo lo de {_ETIQUETAS_CATEGORIA.get(f['categoria'], f['categoria'])}",
             "familia": "Familias de eventos", "forma_natural": "barras",
             "detalle": f"{f['cuantas']} eventos registrados"}
            for f in logs_store.categorias_registradas()
        )
        salida.extend(
            {"id": f"accion:{f['accion']}", "nombre": logs.etiqueta_accion(f["accion"]),
             "familia": "Eventos concretos", "forma_natural": "barras",
             "detalle": f"{f['cuantas']} veces"}
            for f in logs_store.acciones_registradas()
        )
        return salida

    def _pintar(self, panel: dict, *, usar_rango_global: bool = True) -> dict:
        ficha = nodes_store.normalizar_panel(panel)
        clase, _, clave = ficha["medida"].partition(":")
        es_serie = clase == "serie"
        circular = ficha["forma"] in ("donut", "circular")
        unidad = _unidad_de_serie(clave) if es_serie else ""
        nombre = next((c["nombre"] for c in self.catalogo if c["id"] == ficha["medida"]),
                      ficha["medida"])
        agrupacion = ficha["agrupacion"]
        agrupacion_texto = _AGRUPACIONES.get(agrupacion, "Por día")
        if agrupacion == "intervalo":
            agrupacion_texto = f"Cada {ficha['intervalo_minutos']} min"
        if ficha["franja"]:
            ventana = f"{ficha['hora_desde']}–{ficha['hora_hasta']}"
            if ficha["hora_desde"] == ficha["hora_hasta"]:
                ventana += " (24 h)"
            agrupacion_texto += f" · {ventana}"
        salida = {
            **ficha, "datos": [], "datos_circulares": [], "medida_nombre": nombre,
            "fuente_secundaria": "" if ficha.get("titulo", "").strip() == nombre.strip() else nombre,
            "ultima_lectura_texto": "", "principal_numero": "—",
            "principal_unidad": "" if ficha["operacion"] == "conteo" else unidad,
            "unidad": unidad, "unidad_grafica": "" if circular or ficha["operacion"] == "conteo" else unidad,
            "resumen": "", "vacio": True, "dias_texto": f"{ficha['dias']} días",
            "valor_texto": "—", "valor_etiqueta": _OPERACIONES.get(ficha["operacion"], "Media") if es_serie else "Total de eventos",
            "minimo_texto": "—", "maximo_texto": "—", "ultimo_texto": "—",
            "minimo_etiqueta": "Mínimo" if es_serie else "Mínimo por tramo",
            "maximo_etiqueta": "Máximo" if es_serie else "Máximo por tramo",
            "ultimo_etiqueta": "Última lectura" if es_serie else "Último tramo",
            "muestras_texto": "Sin muestras" if es_serie else "Sin eventos",
            "periodo_texto": "", "agrupacion_texto": agrupacion_texto,
            "forma_nombre": _FORMAS.get(ficha["forma"], "Barras"),
            "icono": "thermometer" if unidad == " °C" else "activity" if es_serie else "chart-no-axes-column-increasing",
            "es_serie": es_serie, "es_circular": circular, "error": "",
            "circular_detalle": "Distribución de muestras por valor" if es_serie else "Distribución de eventos por tramo",
        }
        try:
            desde, hasta, periodo = _rango_panel(
                ficha, self.rango_global if usar_rango_global else "panel")
            salida["periodo_texto"] = periodo
            horario = {
                "hora_desde": ficha["hora_desde"] if ficha["franja"] else "",
                "hora_hasta": ficha["hora_hasta"] if ficha["franja"] else "",
            }
            opciones = {"agrupacion": agrupacion,
                        "intervalo_minutos": ficha["intervalo_minutos"], **horario}
            if es_serie:
                filas = logs_store.consultar_metricas(
                    clave, desde, hasta, operacion=ficha["operacion"], **opciones)
            else:
                acciones, categorias = MetricasState._acciones_de(clase, clave)
                if not acciones and not categorias:
                    raise ValueError("Esta fuente ya no está disponible. Edita el panel para elegir otra.")
                filas = logs_store.consultar_eventos(
                    desde, hasta, acciones=acciones, categorias=categorias, **opciones)
            datos = [
                {"x": _etiqueta_bucket(f["bucket"], agrupacion),
                 "y": round(f["valor"], 2) if f["valor"] is not None else None}
                for f in filas
            ]
            muestras = sum(f["muestras"] for f in filas)
            presentes = [f for f in filas if f["muestras"] > 0]
            timestamps = [f["ultimo_ts"] for f in presentes if f["ultimo_ts"] is not None]
            salida["ultima_lectura_texto"] = _texto_fecha_lectura(
                max(timestamps) if timestamps else None)
            salida["datos"] = datos
            salida["vacio"] = muestras == 0
            salida["muestras_texto"] = f"{_numero(muestras)} {'muestras' if es_serie else 'eventos'}"
            salida["resumen"] = f"{len(filas)} tramos · {salida['muestras_texto']}"
            if es_serie and presentes:
                minimo = min(f["minimo"] for f in presentes)
                maximo = max(f["maximo"] for f in presentes)
                ultimo = max(presentes, key=lambda f: f["ultimo_ts"] or 0)["ultimo"]
                media = sum(f["media"] * f["muestras"] for f in presentes) / muestras
                principal = {"media": media, "minimo": minimo, "maximo": maximo,
                             "ultimo": ultimo, "conteo": muestras}[ficha["operacion"]]
                salida.update(
                    valor_texto=_numero(principal, "" if ficha["operacion"] == "conteo" else unidad),
                    principal_numero=_numero(principal),
                    minimo_texto=_numero(minimo, unidad), maximo_texto=_numero(maximo, unidad),
                    ultimo_texto=_numero(ultimo, unidad),
                )
                if circular:
                    salida["datos_circulares"] = _distribucion_serie(
                        clave, desde, hasta, minimo, maximo, muestras, horario)
                    salida["resumen"] = "Cada sector cuenta muestras, no suma valores."
            elif not es_serie:
                valores = [f["valor"] for f in filas]
                salida.update(
                    valor_texto=_numero(muestras), principal_numero=_numero(muestras), minimo_texto=_numero(min(valores) if valores else None),
                    maximo_texto=_numero(max(valores) if valores else None),
                    ultimo_texto=_numero(valores[-1] if valores else None),
                )
                if circular:
                    salida["datos_circulares"] = _agrupar_circulares(datos)
                    salida["resumen"] = f"{_numero(muestras)} eventos · hasta 8 sectores"
        except sqlite3.Error:
            salida["error"] = "El histórico no está disponible. Vuelve a actualizar en unos segundos."
            salida["resumen"] = "No se han podido consultar los datos."
        except (ValueError, OverflowError, OSError) as error:
            salida["error"] = str(error)
            salida["resumen"] = "Ajusta la configuración para consultar este panel."
        return salida

    @staticmethod
    def _acciones_de(clase: str, valor: str) -> tuple[tuple, tuple]:
        if clase == "grupo":
            return GRUPOS.get(valor, ("", ()))[1], ()
        if clase == "categoria":
            return (), (valor,)
        if clase == "accion":
            return (valor,), ()
        return (), ()

    @rx.event
    async def alternar_equipo(self, host_id: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        encendido = nodes_store.toggle_equipo_en_metricas(host_id)
        nombre = next((e["nombre"] for e in self.equipos if e["id"] == host_id), host_id)
        self._recargar()
        await audit.registrar(
            self, logs.EQUIPOS,
            "EQUIPO_EN_METRICAS" if encendido else "EQUIPO_FUERA_DE_METRICAS",
            f"{nombre} · {'se guarda en el histórico' if encendido else 'ya no se guarda'}",
        )

    def _cargar_editor(self, panel: dict) -> None:
        self.preview_movil_abierta = False
        panel = dict(panel)
        if panel["forma"] in ("barras_dia", "barras_hora"):
            panel["forma"] = "barras"
        for campo in _CAMPOS_PANEL:
            setattr(self, f"ed_{campo}", panel[campo])
        self.ed_error = ""
        self.preview_desactualizada = False
        self._actualizar_preview()

    @rx.event
    def nuevo_panel(self):
        self.panel_en_edicion = "nuevo"
        medida = self.catalogo[0]["id"] if self.catalogo else ""
        serie = medida.startswith("serie:")
        ahora = datetime.now()
        ficha = nodes_store.normalizar_panel({
            "titulo": "", "medida": medida, "forma": "area" if serie else "barras",
            "agrupacion": "hora" if serie else "dia", "operacion": "media" if serie else "conteo",
            "dias": 7, "color": "accent", "ancho": "normal",
            "desde": (ahora - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M"),
            "hasta": ahora.strftime("%Y-%m-%dT%H:%M"),
        })
        ficha["titulo"] = ""
        self._cargar_editor(ficha)

    @rx.event
    def editar_panel(self, panel_id: str):
        panel = next((p for p in self.paneles if p["id"] == panel_id), None)
        if panel is None:
            return
        self.panel_en_edicion = panel_id
        ficha = nodes_store.normalizar_panel(panel)
        if not ficha["desde"] or not ficha["hasta"]:
            ahora = datetime.now()
            ficha["desde"] = (ahora - timedelta(days=ficha["dias"])).strftime("%Y-%m-%dT%H:%M")
            ficha["hasta"] = ahora.strftime("%Y-%m-%dT%H:%M")
        self._cargar_editor(ficha)

    @rx.event
    def cerrar_editor(self):
        self.panel_en_edicion = ""
        self.ed_error = ""

    @rx.event
    def cambiar_editor_abierto(self, abierto: bool):
        if not abierto:
            self.panel_en_edicion = ""
            self.ed_error = ""

    def _editor_cambiado(self):
        self.ed_error = ""
        self.preview_desactualizada = True

    @rx.event
    def set_ed_titulo(self, valor: str):
        self.ed_titulo = valor
        self._editor_cambiado()

    @rx.event
    def set_ed_medida(self, valor: str):
        antes_serie = self.ed_medida.startswith("serie:")
        self.ed_medida = valor
        es_serie = valor.startswith("serie:")
        if antes_serie != es_serie:
            self.ed_operacion = "media" if es_serie else "conteo"
        self._editor_cambiado()

    @rx.event
    def set_ed_forma(self, valor: str):
        self.ed_forma = valor
        self._editor_cambiado()

    @rx.event
    def set_ed_dias(self, valor: str):
        try:
            self.ed_dias = int(valor)
        except (TypeError, ValueError):
            self.ed_dias = 7
        self._editor_cambiado()

    @rx.event
    def set_ed_color(self, valor: str):
        self.ed_color = valor
        self._editor_cambiado()

    @rx.event
    def set_ed_agrupacion(self, valor: str):
        self.ed_agrupacion = valor
        self._editor_cambiado()

    @rx.event
    def set_ed_intervalo_minutos(self, valor: str):
        try:
            self.ed_intervalo_minutos = int(valor)
        except (TypeError, ValueError):
            self.ed_intervalo_minutos = 0
        self._editor_cambiado()

    @rx.event
    def set_ed_operacion(self, valor: str):
        self.ed_operacion = valor
        self._editor_cambiado()

    @rx.event
    def set_ed_periodo(self, valor: str):
        self.ed_periodo = valor
        self._editor_cambiado()

    @rx.event
    def set_ed_desde(self, valor: str):
        self.ed_desde = valor
        self._editor_cambiado()

    @rx.event
    def set_ed_hasta(self, valor: str):
        self.ed_hasta = valor
        self._editor_cambiado()

    @rx.event
    def set_ed_franja(self, valor: bool):
        self.ed_franja = valor
        self._editor_cambiado()

    @rx.event
    def set_ed_hora_desde(self, valor: str):
        self.ed_hora_desde = valor
        self._editor_cambiado()

    @rx.event
    def set_ed_hora_hasta(self, valor: str):
        self.ed_hora_hasta = valor
        self._editor_cambiado()

    @rx.event
    def set_ed_ancho(self, valor: str):
        self.ed_ancho = valor
        self._editor_cambiado()

    def _ficha_editor(self) -> dict:
        ficha = {campo: getattr(self, f"ed_{campo}") for campo in _CAMPOS_PANEL}
        ficha["titulo"] = self.ed_titulo.strip() or next(
            (c["nombre"] for c in self.catalogo if c["id"] == self.ed_medida), "Panel")
        if not self.ed_medida.startswith("serie:"):
            ficha["operacion"] = "conteo"
        return ficha

    def _validar_editor(self) -> str:
        if not self.ed_medida:
            return "Elige qué quieres medir."
        if self.ed_forma not in _FORMAS:
            return "Elige un tipo de gráfica disponible."
        if self.ed_agrupacion not in _AGRUPACIONES:
            return "Elige cómo agrupar las lecturas."
        if self.ed_operacion not in _OPERACIONES:
            return "Elige un cálculo disponible."
        if self.ed_periodo not in ("relativo", "personalizado"):
            return "Elige un período disponible."
        if not 5 <= self.ed_intervalo_minutos <= 1440:
            return "El intervalo debe estar entre 5 y 1.440 minutos."
        if self.ed_franja:
            for hora in (self.ed_hora_desde, self.ed_hora_hasta):
                try:
                    if datetime.strptime(hora, "%H:%M").strftime("%H:%M") != hora:
                        raise ValueError
                except (ValueError, TypeError):
                    return "Completa las dos horas de la franja."
        try:
            _rango_panel(self._ficha_editor())
        except (ValueError, OverflowError, OSError) as error:
            return str(error)
        return ""

    def _actualizar_preview(self):
        self.ed_error = self._validar_editor()
        if self.ed_error:
            self.preview_desactualizada = True
            return
        self.preview = self._pintar(
            {"id": "preview", **self._ficha_editor()}, usar_rango_global=False)
        self.ed_error = self.preview["error"]
        self.preview_desactualizada = bool(self.ed_error)

    @rx.event
    def alternar_preview_movil(self):
        self.preview_movil_abierta = not self.preview_movil_abierta

    @rx.event
    def actualizar_preview(self):
        self._actualizar_preview()

    @rx.event
    async def guardar_panel(self):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        self._actualizar_preview()
        if self.ed_error:
            return rx.toast.error(self.ed_error)
        ficha = self._ficha_editor()
        if self.panel_en_edicion == "nuevo":
            nodes_store.add_panel(**ficha)
            accion = "PANEL_METRICA_CREADO"
        elif self.panel_en_edicion:
            guardado = nodes_store.update_panel(self.panel_en_edicion, ficha)
            if guardado is None:
                self.ed_error = "Este panel ya no existe. Crea uno nuevo."
                return rx.toast.error(self.ed_error)
            accion = "PANEL_METRICA_EDITADO"
        else:
            return
        self.panel_en_edicion = ""
        self._recargar()
        await audit.registrar(self, logs.SISTEMA, accion, ficha["titulo"])

    @rx.event
    async def duplicar_panel(self, panel_id: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        ficha = next((p for p in nodes_store.list_paneles() if p["id"] == panel_id), None)
        if ficha is None:
            return
        normal = nodes_store.normalizar_panel(ficha)
        copia = {campo: normal[campo] for campo in _CAMPOS_PANEL}
        copia["titulo"] = f"{copia['titulo']} · copia"
        nodes_store.add_panel(**copia)
        self._recargar()
        await audit.registrar(self, logs.SISTEMA, "PANEL_METRICA_CREADO", copia["titulo"])
        return rx.toast.success("Panel duplicado. Puedes personalizar la copia.")

    @rx.event
    async def crear_dashboard_base(self):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        existentes = {p["medida"] for p in nodes_store.list_paneles()}
        disponibles = {c["id"]: c for c in self.catalogo}
        candidatos = (
            (f"serie:{metricas.SERVIDOR_TEMP}", "area", "accent"),
            (f"serie:{metricas.TEMP_CPU}", "linea", "warning"),
            (f"serie:{metricas.SERVIDOR_CPU}", "area", "purple"),
            (f"serie:{metricas.EQUIPOS_EN_LINEA}", "linea", "success"),
            (f"serie:{metricas.SERVIDOR_RAM}", "area", "purple"),
            ("grupo:aperturas", "barras", "accent"),
        )
        creados = 0
        # Repetir el botón no duplica fuentes ya incluidas, ni rellena datos.
        for medida, forma, color in candidatos:
            if medida not in disponibles or medida in existentes:
                continue
            serie = medida.startswith("serie:")
            nodes_store.add_panel(
                disponibles[medida]["nombre"], forma, medida, 7, color,
                agrupacion="hora" if serie else "dia",
                operacion="media" if serie else "conteo", ancho="normal",
            )
            existentes.add(medida)
            creados += 1
        self._recargar()
        if creados:
            await audit.registrar(self, logs.SISTEMA, "PANEL_METRICA_CREADO",
                                  f"Dashboard de salud · {creados} paneles")
            return rx.toast.success(f"{creados} paneles listos para personalizar.")
        return rx.toast.info("Las fuentes del dashboard base ya están incluidas.")

    @rx.event
    async def borrar_panel(self, panel_id: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        ficha = next((p for p in nodes_store.list_paneles() if p["id"] == panel_id), None)
        if ficha is None:
            return
        normal = nodes_store.normalizar_panel(ficha)
        nodes_store.delete_panel(panel_id)
        self._recargar()
        await audit.registrar(self, logs.SISTEMA, "PANEL_METRICA_ELIMINADO", ficha["titulo"])
        return DeshacerState.apuntar(
            "panel_borrado",
            {"panel": {campo: normal[campo] for campo in _CAMPOS_PANEL}},
            f"Panel «{ficha['titulo']}» quitado",
        )

    @rx.event
    async def mover_panel(self, panel_id: str, direccion: int):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        nodes_store.move_panel(panel_id, direccion)
        self._recargar()


    @rx.var
    def paneles_visibles(self) -> list[dict]:
        filtrados = [
            p for p in self.paneles if self.filtro_paneles == "todos"
            or _categoria_de_medida(p["medida"]) == self.filtro_paneles
        ]
        return filtrados if self.editando else filtrados[:self.limite_paneles]

    @rx.var
    def paneles_filtrados_count(self) -> int:
        return sum(
            self.filtro_paneles == "todos"
            or _categoria_de_medida(p["medida"]) == self.filtro_paneles
            for p in self.paneles
        )

    @rx.var
    def hay_mas_paneles(self) -> bool:
        return not self.editando and self.paneles_filtrados_count > self.limite_paneles

    @rx.var
    def categorias_paneles(self) -> list[dict]:
        conteos = {clave: 0 for clave in _CATEGORIAS_PANEL}
        conteos["todos"] = len(self.paneles)
        for panel in self.paneles:
            conteos[_categoria_de_medida(panel["medida"])] += 1
        return [
            {"id": clave, "nombre": nombre, "cuantos": conteos[clave]}
            for clave, nombre in _CATEGORIAS_PANEL.items()
            if clave == "todos" or conteos[clave] > 0
        ]

    @rx.var
    def resumen_rango(self) -> str:
        if self.rango_global == "panel":
            return "Según cada panel"
        if self.rango_global == "1":
            return "Últimas 24 horas"
        return f"Últimos {self.rango_global} días"

    @rx.var
    def hay_paneles(self) -> bool:
        return bool(self.paneles)

    @rx.var
    def editor_abierto(self) -> bool:
        return bool(self.panel_en_edicion)

    @rx.var
    def ed_es_serie(self) -> bool:
        return self.ed_medida.startswith("serie:")

    @rx.var
    def paneles_count(self) -> int:
        return len(self.paneles)

    @rx.var
    def series_count(self) -> int:
        return sum(c["id"].startswith("serie:") for c in self.catalogo)

    @rx.var
    def equipos_count(self) -> int:
        return sum(bool(h["en_metricas"]) for h in self.equipos)

    @rx.var
    def eventos_count(self) -> int:
        return sum(not p["medida"].startswith("serie:") for p in self.paneles)

    @rx.var
    def catalogo_agrupado(self) -> list[dict]:
        return [{"id": c["id"], "etiqueta": f"{c['familia']} · {c['nombre']}"}
                for c in self.catalogo]

    @rx.var
    def dias_ui(self) -> list[str]:
        return [str(d) for d in DIAS_POSIBLES]

    @rx.var
    def formas_ui(self) -> list[dict]:
        return [{"id": clave, "nombre": nombre} for clave, nombre in _FORMAS.items()
                if clave not in ("barras_dia", "barras_hora")]

    @rx.var
    def agrupaciones_ui(self) -> list[dict]:
        return [{"id": clave, "nombre": nombre} for clave, nombre in _AGRUPACIONES.items()]

    @rx.var
    def operaciones_ui(self) -> list[dict]:
        return [{"id": clave, "nombre": nombre} for clave, nombre in _OPERACIONES.items()]

    @rx.var
    def colores_ui(self) -> list[str]:
        return list(nodes_store.COLORES_PANEL)
