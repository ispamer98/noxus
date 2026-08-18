"""
Estado de la pestaña «Métricas»: un tablero que monta cada uno con lo que le
interese.

No hay gráficas fijas. Hay PANELES, que son fichas guardadas
(nodes_store.list_paneles) con cuatro decisiones cada una: qué mide, en qué
forma, de cuántos días y de qué color. Se añaden, se editan, se ordenan y se
quitan, igual que los widgets del Resumen.

EL CATÁLOGO DE LO MEDIBLE NO ESTÁ ESCRITO A MANO: se le pregunta a la base de
datos qué ha registrado la casa (logs_store.acciones_registradas,
categorias_registradas, claves_de_metricas). Por eso ofrece de verdad «toda la
información disponible» y no se queda corto el día que se añade un evento nuevo
o se marca un equipo más — aparece solo, sin tocar código.

Tres familias de medida, y la diferencia importa:

  serie:<clave>      un número muestreado cada cinco minutos (temperatura, cuántos
                     equipos hay en línea, si un equipo concreto responde). Se
                     pinta como línea, con la media de cada hora.
  accion:<ACCION>    cuántas veces ha pasado UN evento concreto.
  categoria:<id>     cuántas veces ha pasado CUALQUIER evento de una familia.
  grupo:aperturas    grupos con nombre para lo que se pregunta a menudo y no cae
                     en una sola acción (ver GRUPOS).

TODO SE MASTICA AQUÍ: las gráficas reciben listas de diccionarios con las
etiquetas ya escritas y los huecos ya rellenos, porque en la vista no se puede
consultar el disco ni decidir con un `if`.
"""
import time
from datetime import date, datetime, timedelta

import reflex as rx

from . import metricas
from .deshacer import DeshacerState
from ..auth import permisos
from ..nodes import store as nodes_store
from ..security import audit, logs, logs_store

# Rangos que ofrece el selector de cada panel.
DIAS_POSIBLES = (1, 7, 30, 90, 365)

# Grupos de acciones con nombre, para lo que se pregunta mucho y no es una sola
# acción. `aperturas` es el caso claro: el mismo hecho ha tenido cuatro nombres a
# lo largo del tiempo (ver logs.ACCIONES_APERTURA).
GRUPOS = {
    "aperturas": ("Aperturas (todas las formas)", logs.ACCIONES_APERTURA),
    "armados": ("Armados y desarmados",
                ("ARMADO", "DESARMADO", "ARMADO_GRUPO", "DESARMADO_GRUPO")),
    "alarmas": ("Alarmas disparadas",
                ("GRUPO_ALERTA", "ALARMA_DISPARADA", "PUERTA_ABIERTA_ARMADA")),
}

_ETIQUETAS_CATEGORIA = {cid: etiqueta for cid, etiqueta, _ in logs.CATEGORIAS}


def _dia_bonito(iso: str) -> str:
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m")
    except ValueError:
        return iso


def _hora_bonita(clave: str) -> str:
    """"2026-08-17 14" -> "14 h" si es de hoy, "17/08 14 h" si no."""
    try:
        cuando = datetime.strptime(clave, "%Y-%m-%d %H")
    except ValueError:
        return clave
    if cuando.date() == date.today():
        return f"{cuando.hour:02d} h"
    return f"{cuando.strftime('%d/%m')} {cuando.hour:02d} h"


def _nombre_de_serie(clave: str, equipos: dict[str, str]) -> str:
    """Cómo se lee una clave de serie. Los equipos con su nombre de verdad, no
    con su id: «equipo.host_3f2a» no le dice nada a nadie."""
    if clave == metricas.TEMP_CPU:
        return "Temperatura de la Raspberry"
    if clave == metricas.EQUIPOS_EN_LINEA:
        return "Equipos en línea"
    if clave == metricas.EQUIPOS_TOTAL:
        return "Equipos dados de alta"
    if clave.startswith(metricas.PREFIJO_EQUIPO):
        host_id = clave[len(metricas.PREFIJO_EQUIPO):]
        return f"Equipo: {equipos.get(host_id, host_id)}"
    return clave


class MetricasState(rx.State):
    paneles: list[dict] = []
    catalogo: list[dict] = []
    equipos: list[dict] = []

    editando: bool = False

    # Formulario del panel que se está creando o cambiando ("" = ninguno).
    panel_en_edicion: str = ""
    ed_titulo: str = ""
    ed_medida: str = ""
    ed_forma: str = "barras_dia"
    ed_dias: int = 7
    ed_color: str = "accent"

    @rx.event
    def on_load(self):
        self._recargar()

    @rx.event
    def alternar_edicion(self):
        self.editando = not self.editando

    # ── Carga ────────────────────────────────────────────────────────────
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

    def _construir_catalogo(self) -> list[dict]:
        """Todo lo que se puede medir AHORA MISMO, preguntándoselo a la base."""
        nombres_equipo = {h["id"]: h["nombre"] for h in self.equipos}
        salida: list[dict] = []

        for clave in logs_store.claves_de_metricas():
            salida.append({
                "id": f"serie:{clave}",
                "nombre": _nombre_de_serie(clave, nombres_equipo),
                "familia": "Series muestreadas",
                "forma_natural": "linea",
                "detalle": "una muestra cada 5 min",
            })
        for nombre, (etiqueta, _) in GRUPOS.items():
            salida.append({
                "id": f"grupo:{nombre}", "nombre": etiqueta,
                "familia": "Grupos de eventos", "forma_natural": "barras_dia",
                "detalle": "varias acciones juntas",
            })
        for fila in logs_store.categorias_registradas():
            cid = fila["categoria"]
            salida.append({
                "id": f"categoria:{cid}",
                "nombre": f"Todo lo de {_ETIQUETAS_CATEGORIA.get(cid, cid)}",
                "familia": "Familias de eventos", "forma_natural": "barras_dia",
                "detalle": f"{fila['cuantas']} eventos registrados",
            })
        for fila in logs_store.acciones_registradas():
            salida.append({
                "id": f"accion:{fila['accion']}",
                "nombre": logs.etiqueta_accion(fila["accion"]),
                "familia": "Eventos concretos", "forma_natural": "barras_dia",
                "detalle": f"{fila['cuantas']} veces",
            })
        return salida

    # ── Datos de un panel ────────────────────────────────────────────────
    def _pintar(self, panel: dict) -> dict:
        """La ficha del panel con sus datos ya listos para la gráfica."""
        desde = time.time() - panel["dias"] * 86400
        medida = panel["medida"]
        clase, _, valor = medida.partition(":")
        datos: list[dict] = []
        unidad = ""

        if clase == "serie":
            datos = [
                {"x": _hora_bonita(f["hora"]), "y": round(f["valor"], 1)}
                for f in logs_store.serie_por_hora(valor, desde)
            ]
            unidad = " °C" if valor == metricas.TEMP_CPU else ""
        else:
            acciones, categorias = self._acciones_de(clase, valor)
            if panel["forma"] == "barras_hora":
                filas = (logs_store.conteo_por_hora_de_categoria(categorias, desde)
                         if categorias else
                         logs_store.conteo_por_hora_del_dia(acciones, desde))
                datos = [{"x": f["hora"], "y": f["cuantas"]} for f in filas]
            else:
                filas = (logs_store.conteo_por_dia_de_categoria(categorias, desde)
                         if categorias else
                         logs_store.conteo_por_dia(acciones, desde))
                datos = self._rellenar_dias(filas, panel["dias"])

        nombre = next((c["nombre"] for c in self.catalogo if c["id"] == medida),
                      medida)
        total = sum(d["y"] for d in datos)
        return {
            **panel,
            "datos": datos,
            "medida_nombre": nombre,
            "unidad": unidad,
            # Preformateado: dentro de un rx.foreach no se puede componer texto.
            "resumen": (f"{len(datos)} tramos · {total:.0f} en total"
                        if panel["forma"] != "linea"
                        else f"{len(datos)} tramos de una hora"),
            "vacio": len(datos) == 0,
            "dias_texto": f"{panel['dias']} día(s)",
        }

    @staticmethod
    def _acciones_de(clase: str, valor: str) -> tuple[tuple, tuple]:
        """(acciones, categorías) que hay que contar. Una de las dos va vacía."""
        if clase == "grupo":
            return GRUPOS.get(valor, ("", ()))[1], ()
        if clase == "categoria":
            return (), (valor,)
        if clase == "accion":
            return (valor,), ()
        return (), ()

    @staticmethod
    def _rellenar_dias(filas: list[dict], dias: int) -> list[dict]:
        """Los días sin nada salen con cero. Una gráfica que se los salta junta
        el lunes con el jueves y miente sobre la forma de la semana."""
        conteos = {f["dia"]: f["cuantas"] for f in filas}
        hoy = date.today()
        return [
            {"x": _dia_bonito((hoy - timedelta(days=n)).isoformat()),
             "y": conteos.get((hoy - timedelta(days=n)).isoformat(), 0)}
            for n in range(dias - 1, -1, -1)
        ]

    # ── Equipos que se guardan ───────────────────────────────────────────
    @rx.event
    async def alternar_equipo(self, host_id: str):
        """Enciende o apaga el guardado del histórico de un equipo.

        Pide AJUSTES: decide qué se escribe en el histórico de la casa, no es
        mirar una gráfica."""
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        encendido = nodes_store.toggle_equipo_en_metricas(host_id)
        nombre = next((e["nombre"] for e in self.equipos if e["id"] == host_id),
                      host_id)
        self._recargar()
        await audit.registrar(
            self, logs.EQUIPOS,
            "EQUIPO_EN_METRICAS" if encendido else "EQUIPO_FUERA_DE_METRICAS",
            f"{nombre} · {'se guarda en el histórico' if encendido else 'ya no se guarda'}",
        )

    # ── Paneles ──────────────────────────────────────────────────────────
    @rx.event
    def nuevo_panel(self):
        """Abre el formulario en blanco. La primera medida del catálogo va
        puesta para que el desplegable no empiece vacío."""
        self.panel_en_edicion = "nuevo"
        self.ed_titulo = ""
        self.ed_medida = self.catalogo[0]["id"] if self.catalogo else ""
        self.ed_forma = "barras_dia"
        self.ed_dias = 7
        self.ed_color = "accent"

    @rx.event
    def editar_panel(self, panel_id: str):
        panel = next((p for p in self.paneles if p["id"] == panel_id), None)
        if panel is None:
            return
        self.panel_en_edicion = panel_id
        self.ed_titulo = panel["titulo"]
        self.ed_medida = panel["medida"]
        self.ed_forma = panel["forma"]
        self.ed_dias = panel["dias"]
        self.ed_color = panel["color"]

    @rx.event
    def cerrar_editor(self):
        self.panel_en_edicion = ""

    @rx.event
    def set_ed_titulo(self, valor: str):
        self.ed_titulo = valor

    @rx.event
    def set_ed_medida(self, valor: str):
        self.ed_medida = valor
        # Al cambiar de medida se propone la forma que le va: una temperatura en
        # barras por día no dice nada. Se propone, no se impone: si luego el
        # usuario elige otra forma, se respeta.
        natural = next((c["forma_natural"] for c in self.catalogo
                        if c["id"] == valor), "")
        if natural:
            self.ed_forma = natural

    @rx.event
    def set_ed_forma(self, valor: str):
        self.ed_forma = valor

    @rx.event
    def set_ed_dias(self, valor: str):
        try:
            self.ed_dias = max(1, int(valor))
        except (TypeError, ValueError):
            self.ed_dias = 7

    @rx.event
    def set_ed_color(self, valor: str):
        self.ed_color = valor

    @rx.event
    async def guardar_panel(self):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        if not self.ed_medida:
            return rx.toast.error("Elige qué quiere medir el panel.",
                                  position="top-center")
        # Sin título se pone el del catálogo: un panel sin nombre es un panel
        # que no se sabe qué es, y obligar a escribirlo para algo que ya tiene
        # nombre obvio es hacer trabajar a quien lo monta.
        titulo = self.ed_titulo.strip() or next(
            (c["nombre"] for c in self.catalogo if c["id"] == self.ed_medida), "Panel")
        if self.panel_en_edicion == "nuevo":
            nodes_store.add_panel(titulo, self.ed_forma, self.ed_medida,
                                  self.ed_dias, self.ed_color)
            accion, detalle = "PANEL_METRICA_CREADO", titulo
        else:
            nodes_store.update_panel(self.panel_en_edicion, {
                "titulo": titulo, "forma": self.ed_forma,
                "medida": self.ed_medida, "dias": self.ed_dias,
                "color": self.ed_color,
            })
            accion, detalle = "PANEL_METRICA_EDITADO", titulo
        self.panel_en_edicion = ""
        self._recargar()
        await audit.registrar(self, logs.SISTEMA, accion, detalle)

    @rx.event
    async def borrar_panel(self, panel_id: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        # La ficha entera ANTES de borrarla: es lo que hace que se pueda
        # reponer con un toque (ver infra/deshacer.py). Solo los cinco campos que
        # definen un panel — el id y la fecha de creacion se rehacen.
        ficha = next((p for p in nodes_store.list_paneles() if p["id"] == panel_id),
                     None)
        if ficha is None:
            return
        titulo = ficha["titulo"]
        nodes_store.delete_panel(panel_id)
        self._recargar()
        await audit.registrar(self, logs.SISTEMA, "PANEL_METRICA_ELIMINADO", titulo)
        return DeshacerState.apuntar(
            "panel_borrado",
            {"panel": {k: ficha[k] for k in
                       ("titulo", "forma", "medida", "dias", "color")}},
            f"Panel «{titulo}» quitado",
        )

    @rx.event
    async def mover_panel(self, panel_id: str, direccion: int):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            return no
        nodes_store.move_panel(panel_id, direccion)
        self._recargar()

    # ── Vars para la vista ───────────────────────────────────────────────
    @rx.var
    def hay_paneles(self) -> bool:
        return len(self.paneles) > 0

    @rx.var
    def editor_abierto(self) -> bool:
        return self.panel_en_edicion != ""

    @rx.var
    def catalogo_agrupado(self) -> list[dict]:
        """El catálogo con la familia delante del nombre, para que el
        desplegable se lea de un tirón: dentro de un rx.foreach no se pueden
        pintar grupos ni componer el texto."""
        return [{"id": c["id"], "etiqueta": f"{c['familia']} · {c['nombre']}"}
                for c in self.catalogo]

    @rx.var
    def dias_ui(self) -> list[str]:
        return [str(d) for d in DIAS_POSIBLES]

    @rx.var
    def formas_ui(self) -> list[dict]:
        return [
            {"id": "barras_dia", "nombre": "Barras por día"},
            {"id": "barras_hora", "nombre": "Barras por hora del día"},
            {"id": "linea", "nombre": "Línea en el tiempo"},
        ]

    @rx.var
    def colores_ui(self) -> list[str]:
        return list(nodes_store.COLORES_PANEL)
