"""modos.json — qué modos hay, cuál está puesto y qué reglas lanza cada uno."""
import json
import os
import secrets
import time
from pathlib import Path

ARCHIVO = Path(os.getenv("MODOS_FILE", "modos.json"))

# Los cuatro de partida. Nacen SIN reglas: un modo que al estrenarse apagara
# luces o armara la casa por su cuenta haría exactamente lo que nadie le ha
# pedido. Se estrena inerte y cada uno le cuelga lo que quiera.
_DE_FABRICA = [
    {"id": "fuera", "nombre": "Fuera", "icono": "log-out", "color": "#38bdf8",
     "descripcion": "No hay nadie en casa"},
    {"id": "en_casa", "nombre": "En casa", "icono": "house", "color": "#22c55e",
     "descripcion": "Hay alguien y se hace vida normal"},
    {"id": "noche", "nombre": "Noche", "icono": "moon", "color": "#a78bfa",
     "descripcion": "Todo el mundo durmiendo"},
    {"id": "vacaciones", "nombre": "Vacaciones", "icono": "palmtree",
     "color": "#f97316", "descripcion": "Varios días fuera"},
]


def _por_defecto() -> dict:
    return {
        "activo": "",
        "cambiado": 0.0,
        "por": "",
        "modos": [dict(m, reglas=[], orden=i) for i, m in enumerate(_DE_FABRICA)],
    }


def leer() -> dict:
    try:
        if not ARCHIVO.exists():
            datos = _por_defecto()
            escribir(datos)
            return datos
        datos = json.loads(ARCHIVO.read_text())
        datos.setdefault("activo", "")
        datos.setdefault("cambiado", 0.0)
        datos.setdefault("por", "")
        datos.setdefault("modos", [])
        for i, m in enumerate(datos["modos"]):
            m.setdefault("reglas", [])
            m.setdefault("orden", i)
            m.setdefault("color", "#38bdf8")
            m.setdefault("icono", "house")
            m.setdefault("descripcion", "")
        return datos
    except Exception as e:
        print(f"❌ Leyendo {ARCHIVO}: {e}")
        return _por_defecto()


def escribir(datos: dict) -> None:
    tmp = ARCHIVO.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, ARCHIVO)


def todos() -> list[dict]:
    return sorted(leer()["modos"], key=lambda m: m.get("orden", 0))


def get(modo_id: str) -> dict | None:
    return next((m for m in leer()["modos"] if m["id"] == modo_id), None)


def activo() -> str:
    """El id del modo puesto ahora, o "" si nunca se ha puesto ninguno.

    Vacío es un estado legítimo y no un fallo: una casa que nunca ha tocado
    los modos no está «en Fuera», está sin modo. Inventarle uno haría que las
    reglas con condición de modo se cumplieran solas."""
    return leer().get("activo", "")


def poner_activo(modo_id: str, por: str = "") -> bool:
    datos = leer()
    if not any(m["id"] == modo_id for m in datos["modos"]):
        return False
    datos["activo"] = modo_id
    datos["cambiado"] = time.time()
    datos["por"] = por
    escribir(datos)
    return True


def crear(nombre: str, icono: str = "house", color: str = "#38bdf8",
          descripcion: str = "") -> dict:
    datos = leer()
    modo = {
        "id": "modo_" + secrets.token_urlsafe(6),
        "nombre": (nombre or "").strip() or "Modo",
        "icono": icono or "house",
        "color": color or "#38bdf8",
        "descripcion": (descripcion or "").strip(),
        "reglas": [],
        "orden": len(datos["modos"]),
    }
    datos["modos"].append(modo)
    escribir(datos)
    return modo


def editar(modo_id: str, **campos) -> bool:
    datos = leer()
    for m in datos["modos"]:
        if m["id"] != modo_id:
            continue
        for clave in ("nombre", "icono", "color", "descripcion"):
            if clave in campos and campos[clave] is not None:
                valor = str(campos[clave]).strip()
                if clave == "nombre" and not valor:
                    continue
                m[clave] = valor
        if "reglas" in campos and isinstance(campos["reglas"], list):
            m["reglas"] = [str(r) for r in campos["reglas"]]
        escribir(datos)
        return True
    return False


def borrar(modo_id: str) -> None:
    datos = leer()
    quedan = [m for m in datos["modos"] if m["id"] != modo_id]
    if len(quedan) == len(datos["modos"]):
        return
    datos["modos"] = quedan
    if datos.get("activo") == modo_id:
        # Borrar el modo puesto deja la casa SIN modo, no en otro cualquiera:
        # elegir uno por él sería tomar una decisión sobre su casa que nadie ha
        # pedido.
        datos["activo"] = ""
    escribir(datos)


def alternar_regla(modo_id: str, regla_id: str) -> bool:
    datos = leer()
    for m in datos["modos"]:
        if m["id"] != modo_id:
            continue
        if regla_id in m["reglas"]:
            m["reglas"] = [r for r in m["reglas"] if r != regla_id]
        else:
            m["reglas"] = [*m["reglas"], regla_id]
        escribir(datos)
        return True
    return False


def limpiar_reglas_borradas(ids_vivos: set[str]) -> int:
    """Quita de los modos las reglas que ya no existen.

    Sin esto, un modo seguiría intentando ejecutar una regla borrada y soltando
    un error cada vez que se pulsa, sin que se vea de dónde sale."""
    datos = leer()
    quitadas = 0
    for m in datos["modos"]:
        antes = len(m["reglas"])
        m["reglas"] = [r for r in m["reglas"] if r in ids_vivos]
        quitadas += antes - len(m["reglas"])
    if quitadas:
        escribir(datos)
    return quitadas
