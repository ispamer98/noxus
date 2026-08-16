"""
Estado de la pestaña "Registros": qué familias se están mirando (una o
varias a la vez, o "Todo"), desde cuándo y el buscador.

Va aparte de SecurityState a propósito. Ahí el histórico era una lista y ya
está (SecurityState.logs_recientes, que sigue usando la vista clásica); aquí
hay pestañas, rango de fechas y búsqueda, y todo eso es estado de ESTA
pantalla, no del sistema de seguridad.

Aquí se decide también CÓMO se ve cada evento —icono y color—, y no en la
vista: dentro de un rx.foreach no se puede consultar el disco ni elegir con un
if, así que cada fila tiene que llegar con su icono y su color ya resueltos.
La regla es que el elemento manda sobre la familia: una luz sale con el icono y
el color que tenga en el plano, y un equipo con el suyo, porque reconocerlos de
un vistazo es justo para lo que se mira un registro.
"""
import asyncio
import time
from datetime import datetime

import reflex as rx

from . import logs
from ..nodes import store as nodes_store

# Cuántas filas se pintan de una tacada; se amplía con el botón del final.
PAGINA = 150

# Pestaña que enseña todas las familias juntas.
TODO = "todo"

# (id, etiqueta, horas hacia atrás; 0 = sin límite)
RANGOS = (
    ("24h", "24 horas", 24),
    ("7d", "7 días", 24 * 7),
    ("30d", "30 días", 24 * 30),
    ("todo", "Todo", 0),
)
_HORAS_RANGO = {rid: horas for rid, _, horas in RANGOS}

# Valor de `rango` cuando manda el intervalo escrito a mano (desde/hasta). No
# está en RANGOS porque no es un atajo más: no se elige pulsándolo, se activa
# al rellenar las fechas.
PERSONALIZADO = "personalizado"

# Icono y color de cada acción. Es la tabla visual de siempre, ampliada al
# resto del sistema.
#
# Un None significa "aquí manda el elemento": el icono se coge del propio
# elemento (el del equipo, el que tenga la luz en el plano) y el color de su
# color del plano. Así una luz del salón en cian sale en cian también en el
# registro, y un equipo que se cae sale con SU icono, no con un servidor
# genérico igual para todos.
_META = {
    # Aperturas y cierres — lo más visual del registro, iconos de puerta.
    "ELEMENTO_ABIERTO": ("door-open", "aviso"),
    "ELEMENTO_CERRADO": ("door-closed", "ok"),
    "PUERTA_ABIERTA": ("door-open", "aviso"),
    "PUERTA_CERRADA": ("door-closed", "ok"),
    "PUERTA_ABIERTA_ARMADA": ("triangle-alert", "peligro"),
    "PUERTA_ABIERTA_MANDO": ("door-open", "aviso"),
    "PUERTA_MANTENIDA_ABIERTA": ("door-open", "aviso"),
    "PUERTA_MANTENIDA_CERRADA": ("door-closed", "ok"),
    "PUERTA_PULSO_CORTADO": ("square", "neutro"),
    "TAMPER1_ABIERTO": ("lock-open", "peligro"),
    "TAMPER1_CERRADO": ("lock", "ok"),
    "TAMPER2_ABIERTO": ("lock-open", "peligro"),
    "TAMPER2_CERRADO": ("lock", "ok"),
    # Alarma. El armado TOTAL y el de un grupo llevan color distinto a
    # propósito: de un vistazo tiene que verse si se armó la casa entera o una
    # zona, que es la diferencia que importa.
    "ARMADO": ("shield-check", "armado_total"),
    "DESARMADO": ("shield-off", "neutro"),
    "ARMADO_GRUPO": ("shield-check", "armado_parcial"),
    "DESARMADO_GRUPO": ("shield-off", "neutro"),
    "ALARMA_DISPARADA": ("triangle-alert", "peligro"),
    "GRUPO_ALERTA": ("triangle-alert", "peligro"),
    "GRUPO_CERRADO": ("shield-check", "ok"),
    # Luces: encendida toma el color del plano; apagada se apaga también aquí.
    "LUZ_ENCENDIDA": (None, None),
    "LUZ_APAGADA": ("lightbulb-off", "neutro"),
    "LUZ_ERROR": ("triangle-alert", "peligro"),
    # Equipos: siempre su propio icono; verde al conectarse, gris al caerse.
    "EQUIPO_CONECTADO": (None, "ok"),
    "EQUIPO_DESCONECTADO": (None, "neutro"),
    "EQUIPO_APAGADO": (None, "peligro"),
    "EQUIPO_REINICIADO": (None, "aviso"),
    "EQUIPO_CREADO": (None, "ok"),
    "EQUIPO_EDITADO": (None, "info"),
    "EQUIPO_ELIMINADO": (None, "peligro"),
    "COMANDO_SSH": ("terminal", "info"),
    "TEMPERATURA_CONSULTADA": ("thermometer", "info"),
    "ESCRITORIO_REMOTO_ABIERTO": ("monitor-play", "info"),
    "ESCRITORIO_REMOTO_DESCARGADO": ("download", "info"),
    # Altas, bajas y ediciones: mismo lenguaje en todas las familias.
    "SENSOR_AISLADO": ("eye-off", "aviso"),
    "SENSOR_REINTEGRADO": ("eye", "ok"),
    "CAMARA_SIRENA": ("siren", "peligro"),
    "CAMARA_PRIVACIDAD_ON": ("eye-off", "aviso"),
    "CAMARA_PRIVACIDAD_OFF": ("eye", "ok"),
    "ALERTA_ENVIADA": ("bell-ring", "aviso"),
}

# Sufijos genéricos: cualquier acción que acabe así hereda este aspecto si no
# tiene entrada propia arriba. Evita repetir la tabla para cada familia.
_POR_SUFIJO = (
    ("_CREADA", ("plus", "ok")), ("_CREADO", ("plus", "ok")),
    ("_EDITADA", ("pencil", "info")), ("_EDITADO", ("pencil", "info")),
    ("_ELIMINADA", ("trash-2", "peligro")), ("_ELIMINADO", ("trash-2", "peligro")),
    ("_AÑADIDO_A_GRUPO", ("plus", "ok")), ("_QUITADO_DE_GRUPO", ("minus", "aviso")),
    ("_AÑADIDA_A_NIVEL", ("plus", "ok")), ("_QUITADA_DE_NIVEL", ("minus", "aviso")),
)

# Acciones cuyo detalle es una frase, no el nombre de un elemento: en esas el
# texto en grande es la propia acción y la frase pasa a la info ampliada.
_SIN_SUJETO = {
    "ARMADO", "DESARMADO", "ARMADO_GRUPO", "DESARMADO_GRUPO",
    "ALERTA_ENVIADA", "GRUPO_PRINCIPAL_CAMBIADO",
}

_ICONO_CATEGORIA = {cid: icono for cid, _, icono in logs.CATEGORIAS}
_ICONOS_POR_COLECCION = {
    "lights": "lightbulb", "doors": "door-closed",
    "sensors": "radar", "factory_sensors": "radar",
    "cameras": "cctv", "factory_cameras": "cctv",
}


def _catalogo_entidades() -> dict[str, tuple[str, str]]:
    """id -> (icono, color del plano) de todo lo que puede salir en un evento.

    Se lee del disco en cada recarga, no se copia en el registro: así, cambiar
    el icono o el color de una luz repinta también su histórico, en vez de
    dejar los eventos viejos con el aspecto que tenía el día que pasaron."""
    datos = nodes_store.read_all()
    catalogo = {h["id"]: (h.get("icon") or "server", "") for h in datos["hosts"]}
    for coleccion, icono_defecto in _ICONOS_POR_COLECCION.items():
        for item in datos[coleccion]:
            catalogo[item["id"]] = (
                item.get("floor_icon") or icono_defecto,
                item.get("floor_color") or "",
            )
    return catalogo


def _instante(timestamp: str) -> float:
    try:
        return datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").timestamp()
    except Exception:
        return 0.0


def _instante_local(valor: str) -> float:
    """Lo que manda un <input type="datetime-local">: "2026-08-07T14:30".
    Devuelve 0 si está vacío o a medias, y 0 significa "sin límite por ese
    lado" — así se puede poner solo el desde, solo el hasta, o los dos."""
    try:
        return datetime.fromisoformat(valor).timestamp() if valor else 0.0
    except Exception:
        return 0.0


def _bonito(valor: str) -> str:
    """"2026-08-07T14:30" -> "07/08 14:30", para la etiqueta del botón."""
    try:
        return datetime.fromisoformat(valor).strftime("%d/%m %H:%M")
    except Exception:
        return ""


# Los nombres van a mano y no con strftime: éste depende del locale que tenga
# instalado el sistema, y en un servidor pelado sale en inglés.
_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def _fecha_larga(fecha: str) -> str:
    """"2026-08-15" -> "Hoy", "Ayer" o "sábado, 15 de agosto" — el rótulo que
    encabeza el bloque de eventos de cada día."""
    try:
        dia = datetime.strptime(fecha, "%Y-%m-%d").date()
    except Exception:
        return fecha
    hoy = datetime.now().date()
    if dia == hoy:
        return "Hoy"
    if (hoy - dia).days == 1:
        return "Ayer"
    texto = f"{_DIAS[dia.weekday()]}, {dia.day} de {_MESES[dia.month - 1]}"
    if dia.year != hoy.year:
        texto += f" de {dia.year}"
    return texto


class LogsState(rx.State):
    # Familias marcadas a la vez ([] = "Todo", sin ninguna en concreto
    # seleccionada). "Todo" es independiente del resto: marcarlo vacía la
    # selección en vez de añadirse a ella — ver ver_pestana.
    pestanas_activas: list[str] = []
    rango: str = "7d"
    desde: str = ""
    hasta: str = ""
    busqueda: str = ""
    limite: int = PAGINA
    _entradas: list[dict] = []
    _entidades: dict[str, list[str]] = {}

    @rx.event
    async def on_load(self):
        self._releer()
        yield LogsState.sync_loop

    def _releer(self) -> None:
        # Más reciente primero: en un registro se mira lo último, no lo primero.
        self._entradas = [
            {**e, "ts": _instante(e["timestamp"])} for e in reversed(logs.leer_logs())
        ]
        # dict[str, list] en vez de dict[str, tuple]: Reflex serializa las Vars
        # a JSON y las tuplas vuelven como listas de todas formas.
        self._entidades = {k: list(v) for k, v in _catalogo_entidades().items()}

    @rx.event
    def refrescar(self):
        self._releer()

    @rx.event(background=True)
    async def sync_loop(self):
        """Relee cada dos segundos: un evento que pase con la pestaña abierta
        tiene que aparecer solo, sin tocar el botón de recargar.

        Se compara antes de asignar, y no es un detalle: sin eso cada vuelta
        reasignaría la lista entera, el navegador repintaría las filas y se
        cerraría el bocadillo que estuviera abierto — cada dos segundos."""
        while True:
            try:
                await asyncio.sleep(2)
                nuevas = await asyncio.to_thread(logs.leer_logs)
                nuevas = [{**e, "ts": _instante(e["timestamp"])} for e in reversed(nuevas)]
                async with self:
                    if nuevas != self._entradas:
                        self._entradas = nuevas
            except Exception as e:
                print(f"⚠️ Error en LogsState.sync_loop: {e}")
                await asyncio.sleep(5)

    # ── Filtros ──────────────────────────────────────────────────────────
    @rx.event
    def ver_pestana(self, categoria: str):
        """Selección múltiple de familias: cada una se marca/desmarca sin
        tocar las demás, para poder mirar "Alarma y Luces" o "Equipos y
        Accesos" a la vez. "Todo" es independiente del resto — marcarlo
        siempre vacía la selección entera (ver todo), nunca se suma a otras
        familias marcadas."""
        if categoria == TODO:
            self.pestanas_activas = []
        elif categoria in self.pestanas_activas:
            self.pestanas_activas = [c for c in self.pestanas_activas if c != categoria]
        else:
            self.pestanas_activas = [*self.pestanas_activas, categoria]
        self.limite = PAGINA

    @rx.event
    def set_rango(self, rango: str):
        """Los atajos y el intervalo a mano se pisan: elegir "7 días" vacía el
        desde/hasta, para que no quede un intervalo escrito que ya no se aplica
        y confunda al mirar el botón."""
        self.rango = rango
        self.desde = ""
        self.hasta = ""
        self.limite = PAGINA

    @rx.event
    def set_desde(self, valor: str):
        self.desde = valor
        self.rango = PERSONALIZADO
        self.limite = PAGINA

    @rx.event
    def set_hasta(self, valor: str):
        self.hasta = valor
        self.rango = PERSONALIZADO
        self.limite = PAGINA

    @rx.event
    def limpiar_intervalo(self):
        self.desde = ""
        self.hasta = ""
        self.rango = "todo"
        self.limite = PAGINA

    @rx.event
    def set_busqueda(self, valor: str):
        self.busqueda = valor
        self.limite = PAGINA

    @rx.event
    def ver_mas(self):
        self.limite += PAGINA

    # ── Selección ────────────────────────────────────────────────────────
    def _limites(self) -> tuple[float, float]:
        """(desde, hasta) en segundos; 0 en cualquiera de los dos = sin límite
        por ese lado."""
        if self.rango == PERSONALIZADO:
            return _instante_local(self.desde), _instante_local(self.hasta)
        horas = _HORAS_RANGO.get(self.rango, 0)
        return (time.time() - horas * 3600 if horas else 0.0), 0.0

    def _coincide(self, entrada: dict, limites: tuple[float, float]) -> bool:
        if self.pestanas_activas and entrada["categoria"] not in self.pestanas_activas:
            return False
        desde, hasta = limites
        # ts == 0 es una marca de tiempo que no se pudo leer: se deja pasar
        # antes que esconder un evento por un fallo de formato.
        if entrada["ts"]:
            if desde and entrada["ts"] < desde:
                return False
            if hasta and entrada["ts"] > hasta:
                return False
        texto = self.busqueda.strip().lower()
        if not texto:
            return True
        return texto in " ".join((
            entrada["accion"], logs.etiqueta_accion(entrada["accion"]),
            entrada["usuario"], entrada["detalle"], entrada["grupo"],
        )).lower()

    def _aspecto(self, entrada: dict) -> tuple[str, str]:
        """(icono, clave de color) de un evento — ver _META."""
        accion = entrada["accion"]
        icono, color = _META.get(accion, (None, None))
        if accion not in _META:
            for sufijo, meta in _POR_SUFIJO:
                if accion.endswith(sufijo):
                    icono, color = meta
                    break
        icono_ent, color_ent = self._entidades.get(entrada["entidad"], ("", ""))
        return (
            icono or icono_ent or _ICONO_CATEGORIA.get(entrada["categoria"], "file-text"),
            color or color_ent or entrada["categoria"],
        )

    @rx.var
    def reciente(self) -> dict:
        """El último evento de TODA la casa, sin mirar rango/pestañas/búsqueda
        de esta pantalla — es lo que consume el widget "Último evento" del
        Resumen. Tiene que ser el último de verdad pase lo que pase con los
        filtros que alguien haya dejado puestos en Registros: si tirara de
        `filtradas`, filtrar por "Luces" en una pestaña le mentiría al
        Resumen sobre cuál fue el último suceso."""
        if not self._entradas:
            return {}
        e = self._entradas[0]
        etiqueta = logs.etiqueta_accion(e["accion"])
        icono, color = self._aspecto(e)
        partes = e["detalle"].split(" · ")
        sujeto, resto = partes[0], " · ".join(partes[1:])
        if e["accion"] in _SIN_SUJETO or len(sujeto) > 42:
            titulo, extra = etiqueta, e["detalle"]
        else:
            titulo, extra = sujeto, resto
        return {
            "titulo": titulo, "extra": extra, "icono": icono, "color": color,
            "hora": e["timestamp"][11:19], "fecha": e["timestamp"][:10],
        }

    @rx.var
    def filtradas(self) -> list[dict]:
        """Las entradas visibles, ya masticadas para la UI: dentro de un
        rx.foreach no se puede llamar a funciones de Python, así que todo lo
        que hay que decidir se decide aquí.

        La clave es la posición en la lista COMPLETA: así identifica siempre al
        mismo evento, cambien los filtros que cambien."""
        limites = self._limites()
        salida = []
        # Fecha de la última fila añadida, para saber dónde cambia el día. Se
        # decide aquí y no al pintar porque dentro de un rx.foreach no se puede
        # mirar la fila anterior.
        dia_anterior = ""
        for i, e in enumerate(self._entradas):
            if not self._coincide(e, limites):
                continue
            etiqueta = logs.etiqueta_accion(e["accion"])
            icono, color = self._aspecto(e)
            fecha = e["timestamp"][:10]
            nuevo_dia = fecha != dia_anterior
            dia_anterior = fecha

            partes = e["detalle"].split(" · ")
            sujeto, resto = partes[0], " · ".join(partes[1:])
            if e["accion"] in _SIN_SUJETO or len(sujeto) > 42:
                # El detalle es una frase: manda la acción y la frase va debajo.
                titulo, tag, extra = etiqueta, "", e["detalle"]
            else:
                titulo, tag, extra = sujeto, etiqueta, resto
            extra = extra.replace("Armado con abiertos: ", "Abiertos al armar: ")

            salida.append({
                **e,
                "clave": str(i),
                "icono": icono,
                "color": color,
                "titulo": titulo,
                "tag": tag,
                "extra": extra,
                "hora": e["timestamp"][11:19],
                "fecha": fecha,
                # Primera fila de su día: lleva encima el separador con la
                # fecha (ver _fila en ui/dashboard/views/logs.py).
                "nuevo_dia": nuevo_dia,
                "fecha_larga": _fecha_larga(fecha) if nuevo_dia else "",
            })
            if len(salida) >= self.limite:
                break
        return salida

    @rx.var
    def total_filtradas(self) -> int:
        limites = self._limites()
        return sum(1 for e in self._entradas if self._coincide(e, limites))

    @rx.var
    def hay_mas(self) -> bool:
        return self.total_filtradas > self.limite

    @rx.var
    def pestanas(self) -> list[dict]:
        """Las pestañas con su recuento DENTRO del rango de tiempo elegido: un
        contador que ignorase el rango prometería eventos que luego no salen.

        "Todo" aparece marcada solo cuando no hay ninguna familia concreta
        seleccionada — es su propio estado, no una familia más."""
        desde, hasta = self._limites()
        conteo = {c: 0 for c in logs.IDS_CATEGORIAS}
        total = 0
        for e in self._entradas:
            if e["ts"] and ((desde and e["ts"] < desde) or (hasta and e["ts"] > hasta)):
                continue
            total += 1
            if e["categoria"] in conteo:
                conteo[e["categoria"]] += 1
        return [
            {"id": TODO, "label": "Todo", "icon": "layers", "conteo": total,
             "activa": len(self.pestanas_activas) == 0},
        ] + [
            {"id": cid, "label": etiqueta, "icon": icono, "conteo": conteo[cid],
             "activa": cid in self.pestanas_activas}
            for cid, etiqueta, icono in logs.CATEGORIAS
        ]

    @rx.var
    def rangos_ui(self) -> list[dict]:
        return [
            {"id": rid, "label": etiqueta, "activa": self.rango == rid}
            for rid, etiqueta, _ in RANGOS
        ]

    @rx.var
    def intervalo_activo(self) -> bool:
        return self.rango == PERSONALIZADO and bool(self.desde or self.hasta)

    @rx.var
    def etiqueta_intervalo(self) -> str:
        """Lo que se lee en el botón del calendario. Con un solo extremo puesto
        se dice explícitamente ("Desde ..." / "Hasta ..."): un intervalo a
        medias filtra igual, y callárselo haría pensar que no se aplica."""
        if not self.intervalo_activo:
            return "Intervalo"
        desde, hasta = _bonito(self.desde), _bonito(self.hasta)
        if desde and hasta:
            return f"{desde} → {hasta}"
        return f"Desde {desde}" if desde else f"Hasta {hasta}"
