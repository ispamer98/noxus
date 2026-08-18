"""
Qué elementos están abiertos ahora mismo, resuelto en un solo sitio.

Antes cada pantalla lo calculaba a su manera y ninguna coincidía con las
otras. El armado clásico (SecurityState.obtener_abiertos) recorría TODOS los
sensores de registry.binary_sensors() y sacaba el nombre de registry.DEVICES,
lo que provocaba las tres cosas raras que se veían en el registro de armado:

- Nombres que ya no existían: DEVICES se construye una vez al importar el
  módulo, así que un sensor renombrado desde la web seguía apareciendo con el
  nombre viejo hasta reiniciar el panel.
- Sensores aislados: aislar uno significa "la alarma hace como si no
  existiera", pero aquel listado no miraba la marca, así que salían igual.
- Sensores de otros grupos: al armar el grupo principal se listaba lo abierto
  de TODA la casa, perteneciera o no a ese grupo. Y al revés, los sensores
  dados de alta desde la web no salían nunca, porque solo se miraban los de
  fábrica.

Aquí se lee siempre del disco (nodos_dinamicos.json), que es donde de verdad
viven los nombres y los estados en vivo, y se aplican los mismos descartes
para todos: ocultos, aislados y los que ya no existen.
"""
from ..devices import registry
from ..nodes import store as nodes_store
from . import groups_store


def _nombres_actuales() -> dict[str, str]:
    """id -> nombre de AHORA de cada sensor que existe, de fábrica o dado de
    alta desde la web. Que un id no esté aquí significa que ese sensor se
    borró: puede seguir apuntado como miembro de un grupo (los miembros se
    guardan denormalizados) y por eso hay que comprobarlo, o el registro
    acabaría nombrando cosas que ya no están."""
    datos = nodes_store.read_all()
    return {
        **{s["id"]: s["name"] for s in datos["factory_sensors"]},
        **{s["id"]: s["name"] for s in datos["sensors"]},
    }


def _filtrar(ids, estados: dict, nombres: dict[str, str]) -> list[str]:
    descartados = registry.isolated_ids() | registry.hidden_ids()
    return [
        nombres[sid]
        for sid in ids
        if sid not in descartados and sid in nombres and estados.get(sid, False)
    ]


def abiertos_ahora() -> list[str]:
    """Todo lo que está abierto en la casa — para el contador "Abiertos ahora".
    No mira grupos a propósito: ahí la pregunta es qué hay abierto, no qué
    afecta a un armado concreto."""
    nombres = _nombres_actuales()
    return _filtrar(nombres.keys(), nodes_store.get_all_sensor_states(), nombres)


def abiertos_de_grupo(grupo: dict | None) -> list[str]:
    """Lo que se queda abierto al armar ESE grupo: solo sus miembros. Es lo
    que se apunta en el registro de armado, así que tiene que corresponder
    exactamente con lo que ese armado deja de vigilar."""
    if not grupo:
        return []
    nombres = _nombres_actuales()
    ids = [m["id"] for m in grupo.get("members", [])]
    return _filtrar(ids, nodes_store.get_all_sensor_states(), nombres)


def abiertos_del_principal() -> list[str]:
    """Miembros abiertos del grupo principal — el que mueve el botón de armado
    general de siempre."""
    return abiertos_de_grupo(groups_store.ensure_principal_group())


def nombres_de(ids: list[str]) -> list[str]:
    """Los nombres de AHORA de unos ids concretos.

    Para el registro de exclusiones: un sensor excluido y luego renombrado
    tiene que salir en el registro con el nombre que se le ve en pantalla, no
    con el que tenía cuando se excluyó. Uno que ya no existe se dice tal cual
    en vez de callarlo — que en el registro falte un excluido sería peor que
    verlo marcado como desaparecido."""
    nombres = _nombres_actuales()
    return [nombres.get(i, f"(borrado: {i})") for i in ids]


def con_id_de_grupo(grupo: dict | None) -> list[dict]:
    """Los miembros abiertos de un grupo, con su id — lo que necesita el
    diálogo de armado para poder excluirlos uno a uno. `abiertos_de_grupo` solo
    devuelve nombres porque es lo único que necesita el registro."""
    if not grupo:
        return []
    nombres = _nombres_actuales()
    estados = nodes_store.get_all_sensor_states()
    descartados = registry.isolated_ids() | registry.hidden_ids()
    return [
        {"id": m["id"], "nombre": nombres[m["id"]]}
        for m in grupo.get("members", [])
        if m["id"] not in descartados and m["id"] in nombres
        and estados.get(m["id"], False)
    ]


def detalle_armado(abiertos: list[str]) -> str:
    """Texto del registro al armar. Formato fijo: log_row lo reconoce por el
    prefijo para enseñar el desplegable con la lista."""
    return f"Armado con abiertos: {', '.join(abiertos)}" if abiertos else "Armado (sin abiertos)"
