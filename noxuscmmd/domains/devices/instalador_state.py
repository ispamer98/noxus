"""
Estado del modo instalador (Ajustes → Instalador): de lo que se oye por MQTT a
un sensor, una luz o una puerta en tres pasos.

  1. OÍR      se escucha la casa y se enseña lo que va llegando, lo que se
              acaba de mover arriba.
  2. FICHA    se elige un hallazgo y se le pone nombre y tipo. El nodo sale del
              propio topic; si no está dado de alta, se da aquí.
  3. HECHO    resumen de lo que se ha creado.

La salvaguarda que justifica la pantalla entera está en `guardar`: el alta
recalcula el topic a partir del nombre del nodo y de la señal (ver
nodes/store.sensor_topic), así que antes de escribir se comprueba que ese topic
sea EXACTAMENTE el que se ha oído. Si no cuadra, no se guarda: un sensor con el
topic mal puesto se da de alta sin protestar y luego no se mueve nunca, que es
el fallo que este modo existe para no repetir.
"""
import reflex as rx

from . import descubrimiento
from ..auth import permisos
from ..nodes import store as nodes_store
from ..security import audit, logs
from ...core import sesiones

OIR, FICHA, HECHO = "oir", "ficha", "hecho"

TIPOS = ["sensor", "luz", "puerta"]
CLASES_SENSOR = ["door", "pir", "tamper"]

# Cómo se llama cada cosa en la pantalla. En un sitio para que el resumen del
# paso 3 y la lista digan lo mismo.
NOMBRES_TIPO = {"sensor": "Sensor", "luz": "Luz", "puerta": "Puerta"}
NOMBRES_CLASE = {"door": "Magnético / de apertura", "pir": "Detector de movimiento",
                 "tamper": "Sabotaje"}


class InstaladorState(rx.State):
    paso: str = OIR
    escuchando: bool = False
    mensaje: str = ""
    error: bool = False

    hallazgos: list[dict] = []
    segundos: int = 0

    # ── Ficha del paso 2 ─────────────────────────────────────────────────
    topic_elegido: str = ""
    nodo_slug: str = ""
    senal: str = ""
    ficha_nombre: str = ""
    ficha_tipo: str = "sensor"
    ficha_clase: str = "pir"
    ficha_en_plano: bool = False

    # El nodo: o ya existe, o hay que crearlo aquí mismo.
    nodo_id: str = ""
    nodo_nombre: str = ""
    nodo_hay_que_crearlo: bool = False
    nodo_ip: str = ""

    creado_texto: str = ""

    # ── Paso 1: oír ──────────────────────────────────────────────────────
    @rx.event
    async def empezar(self):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            yield no
            return
        motivo = descubrimiento.arrancar()
        if motivo:
            self.error, self.mensaje = True, motivo
            return
        self.error, self.mensaje = False, ""
        self.escuchando = True
        self._refrescar()
        yield InstaladorState.vigilar

    @rx.event
    async def detener(self):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            yield no
            return
        descubrimiento.parar()
        self.escuchando = False

    @rx.event
    async def olvidar(self):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            yield no
            return
        descubrimiento.olvidar()
        self._refrescar()

    @rx.event
    def on_unmount(self):
        """Salir de la pantalla deja de escuchar. Tener al broker mandando toda
        la casa a este proceso solo tiene sentido con alguien delante."""
        descubrimiento.parar()
        self.escuchando = False

    def _refrescar(self) -> None:
        crudos = descubrimiento.hallazgos()
        self.hallazgos = [
            {
                # Todo a texto ya formateado: dentro de un rx.foreach concatenar
                # y convertir es la fuente de fallos número uno del frontend.
                "topic": h["topic"],
                "titulo": h["senal"] or h["topic"],
                "nodo": h["nodo"] or "(sin nodo)",
                "valor": h["payload"] or "(vacío)",
                "veces": f"{h['veces']} mensaje(s)",
                "hace": "ahora mismo" if h["hace"] < 2 else f"hace {h['hace']} s",
                "sugerencia": NOMBRES_TIPO.get(h["tipo"], h["tipo"]),
                "conocido": h["conocido"],
                "es_orden": h["es_orden"],
                "etiqueta_estado": (
                    f"Ya está: {h['nombre_conocido']}" if h["conocido"]
                    else "Orden del panel" if h["es_orden"]
                    else "Sin dar de alta"
                ),
                "elegible": (not h["conocido"]) and (not h["es_orden"]),
            }
            for h in crudos
        ]
        self.segundos = descubrimiento.segundos_escuchando()

    @rx.event(background=True)
    async def vigilar(self):
        """Refresca la lista mientras se escucha. Muere con la sesión (ver
        core/sesiones) y también en cuanto se deja de escuchar."""
        guardia = await sesiones.guardia(self)
        while True:
            async with self:
                if not self.escuchando:
                    return
                self._refrescar()
            if not await sesiones.espera(guardia, 1):
                return

    # ── Paso 2: ficha ────────────────────────────────────────────────────
    @rx.event
    async def elegir(self, topic: str):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            yield no
            return
        nodo, senal, es_orden = descubrimiento.partir(topic)
        if es_orden:
            self.error = True
            self.mensaje = ("Ese topic es una orden que publica el propio panel, "
                            "no un aparato informando de su estado.")
            return
        tipo, clase = descubrimiento.proponer(senal)

        self.topic_elegido, self.nodo_slug, self.senal = topic, nodo, senal
        self.ficha_tipo = tipo
        self.ficha_clase = clase or "pir"
        self.ficha_nombre = senal.replace("_", " ").strip().capitalize()
        self.ficha_en_plano = False
        self.error, self.mensaje = False, ""

        # ¿Hay ya un nodo cuyo nombre dé este slug?
        existente = next(
            (n for n in nodes_store.read_all().get("nodes", [])
             if nodes_store.slugify(n.get("name", "")) == nodo), None)
        if existente:
            self.nodo_id = existente["id"]
            self.nodo_nombre = existente["name"]
            self.nodo_hay_que_crearlo = False
            self.nodo_ip = existente.get("ip", "")
        else:
            self.nodo_id = ""
            # El nombre por defecto es el slug tal cual: es el único que vuelve
            # a dar este mismo topic al recalcularlo.
            self.nodo_nombre = nodo
            self.nodo_hay_que_crearlo = True
            self.nodo_ip = ""
        self.paso = FICHA

    @rx.event
    def volver(self):
        self.paso = OIR
        self.error, self.mensaje = False, ""

    @rx.event
    def set_ficha_nombre(self, valor: str):
        self.ficha_nombre = valor

    @rx.event
    def set_ficha_tipo(self, valor: str):
        self.ficha_tipo = valor

    @rx.event
    def set_ficha_clase(self, valor: str):
        self.ficha_clase = valor

    @rx.event
    def set_nodo_nombre(self, valor: str):
        self.nodo_nombre = valor

    @rx.event
    def set_nodo_ip(self, valor: str):
        self.nodo_ip = valor

    @rx.event
    def toggle_en_plano(self, valor: bool):
        self.ficha_en_plano = valor

    @rx.var
    def resumen_topic(self) -> str:
        """Lo que se va a escuchar/ordenar de verdad, para poder compararlo con
        el hallazgo antes de guardar."""
        if not self.nodo_nombre or not self.senal:
            return ""
        return nodes_store.sensor_topic(self.nodo_nombre, self.senal)

    @rx.var
    def topic_cuadra(self) -> bool:
        return bool(self.resumen_topic) and self.resumen_topic == self.topic_elegido

    @rx.var
    def es_sensor(self) -> bool:
        return self.ficha_tipo == "sensor"

    # ── Paso 3: guardar ──────────────────────────────────────────────────
    @rx.event
    async def guardar(self):
        if (no := await permisos.denegar(self, permisos.AJUSTES)):
            yield no
            return
        nombre = (self.ficha_nombre or "").strip()
        if not nombre:
            self.error, self.mensaje = True, "Ponle un nombre."
            return
        if not self.senal:
            self.error, self.mensaje = True, "Ese topic no trae ninguna señal."
            return

        # LA comprobación: el alta recalcula el topic, así que si lo que saldría
        # no es lo que se ha oído, esto no funcionaría y no se guarda.
        esperado = nodes_store.sensor_topic(self.nodo_nombre, self.senal)
        if esperado != self.topic_elegido:
            self.error = True
            self.mensaje = (
                f"Con el nombre de nodo «{self.nodo_nombre}» el panel escucharía "
                f"«{esperado}», pero lo que se ha oído es «{self.topic_elegido}». "
                f"Cámbiale el nombre al nodo para que coincida — si no, se daría "
                f"de alta y no se movería nunca."
            )
            return

        try:
            node_id, node_name = self.nodo_id, self.nodo_nombre
            if self.nodo_hay_que_crearlo:
                nodo = nodes_store.add_node(self.nodo_nombre, (self.nodo_ip or "").strip())
                node_id, node_name = nodo["id"], nodo["name"]
                await audit.registrar(self, logs.SENSORES, "NODO_CREADO",
                                      f"{node_name} (modo instalador)", entidad=node_id)

            # Cada alta se apunta con la MISMA categoría y acción que usa la
            # pantalla de siempre (ver nodes/state.py): si el instalador
            # estrenara vocabulario, el filtro de Registros enseñaría dos
            # nombres para el mismo suceso.
            if self.ficha_tipo == "luz":
                creado = nodes_store.add_light(
                    nombre, node_id, node_name, self.senal,
                    show_on_floor=self.ficha_en_plano)
                categoria, accion, que = logs.LUCES, "LUZ_CREADA", "la luz"
            elif self.ficha_tipo == "puerta":
                creado = nodes_store.add_door(
                    nombre, node_id, node_name, self.senal,
                    show_on_floor=self.ficha_en_plano)
                categoria, accion, que = logs.PUERTAS, "PUERTA_CREADA", "la puerta"
            else:
                creado = nodes_store.add_sensor(
                    nombre, self.ficha_clase, node_id, node_name, self.senal,
                    show_on_floor=self.ficha_en_plano)
                categoria, accion, que = logs.SENSORES, "SENSOR_CREADO", "el sensor"

            await audit.registrar(self, categoria, accion,
                                  f"{nombre} · {self.topic_elegido} (modo instalador)",
                                  entidad=creado.get("id", ""))
            self.error = False
            self.mensaje = ""
            self.creado_texto = (
                f"Ya está {que} «{nombre}» en {node_name}, escuchando "
                f"{self.topic_elegido}."
            )
            self.paso = HECHO
        except Exception as e:
            self.error = True
            self.mensaje = f"No se pudo dar de alta: {e}"

    @rx.event
    def otro_mas(self):
        """Vuelve al paso 1 sin dejar de escuchar, para seguir con el siguiente
        aparato: instalar es repetir esto varias veces seguidas."""
        self.paso = OIR
        self.topic_elegido = ""
        self.creado_texto = ""
        self.error, self.mensaje = False, ""
        self._refrescar()
