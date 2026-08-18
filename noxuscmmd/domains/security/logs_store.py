"""
Persistencia del registro de eventos y del histórico: SQLite en modo WAL.

Esto era logs.json: una lista de diccionarios que se reescribía ENTERA en cada
evento, con `flock` alrededor y tope de 1.500 entradas. Funcionaba, pero tenía
dos techos que ya se estaban tocando:

  - Tres semanas de memoria. A los ~70 eventos diarios que genera la casa,
    1.500 entradas son veintitantos días. Suficiente para "qué pasó anoche",
    inútil para gráficas por hora y por día, o para deducir los horarios reales
    de las últimas semanas.
  - El coste de escribir crecía con lo ya guardado: abrir una puerta
    reserializaba los 286 KB del fichero completo.

Aquí no se borra nada (LOGS_MAX_DIAS = 0, ver MAX_DIAS). Al ritmo actual son
unos 5 MB al año, y apuntar un evento ya no cuesta más por tener más historia.

Cinco cosas que conviene saber antes de tocar esto:

1. WAL. El modo journal se guarda DENTRO del fichero, así que se pone una vez y
   sobrevive a los reinicios. Es lo que permite que el vigilante apunte un
   evento mientras tres pestañas leen el listado sin que nadie espere a nadie.
   Trae dos ficheros satélite, `historico.db-wal` y `historico.db-shm`: son
   parte de la base de datos, no basura suelta. Copiar el .db sin ellos da una
   copia SIN los últimos eventos — de ahí que exista `copia_a()`.

2. UNA CONEXIÓN POR OPERACIÓN. Reflex atiende cada evento en el hilo que le
   toca, y las conexiones de sqlite3 no se comparten entre hilos. Abrir y
   cerrar en cada llamada cuesta microsegundos con la base ya creada, y quita
   de encima toda una familia de fallos que solo aparecen bajo carga.

3. `ts` Y `timestamp` A LA VEZ, a propósito. `ts` (epoch, indexado) es para
   filtrar por fechas y para agrupar por hora o por día. El texto
   "2026-08-17 07:53:11" es lo que consume la interfaz entera, que lo parte por
   posiciones fijas. Se guarda tal cual en vez de derivarlo de `ts` para que una
   entrada antigua con la marca malformada siga saliendo como hasta ahora, en
   vez de desaparecer o salir con otra fecha.

4. EL ORDEN ES `id`, NO `ts`. El listado va por orden de llegada, que es lo que
   hacía el fichero. Ordenar por `ts` mandaría al principio o al final las
   entradas viejas cuya marca no se pudo interpretar (ts = 0), que hoy salen en
   su sitio. Por el mismo motivo, un filtro de fechas deja pasar siempre las de
   ts = 0: esconder un evento por un fallo de formato es peor que enseñarlo
   descolocado (misma regla que LogsState._coincide).

5. ESCRIBIR SIEMPRE CON `BEGIN IMMEDIATE`. Apuntar un evento lee el último para
   descartar repetidos, y entre esa lectura y la escritura no puede colarse
   nadie. Con la transacción por defecto (diferida) dos hilos pueden leer el
   mismo "último" y escribir los dos; `IMMEDIATE` coge el candado de escritura
   desde el principio, que es lo que hacía el `flock` de antes.

logs.json se queda intacto donde está: se importa una vez (ver `_importar`) y no
se vuelve a leer ni a escribir. Es la red para poder volver atrás.
"""
import json
import os
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

RUTA = Path(os.getenv("HISTORICO_DB", "historico.db"))

# El fichero de antes. Solo se lee una vez, para volcarlo en la tabla.
JSON_HEREDADO = Path(os.getenv("LOGS_FILE", "logs.json"))

# Días de historia que se conservan. 0 = todos, que es lo que se quiere: 5.3
# (gráficas por hora y día) y la simulación de presencia necesitan semanas
# reales, y el tamaño no es problema. Queda como variable para poder podar
# algún día sin tocar código.
MAX_DIAS = int(os.getenv("LOGS_MAX_DIAS", "0"))

# Cuánto espera una operación si otra tiene el candado de escritura. Diez
# segundos son una eternidad para una escritura de una fila: si se agota, el
# problema es otro y es mejor que se vea.
ESPERA = 10.0

VERSION_ESQUEMA = 3

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS eventos (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        INTEGER NOT NULL,
    timestamp TEXT    NOT NULL,
    categoria TEXT    NOT NULL DEFAULT '',
    accion    TEXT    NOT NULL DEFAULT '',
    usuario   TEXT    NOT NULL DEFAULT '',
    detalle   TEXT    NOT NULL DEFAULT '',
    grupo     TEXT    NOT NULL DEFAULT '',
    entidad   TEXT    NOT NULL DEFAULT '',
    -- Nombre del fichero del fotograma que se capturó al pasar esto, si se
    -- capturó (ver cameras/fotogramas.py). Solo el nombre, no la ruta: la
    -- carpeta se resuelve al leer, así que mover la carpeta no invalida el
    -- histórico. Vacío = no había cámara, o no se pudo.
    foto      TEXT    NOT NULL DEFAULT ''
);
-- Filtrar por fechas es lo que hace la pestaña Registros en cada recarga, y
-- agrupar por hora/día lo que harán las gráficas: los dos van por ts.
CREATE INDEX IF NOT EXISTS idx_eventos_ts ON eventos(ts);
CREATE TABLE IF NOT EXISTS meta (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
-- Series de números en el tiempo: temperatura de la CPU, equipos en línea. Van
-- en la MISMA base que los eventos porque son el mismo histórico de la misma
-- casa, y porque una sola base es una sola copia de seguridad, un solo modo WAL
-- y una sola migración. Quien las muestrea es infra/metricas.py; aquí solo se
-- guardan y se consultan.
--
-- Sin clave primaria a propósito: son muestras, no entidades. Dos lecturas del
-- mismo segundo no son un error que haya que impedir, y un índice único ahí
-- costaría en cada inserción para proteger de algo que no importa.
CREATE TABLE IF NOT EXISTS metricas (
    ts    INTEGER NOT NULL,
    clave TEXT    NOT NULL,
    valor REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metricas ON metricas(clave, ts);
"""

_CAMPOS = ("timestamp", "categoria", "accion", "usuario", "detalle", "grupo",
           "entidad")

# El candado protege la PREPARACIÓN (crear el esquema y volcar logs.json), que
# tiene que pasar una sola vez aunque arranquen dos hilos a la vez. Las
# operaciones normales no lo usan: de serializarlas ya se encarga SQLite.
_candado = threading.Lock()
_preparada = False


# ── Conexión ────────────────────────────────────────────────────────────────
def _abrir() -> sqlite3.Connection:
    """Conexión cruda, sin preparar la base. Uso interno."""
    cx = sqlite3.connect(RUTA, timeout=ESPERA, isolation_level=None)
    cx.row_factory = sqlite3.Row
    cx.execute(f"PRAGMA busy_timeout = {int(ESPERA * 1000)}")
    return cx


def _conectar() -> sqlite3.Connection:
    """Conexión lista para usar: la primera vez crea el esquema e importa el
    logs.json que hubiera."""
    global _preparada
    if not _preparada:
        with _candado:
            if not _preparada:
                _preparar()
                _preparada = True
    return _abrir()


def preparar() -> None:
    """Crea la base si no está e importa el logs.json que hubiera.

    Se hace sola en la primera operación, así que llamar a esto no es
    obligatorio; lo llama el arranque del panel (noxuscmmd.py) por dos motivos:
    la copia de seguridad de arranque se hace antes de que nadie toque nada, y un
    fichero que no existe no entra en la copia — sin esto, la primera copia tras
    el estreno se quedaría sin el registro. Y de paso la importación y cualquier
    queja suya salen en el log del servicio al arrancar, no a media tarde dentro
    del primer evento que pase."""
    _conectar().close()


def _preparar() -> None:
    RUTA.parent.mkdir(parents=True, exist_ok=True)
    cx = _abrir()
    try:
        # journal_mode se queda grabado en el fichero; synchronous es de la
        # conexión, pero con WAL el valor recomendado es NORMAL: aguanta que se
        # caiga el proceso (que es el riesgo real aquí) y solo cede ante un
        # apagón justo en el commit, a cambio de no hacer fsync por evento.
        cx.execute("PRAGMA journal_mode = WAL")
        cx.execute("PRAGMA synchronous = NORMAL")
        cx.executescript(_ESQUEMA)
        _migrar(cx)
        cx.execute(f"PRAGMA user_version = {VERSION_ESQUEMA}")
        _importar(cx)
    finally:
        cx.close()


def _migrar(cx: sqlite3.Connection) -> None:
    """Pone al día una base que se creó con un esquema anterior.

    Se mira qué columnas HAY de verdad y no el `user_version`. Es a propósito:
    el número lo escribe este mismo código y puede quedarse adelantado si algo
    falla en medio, y entonces una base a medias se daría por buena para
    siempre. `PRAGMA table_info` no puede mentir, y comprobar antes de añadir
    hace que esto se pueda ejecutar mil veces sin consecuencias.
    """
    columnas = {c["name"] for c in cx.execute("PRAGMA table_info(eventos)")}
    if "foto" not in columnas:
        # Un ALTER TABLE ADD COLUMN en SQLite no reescribe la tabla: es
        # instantáneo aunque haya cien mil filas.
        cx.execute("ALTER TABLE eventos ADD COLUMN foto TEXT NOT NULL DEFAULT ''")
        print("✅ Histórico: columna «foto» añadida")


# ── Importación del logs.json de antes ──────────────────────────────────────
def _importar(cx: sqlite3.Connection) -> int:
    """Vuelca logs.json en la tabla la primera vez, y solo esa vez.

    Se marca en `meta` en la MISMA transacción que las filas: si el proceso
    muere a mitad no queda medio histórico importado y marcado como hecho, se
    reintenta entero al arrancar. Y se exige además que la tabla esté vacía,
    porque un fichero de marca borrado a mano no debe poder duplicar el
    histórico entero.

    El import diferido de `logs` es para no cerrar el círculo: logs.py importa
    este módulo. Interpretar las entradas antiguas (deducirles la categoría,
    devolver el nombre a su sitio) es vocabulario del dominio y vive allí; aquí
    solo se guarda lo que salga de ello.
    """
    if cx.execute("SELECT 1 FROM meta WHERE clave = 'json_importado'").fetchone():
        return 0
    if cx.execute("SELECT 1 FROM eventos LIMIT 1").fetchone():
        # Base con datos y sin marca: se marca sin importar nada. Duplicar el
        # histórico es mucho peor que no traerse un fichero que probablemente
        # ya está dentro.
        cx.execute("INSERT INTO meta VALUES ('json_importado', 'tabla no vacía')")
        return 0

    from . import logs  # noqa: PLC0415 — ver el docstring

    entradas = []
    if JSON_HEREDADO.exists():
        try:
            with open(JSON_HEREDADO, encoding="utf-8") as f:
                contenido = f.read().strip()
            entradas = json.loads(contenido) if contenido else []
        except (OSError, ValueError) as e:
            print(f"⚠️ No se pudo leer {JSON_HEREDADO} para importarlo: {e}")
            return 0

    filas = []
    for entrada in entradas:
        if not isinstance(entrada, dict):
            continue
        e = logs.normalizar_heredada(entrada)
        filas.append((_epoch(e["timestamp"]), *(e[c] for c in _CAMPOS)))

    cx.execute("BEGIN IMMEDIATE")
    try:
        cx.executemany(
            f"INSERT INTO eventos (ts, {', '.join(_CAMPOS)}) "
            f"VALUES (?{', ?' * len(_CAMPOS)})",
            filas,
        )
        cx.execute("INSERT INTO meta VALUES ('json_importado', ?)",
                   (datetime.now().isoformat(timespec="seconds"),))
        cx.execute("COMMIT")
    except Exception:
        cx.execute("ROLLBACK")
        raise
    if filas:
        print(f"✅ Histórico: {len(filas)} eventos importados de {JSON_HEREDADO}")
    return len(filas)


def _epoch(timestamp: str) -> int:
    """Segundos de "2026-08-17 07:53:11". 0 si no se puede interpretar — ver la
    nota 4 de la cabecera."""
    try:
        return int(datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").timestamp())
    except (ValueError, TypeError):
        return 0


# ── Lectura ─────────────────────────────────────────────────────────────────
def _fila(fila: sqlite3.Row) -> dict:
    """Una fila con la forma que consume la interfaz. `ts` viene ya calculado
    (antes lo reparseaba cada pestaña en cada recarga) y `id` es la identidad
    de verdad del evento, para lo que venga a colgarse de él."""
    return {
        "id": fila["id"],
        "ts": float(fila["ts"]),
        "timestamp": fila["timestamp"],
        "categoria": fila["categoria"],
        "accion": fila["accion"],
        "usuario": fila["usuario"],
        "detalle": fila["detalle"],
        "grupo": fila["grupo"],
        "entidad": fila["entidad"],
        "foto": fila["foto"],
    }


def _rango(desde: float, hasta: float) -> tuple[str, list]:
    """Trozo de WHERE y sus parámetros. 0 en cualquiera de los dos = sin límite
    por ese lado."""
    partes, params = [], []
    if desde:
        partes.append("(ts = 0 OR ts >= ?)")
        params.append(int(desde))
    if hasta:
        partes.append("(ts = 0 OR ts <= ?)")
        params.append(int(hasta))
    return (" WHERE " + " AND ".join(partes)) if partes else "", params


def ultimos(limite: int | None = None, desde: float = 0.0,
            hasta: float = 0.0) -> list[dict]:
    """Los `limite` eventos más recientes del intervalo, MÁS RECIENTE PRIMERO.

    Sin `limite` devuelve el intervalo entero, así que solo se pide así cuando
    hace falta de verdad (exportar). Para pintar se pide siempre acotado."""
    where, params = _rango(desde, hasta)
    sql = f"SELECT * FROM eventos{where} ORDER BY id DESC"
    if limite is not None:
        sql += " LIMIT ?"
        params = [*params, limite]
    cx = _conectar()
    try:
        return [_fila(f) for f in cx.execute(sql, params)]
    finally:
        cx.close()


def recorrer(desde: float = 0.0, hasta: float = 0.0):
    """Igual que `ultimos()` sin límite, pero fila a fila y sin construir la
    lista en memoria. Es lo que usa la exportación a CSV: exporta el intervalo
    completo, y ese "completo" puede ser el histórico entero."""
    where, params = _rango(desde, hasta)
    cx = _conectar()
    try:
        for fila in cx.execute(
            f"SELECT * FROM eventos{where} ORDER BY id DESC", params
        ):
            yield _fila(fila)
    finally:
        cx.close()


def leer(limite: int | None = None, desde: float = 0.0,
         hasta: float = 0.0) -> list[dict]:
    """Como `ultimos()` pero del más antiguo al más reciente — el orden en el
    que devolvía las cosas logs.json, para lo que aún lo espera así."""
    return list(reversed(ultimos(limite, desde, hasta)))


def contar(desde: float = 0.0, hasta: float = 0.0) -> int:
    where, params = _rango(desde, hasta)
    cx = _conectar()
    try:
        return cx.execute(f"SELECT COUNT(*) FROM eventos{where}", params).fetchone()[0]
    finally:
        cx.close()


def ultima_accion(acciones: tuple[str, ...]) -> str:
    """La más reciente de esas acciones, o "" si no hay ninguna."""
    if not acciones:
        return ""
    huecos = ", ".join("?" * len(acciones))
    cx = _conectar()
    try:
        fila = cx.execute(
            f"SELECT accion FROM eventos WHERE accion IN ({huecos}) "
            f"ORDER BY id DESC LIMIT 1", acciones,
        ).fetchone()
        return fila["accion"] if fila else ""
    finally:
        cx.close()


def senal() -> str:
    """Marca que cambia si y solo si el registro ha cambiado.

    Existe para que las pestañas abiertas no relean el listado entero cada dos
    segundos "por si acaso": comparan esto, que son dos números, y solo releen
    cuando de verdad ha pasado algo. Va el recuento además del último id porque
    borrar (podar, restaurar una copia) quita filas sin crear ninguna."""
    cx = _conectar()
    try:
        maximo, total = cx.execute(
            "SELECT COALESCE(MAX(id), 0), COUNT(*) FROM eventos").fetchone()
        return f"{maximo}:{total}"
    finally:
        cx.close()


# ── Escritura ───────────────────────────────────────────────────────────────
def registrar(categoria: str, accion: str, usuario: str = "sistema",
              detalle: str = "", grupo: str = "", entidad: str = "") -> int:
    """Apunta un evento. Devuelve su id, o 0 si se descartó por repetido.

    El id hace falta para poder colgarle algo al evento DESPUÉS de haberlo
    apuntado, que es lo que hace la captura de la cámara: el evento se registra
    ya —eso no puede esperar a nada— y el fotograma se le engancha cuando
    llegue, segundos más tarde (ver adjuntar_foto y cameras/fotogramas.py).

    Repetido exacto e inmediato = ruido (un sensor que rebota, un botón pulsado
    dos veces). No se filtra nada más antiguo: dos eventos iguales separados en
    el tiempo son dos hechos distintos, y un registro que se los come deja de
    servir para lo que sirve.
    """
    ahora = time.time()
    fila = (
        int(ahora), time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ahora)),
        categoria, accion, usuario or "sistema", detalle, grupo, entidad,
    )
    cx = _conectar()
    try:
        cx.execute("BEGIN IMMEDIATE")
        try:
            ultimo = cx.execute(
                "SELECT accion, detalle, grupo FROM eventos "
                "ORDER BY id DESC LIMIT 1").fetchone()
            if (ultimo and ultimo["accion"] == accion
                    and ultimo["detalle"] == detalle
                    and ultimo["grupo"] == grupo):
                cx.execute("ROLLBACK")
                return 0
            cur = cx.execute(
                f"INSERT INTO eventos (ts, {', '.join(_CAMPOS)}) "
                f"VALUES (?{', ?' * len(_CAMPOS)})", fila,
            )
            nuevo = cur.lastrowid or 0
            cx.execute("COMMIT")
        except Exception:
            cx.execute("ROLLBACK")
            raise
    finally:
        cx.close()
    return nuevo


def adjuntar_foto(evento_id: int, nombre: str) -> bool:
    """Cuelga un fotograma de un evento ya apuntado. False si el evento no está.

    Se llama segundos después de registrar el evento, cuando la cámara por fin
    ha dado la imagen. Que sea un UPDATE y no parte del INSERT es justo lo que
    permite que el registro de la alarma no espere a la cámara."""
    cx = _conectar()
    try:
        cur = cx.execute("UPDATE eventos SET foto = ? WHERE id = ?",
                         (nombre, evento_id))
        return bool(cur.rowcount)
    finally:
        cx.close()


def purgar() -> int:
    """Borra lo anterior a MAX_DIAS y devuelve cuántas filas quitó. Con
    MAX_DIAS = 0 (lo puesto) no borra nada nunca."""
    if MAX_DIAS <= 0:
        return 0
    corte = int(time.time() - MAX_DIAS * 86400)
    cx = _conectar()
    try:
        # ts = 0 se salva: es una marca ilegible, no un evento antiguo.
        cur = cx.execute("DELETE FROM eventos WHERE ts > 0 AND ts < ?", (corte,))
        return cur.rowcount or 0
    finally:
        cx.close()


# ── Métricas: series de números en el tiempo ─────────────────────────────────
def anotar(clave: str, valor: float, cuando: float | None = None) -> None:
    """Guarda una muestra. Nunca levanta: una métrica perdida no es un problema.

    Quien llama decide si el valor merece guardarse. Es importante: la lectura de
    temperatura devuelve 0.0 cuando el SSH falla, y guardar ese cero pintaría una
    gráfica que dice que la Raspberry estuvo a cero grados. Un hueco en la línea
    es la verdad; un cero es una mentira."""
    try:
        cx = _conectar()
        try:
            cx.execute("INSERT INTO metricas (ts, clave, valor) VALUES (?, ?, ?)",
                       (int(cuando if cuando is not None else time.time()),
                        clave, float(valor)))
        finally:
            cx.close()
    except Exception as e:
        print(f"⚠️ No se pudo anotar la métrica {clave}: {e}")


def serie(clave: str, desde: float = 0.0, hasta: float = 0.0) -> list[dict]:
    """Las muestras de esa métrica, de la más antigua a la más reciente."""
    condiciones, params = ["clave = ?"], [clave]
    if desde:
        condiciones.append("ts >= ?")
        params.append(int(desde))
    if hasta:
        condiciones.append("ts <= ?")
        params.append(int(hasta))
    cx = _conectar()
    try:
        return [
            {"ts": float(f["ts"]), "valor": float(f["valor"])}
            for f in cx.execute(
                f"SELECT ts, valor FROM metricas "
                f"WHERE {' AND '.join(condiciones)} ORDER BY ts", params)
        ]
    finally:
        cx.close()


def serie_por_hora(clave: str, desde: float = 0.0) -> list[dict]:
    """La media de cada hora, para pintar días enteros sin mandar al navegador
    una muestra cada cinco minutos.

    Se agrupa por el texto de la hora local ('%Y-%m-%d %H') y no por aritmética
    sobre el epoch: así los tramos son las horas del reloj de la casa, con su
    cambio de hora incluido, y no bloques de 3.600 segundos desde 1970."""
    cx = _conectar()
    try:
        return [
            {"hora": f["hora"], "valor": float(f["media"]),
             "minimo": float(f["minimo"]), "maximo": float(f["maximo"])}
            for f in cx.execute(
                "SELECT strftime('%Y-%m-%d %H', ts, 'unixepoch', 'localtime') AS hora,"
                "       AVG(valor) AS media, MIN(valor) AS minimo, MAX(valor) AS maximo "
                "FROM metricas WHERE clave = ? AND ts >= ? "
                "GROUP BY hora ORDER BY hora", (clave, int(desde)))
        ]
    finally:
        cx.close()


def purgar_metricas(dias: int) -> int:
    if dias <= 0:
        return 0
    cx = _conectar()
    try:
        cur = cx.execute("DELETE FROM metricas WHERE ts < ?",
                         (int(time.time() - dias * 86400),))
        return cur.rowcount or 0
    finally:
        cx.close()


# ── Recuentos de eventos, para las gráficas ──────────────────────────────────
# QUÉ acciones cuentan como "una apertura" lo decide logs.py, que es el que sabe
# lo que significa cada acción; aquí solo se sabe contar. Así, una acción nueva
# se añade en un sitio y las gráficas la recogen sin tocar SQL.
def conteo_por_hora_del_dia(acciones: tuple[str, ...], desde: float = 0.0) -> list[dict]:
    """Cuántas veces pasó eso en cada hora DEL RELOJ (0..23), sumando todos los
    días del periodo. Es la forma de ver «a qué hora se abre esta puerta»."""
    if not acciones:
        return []
    huecos = ", ".join("?" * len(acciones))
    cx = _conectar()
    try:
        filas = {
            f["hora"]: f["cuantas"]
            for f in cx.execute(
                f"SELECT CAST(strftime('%H', timestamp) AS INTEGER) AS hora, "
                f"       COUNT(*) AS cuantas "
                f"FROM eventos WHERE accion IN ({huecos}) AND ts >= ? "
                f"GROUP BY hora", (*acciones, int(desde)))
        }
        # Las 24 horas siempre, con cero donde no hubo nada: una gráfica a la que
        # le faltan las horas vacías miente sobre la forma del día.
        return [{"hora": f"{h:02d}", "cuantas": filas.get(h, 0)} for h in range(24)]
    finally:
        cx.close()


def conteo_por_dia(acciones: tuple[str, ...], desde: float = 0.0) -> list[dict]:
    """Cuántas veces pasó eso cada día. Los días sin nada NO salen aquí: los
    rellena quien pinta, que es el que sabe qué rango está enseñando."""
    if not acciones:
        return []
    huecos = ", ".join("?" * len(acciones))
    cx = _conectar()
    try:
        return [
            {"dia": f["dia"], "cuantas": f["cuantas"]}
            for f in cx.execute(
                f"SELECT substr(timestamp, 1, 10) AS dia, COUNT(*) AS cuantas "
                f"FROM eventos WHERE accion IN ({huecos}) AND ts >= ? "
                f"GROUP BY dia ORDER BY dia", (*acciones, int(desde)))
        ]
    finally:
        cx.close()


# ── Qué hay disponible para medir ────────────────────────────────────────────
# Estas dos son lo que hace que el catálogo de la pestaña Métricas sea de verdad
# «todo lo que hay» en vez de una lista escrita a mano que se queda corta el día
# que se añade un evento nuevo: se le pregunta a la base qué ha registrado.
def acciones_registradas(desde: float = 0.0) -> list[dict]:
    """Cada acción que consta en el histórico, con su categoría y cuántas veces.

    De más frecuente a menos: al montar un panel, lo que más ha pasado es lo que
    más probablemente se quiera mirar."""
    where, params = _rango(desde, 0.0)
    cx = _conectar()
    try:
        return [
            {"accion": f["accion"], "categoria": f["categoria"],
             "cuantas": f["cuantas"]}
            for f in cx.execute(
                f"SELECT accion, categoria, COUNT(*) AS cuantas FROM eventos"
                f"{where} GROUP BY accion, categoria ORDER BY cuantas DESC",
                params)
        ]
    finally:
        cx.close()


def categorias_registradas(desde: float = 0.0) -> list[dict]:
    where, params = _rango(desde, 0.0)
    cx = _conectar()
    try:
        return [
            {"categoria": f["categoria"], "cuantas": f["cuantas"]}
            for f in cx.execute(
                f"SELECT categoria, COUNT(*) AS cuantas FROM eventos{where} "
                f"GROUP BY categoria ORDER BY cuantas DESC", params)
        ]
    finally:
        cx.close()


def claves_de_metricas() -> list[str]:
    """Las series que se han muestreado alguna vez."""
    cx = _conectar()
    try:
        return [f[0] for f in cx.execute(
            "SELECT DISTINCT clave FROM metricas ORDER BY clave")]
    finally:
        cx.close()


def conteo_por_hora_de_categoria(categorias: tuple[str, ...],
                                 desde: float = 0.0) -> list[dict]:
    """Como conteo_por_hora_del_dia pero filtrando por familia en vez de por
    acción. Hacen falta las dos: un panel puede querer «todo lo de Puertas» o
    «solo las aperturas»."""
    if not categorias:
        return []
    huecos = ", ".join("?" * len(categorias))
    cx = _conectar()
    try:
        filas = {
            f["hora"]: f["cuantas"]
            for f in cx.execute(
                f"SELECT CAST(strftime('%H', timestamp) AS INTEGER) AS hora, "
                f"       COUNT(*) AS cuantas FROM eventos "
                f"WHERE categoria IN ({huecos}) AND ts >= ? GROUP BY hora",
                (*categorias, int(desde)))
        }
        return [{"hora": f"{h:02d}", "cuantas": filas.get(h, 0)} for h in range(24)]
    finally:
        cx.close()


def conteo_por_dia_de_categoria(categorias: tuple[str, ...],
                                desde: float = 0.0) -> list[dict]:
    if not categorias:
        return []
    huecos = ", ".join("?" * len(categorias))
    cx = _conectar()
    try:
        return [
            {"dia": f["dia"], "cuantas": f["cuantas"]}
            for f in cx.execute(
                f"SELECT substr(timestamp, 1, 10) AS dia, COUNT(*) AS cuantas "
                f"FROM eventos WHERE categoria IN ({huecos}) AND ts >= ? "
                f"GROUP BY dia ORDER BY dia", (*categorias, int(desde)))
        ]
    finally:
        cx.close()


# ── Copias de seguridad ─────────────────────────────────────────────────────
def copia_a(destino: Path) -> None:
    """Deja en `destino` un .db suelto con TODO lo que hay ahora mismo.

    Con `VACUUM INTO` y no copiando el fichero: una copia a pelo del .db se
    dejaría fuera lo que aún viva en el -wal, y la copia saldría sin los
    últimos eventos justo cuando más falta hacen. Además sale compacto y sin
    ficheros satélite, así que la carpeta de la copia es un solo fichero por
    cosa, como con los JSON.

    Los fallos salen como OSError a propósito: para quien llama esto es un
    fichero que no se pudo escribir, igual que un shutil.copy2 que falla, y no
    tiene por qué saber que debajo hay un SQLite."""
    try:
        cx = _conectar()
    except sqlite3.Error as e:
        raise OSError(f"no se pudo abrir el histórico: {e}") from e
    try:
        cx.execute("VACUUM INTO ?", (str(destino),))
    except sqlite3.Error as e:
        raise OSError(f"no se pudo copiar el histórico: {e}") from e
    finally:
        cx.close()


def integro(ruta: Path) -> bool:
    """¿Ese fichero es una base de datos sana y con la tabla dentro?

    El equivalente de comprobar que un JSON parsea antes de dar una copia por
    buena. Se abre en modo lectura para no escribir ni un byte en la copia (una
    conexión normal le crearía su -wal al lado)."""
    try:
        cx = sqlite3.connect(f"{Path(ruta).resolve().as_uri()}?mode=ro", uri=True,
                             timeout=ESPERA)
    except sqlite3.Error:
        return False
    try:
        if cx.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            return False
        cx.execute("SELECT 1 FROM eventos LIMIT 1").fetchone()
        return True
    except sqlite3.Error:
        return False
    finally:
        cx.close()


def restaurar_desde(ruta: Path) -> None:
    """Deja el histórico igual que el de esa copia.

    Se vuelca DENTRO de la base que ya existe (API `backup` de sqlite3) en vez
    de sustituir el fichero: cambiar el .db por debajo dejaría al lado un -wal
    que pertenece a la base anterior, y eso no es una restauración, es una
    corrupción. Así además se hace en una transacción, y quien esté leyendo ve
    lo de antes o lo de después, nunca una mezcla."""
    try:
        origen = sqlite3.connect(f"{Path(ruta).resolve().as_uri()}?mode=ro",
                                 uri=True, timeout=ESPERA)
    except sqlite3.Error as e:
        raise OSError(f"no se pudo leer el histórico de la copia: {e}") from e
    try:
        destino = _conectar()
        try:
            origen.backup(destino)
        finally:
            destino.close()
    except sqlite3.Error as e:
        raise OSError(f"no se pudo restaurar el histórico: {e}") from e
    finally:
        origen.close()
