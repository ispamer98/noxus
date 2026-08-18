"""inventario.json — lo que no se puede averiguar solo.

Dos cosas viven aquí y solo aquí:

1. Los campos que el panel no guarda de ningún elemento: modelo, ubicación,
   notas, y una IP o MAC puestas a mano para lo que no se descubre solo.
2. Los elementos que el panel NO controla pero están en la casa: el router, un
   switch, un lector de tarjetas, un repetidor. Se llaman «elementos sueltos»
   y existen porque un inventario que solo enseña lo que el panel gobierna no
   es un inventario de la instalación, es un reflejo del panel.

Todo lo demás —el nombre de un sensor, a qué nodo va, en qué pin— se lee de
nodos_dinamicos.json y NO se copia aquí: una segunda copia acabaría
discrepando de la primera.
"""
import json
import os
import secrets
import time
from pathlib import Path

ARCHIVO = Path(os.getenv("INVENTARIO_FILE", "inventario.json"))

# Lo que se puede escribir a mano de CUALQUIER elemento.
CAMPOS = ("modelo", "ubicacion", "notas", "ip_manual", "mac_manual")

_VACIO = {"campos": {}, "sueltos": []}


def leer() -> dict:
    try:
        if not ARCHIVO.exists():
            return json.loads(json.dumps(_VACIO))
        datos = json.loads(ARCHIVO.read_text())
        datos.setdefault("campos", {})
        datos.setdefault("sueltos", [])
        return datos
    except Exception as e:
        print(f"❌ Leyendo {ARCHIVO}: {e}")
        return json.loads(json.dumps(_VACIO))


def escribir(datos: dict) -> None:
    tmp = ARCHIVO.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, ARCHIVO)


# ── Campos a mano de un elemento que ya existe en el panel ───────────────
def campos_de(elemento_id: str) -> dict:
    return leer()["campos"].get(elemento_id, {})


def guardar_campos(elemento_id: str, **valores) -> None:
    datos = leer()
    ficha = datos["campos"].setdefault(elemento_id, {})
    for clave, valor in valores.items():
        if clave not in CAMPOS:
            continue
        valor = (valor or "").strip()
        if valor:
            ficha[clave] = valor
        else:
            # Un campo vacío se BORRA en vez de guardarse como "": así el
            # fichero solo tiene lo que de verdad se ha escrito, y se ve de un
            # vistazo qué está documentado y qué no.
            ficha.pop(clave, None)
    if not ficha:
        datos["campos"].pop(elemento_id, None)
    escribir(datos)


def limpiar_huerfanos(ids_vivos: set[str]) -> int:
    """Quita los campos de elementos que ya no existen.

    Sin esto, dar de baja un sensor y volver a crearlo con otro id dejaría el
    modelo y la ubicación del viejo colgando para siempre."""
    datos = leer()
    sobran = [i for i in datos["campos"] if i not in ids_vivos]
    for i in sobran:
        datos["campos"].pop(i, None)
    if sobran:
        escribir(datos)
    return len(sobran)


# ── Elementos sueltos (los que el panel no controla) ─────────────────────
def sueltos() -> list[dict]:
    return leer()["sueltos"]


def añadir_suelto(nombre: str, familia: str = "otros", **campos) -> dict:
    datos = leer()
    ficha = {
        "id": "suelto_" + secrets.token_urlsafe(6),
        "nombre": (nombre or "").strip() or "Sin nombre",
        "familia": familia,
        "created_at": time.time(),
    }
    for clave in CAMPOS:
        valor = (campos.get(clave) or "").strip()
        if valor:
            ficha[clave] = valor
    datos["sueltos"].append(ficha)
    escribir(datos)
    return ficha


def editar_suelto(suelto_id: str, **campos) -> bool:
    datos = leer()
    for ficha in datos["sueltos"]:
        if ficha["id"] != suelto_id:
            continue
        if "nombre" in campos:
            ficha["nombre"] = (campos["nombre"] or "").strip() or ficha["nombre"]
        if "familia" in campos and campos["familia"]:
            ficha["familia"] = campos["familia"]
        for clave in CAMPOS:
            if clave not in campos:
                continue
            valor = (campos[clave] or "").strip()
            if valor:
                ficha[clave] = valor
            else:
                ficha.pop(clave, None)
        escribir(datos)
        return True
    return False


def borrar_suelto(suelto_id: str) -> None:
    datos = leer()
    quedan = [f for f in datos["sueltos"] if f["id"] != suelto_id]
    if len(quedan) != len(datos["sueltos"]):
        datos["sueltos"] = quedan
        escribir(datos)
