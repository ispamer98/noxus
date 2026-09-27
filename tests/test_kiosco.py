"""La tablet de habitación: qué controles son de una estancia y qué puede hacer
un dispositivo con el rol `kiosco`.

Todo escribe en la casa temporal de ``tests.comun``: no toca los ficheros vivos
ni ningún aparato real.
"""
from tests.comun import Caso

from noxuscmmd.domains.auth import permisos, store
from noxuscmmd.domains.nodes import store as nodos


def _miembros_de_estancia() -> Caso:
    c = Caso("Una estancia junta sus luces con las entidades que se le añaden")
    sala = nodos.add_room("Sala de pruebas")
    c.revisar("sin miembros al crearla", nodos.referencias_estancia(sala["id"]), set())
    nodos.update_room(sala["id"], "Sala de pruebas",
                      ["doors:puerta_x", "ir_remotes:mando_x", "doors:puerta_x", "sin-dos-puntos"])
    refs = nodos.referencias_estancia(sala["id"])
    c.cierto("guarda las refs válidas y sin repetir",
             refs == {"doors:puerta_x", "ir_remotes:mando_x"})
    c.cierto("una ref de otra estancia no es miembro",
             not nodos.referencia_en_estancia(sala["id"], "doors:otra"))
    c.revisar("una estancia que no existe no tiene miembros",
            nodos.referencias_estancia("room_inexistente"), set())
    return c


def _limites_del_rol_kiosco() -> Caso:
    c = Caso("El rol kiosco solo hace lo mínimo y solo con estancia")
    sala = nodos.add_room("Habitación de prueba")
    store.alta("tablet1", nombre="Tablet", rol=store.KIOSCO)
    c.cierto("sin estancia vinculada no puede ni ver",
             not permisos.puede("tablet1", permisos.VER))
    store.actualizar("tablet1", kiosco_estancia=sala["id"])
    for cap, nombre in ((permisos.VER, "ver"), (permisos.LUCES, "luces"),
                        (permisos.PUERTAS, "puertas")):
        c.cierto(f"con estancia puede {nombre}", permisos.puede("tablet1", cap))
    c.cierto("no puede tocar los ajustes", not permisos.puede("tablet1", permisos.AJUSTES))
    c.cierto("no puede armar ni desarmar", not permisos.puede("tablet1", permisos.ARMAR))
    c.cierto("las cámaras son una concesión aparte y empiezan cerradas",
             not permisos.puede("tablet1", permisos.CAMARAS))
    store.actualizar("tablet1", kiosco_camaras=True)
    c.cierto("y se pueden conceder", permisos.puede("tablet1", permisos.CAMARAS))
    c.revisar("estancia_kiosco devuelve la suya", store.estancia_kiosco("tablet1"), sala["id"])
    return c


def _solo_su_habitacion() -> Caso:
    c = Caso("Una tablet solo controla lo de SU estancia")
    mia = nodos.add_room("Mi habitación")
    ajena = nodos.add_room("Habitación ajena")
    nodos.update_room(mia["id"], "Mi habitación", ["doors:mi_puerta"])
    nodos.update_room(ajena["id"], "Habitación ajena", ["doors:su_puerta"])
    store.alta("tablet2", nombre="Tablet 2", rol=store.KIOSCO)
    store.actualizar("tablet2", kiosco_estancia=mia["id"])
    c.cierto("un control de su estancia, permitido",
             permisos.entidad_permitida("tablet2", "doors:mi_puerta"))
    c.cierto("el de otra habitación, no",
             not permisos.entidad_permitida("tablet2", "doors:su_puerta"))
    c.cierto("uno que no existe, tampoco",
             not permisos.entidad_permitida("tablet2", "lights:fantasma"))
    store.alta("familiar1", nombre="Familiar", rol=store.FAMILIA)
    c.cierto("quien no es kiosco no queda confinado",
             permisos.entidad_permitida("familiar1", "doors:su_puerta"))
    store.actualizar("familiar1", kiosco_estancia=mia["id"])
    c.revisar("el campo de estancia solo cuenta si el rol es kiosco",
            store.estancia_kiosco("familiar1"), "")
    return c


def _mural_de_camaras() -> Caso:
    from types import SimpleNamespace

    from noxuscmmd.domains.nodes.kiosco_state import KioscoState

    c = Caso("El mural de cámaras se recuerda por estancia")
    sala = nodos.add_room("Sala del mural")
    otra = nodos.add_room("Otra sala")
    c.revisar("sin guardar: reparto de 4 y ningún hueco",
              nodos.get_room_mural(sala["id"]), {"layout": "4", "slots": {}, "activo": False})
    nodos.set_room_mural(sala["id"], "6", {"0": "cam_fija", "5": "cam_ptz", "9": "fuera", "x": "mal"}, True)
    c.revisar("guarda solo huecos que caben en el reparto",
              nodos.get_room_mural(sala["id"]),
              {"layout": "6", "slots": {"0": "cam_fija", "5": "cam_ptz"}, "activo": True})
    c.revisar("otra estancia no lo comparte",
              nodos.get_room_mural(otra["id"])["slots"], {})
    nodos.set_room_mural(sala["id"], "3", {"0": "cam_fija"})
    c.revisar("un reparto no válido se ignora",
              nodos.get_room_mural(sala["id"])["layout"], "6")
    nodos.update_room(sala["id"], "Sala del mural", [])
    c.revisar("editar la estancia no borra el mural",
              nodos.get_room_mural(sala["id"])["slots"], {"0": "cam_fija", "5": "cam_ptz"})

    falso = SimpleNamespace(
        mural_layout="2", mural_celdas=[], _mural_visibles=["0"], _mural_nonce={"0": 3},
        _mural_slots={"0": "a"},
        _mural_camaras={"a": {"name": "Fija", "stream_url": "/cam/stream.html?src=a",
                              "playable": True}},
    )
    KioscoState._mural_pintar(falso)
    c.revisar("pinta un hueco por celda", len(falso.mural_celdas), 2)
    c.revisar("el hueco ocupado lleva el nombre y fuerza la recarga",
              (falso.mural_celdas[0]["nombre"], falso.mural_celdas[0]["url"],
               falso.mural_celdas[0]["visible"]),
              ("Fija", "/cam/stream.html?src=a&_r=3", True))
    c.cierto("el hueco libre sale vacío", falso.mural_celdas[1]["vacia"])
    return c


def _sirena_de_la_tablet() -> Caso:
    c = Caso("La sirena de la tablet se recuerda por estancia")
    sala = nodos.add_room("Sala de la sirena")
    c.revisar("por defecto: apagada, sirena, volumen alto",
              nodos.get_room_sirena(sala["id"]),
              {"activa": False, "sonido": "sirena", "volumen": "75"})
    nodos.set_room_sirena(sala["id"], True, "timbre", "100")
    c.revisar("guarda lo elegido", nodos.get_room_sirena(sala["id"]),
              {"activa": True, "sonido": "timbre", "volumen": "100"})
    nodos.set_room_sirena(sala["id"], False, "inventado", "100")
    c.revisar("un sonido desconocido no cambia nada",
              nodos.get_room_sirena(sala["id"])["sonido"], "timbre")
    nodos.set_room_sirena(sala["id"], False, "pitido", "999")
    c.revisar("un volumen fuera de la lista tampoco",
              nodos.get_room_sirena(sala["id"])["volumen"], "100")
    nodos.update_room(sala["id"], "Sala de la sirena", [])
    c.cierto("editar la estancia no borra la sirena",
             nodos.get_room_sirena(sala["id"])["activa"])
    return c


def _personalizar_estancia() -> Caso:
    from types import SimpleNamespace

    from noxuscmmd.domains.nodes.state import NodesState

    c = Caso("Cada estancia decide qué se ve en su pantalla")
    sala = nodos.add_room("Sala personalizable")
    sid = sala["id"]
    c.revisar("por defecto todo visible y baldosas normales",
              nodos.get_room_pantalla(sid),
              {"plano": True, "camaras": True, "sirena": True, "hora": True, "baldosas": "normales"})
    nodos.set_room_pantalla(sid, "plano", False)
    nodos.set_room_pantalla(sid, "baldosas", "enormes")
    nodos.set_room_pantalla(sid, "inventada", True)
    p = nodos.get_room_pantalla(sid)
    c.cierto("guarda una opción válida", p["plano"] is False)
    c.revisar("ignora un tamaño o una opción que no existen", p["baldosas"], "normales")
    nodos.set_room_pantalla(sid, "baldosas", "grandes")
    c.revisar("acepta un tamaño válido", nodos.get_room_pantalla(sid)["baldosas"], "grandes")

    nodos.update_room(sid, "Sala personalizable", ["doors:a", "doors:b", "doors:c"])
    nodos.set_room_miembro(sid, "doors:b", oculto=True)
    nodos.set_room_miembro(sid, "doors:c", etiqueta="  Puerta   del  patio ")
    nodos.set_room_orden(sid, ["doors:c", "doors:a", "doors:b", "doors:c", "mal"])
    sala_db = next(r for r in nodos.list_rooms() if r["id"] == sid)
    c.revisar("la etiqueta se normaliza",
              sala_db["personalizado"]["doors:c"]["etiqueta"], "Puerta del patio")
    c.revisar("el orden no repite ni admite refs inválidas", sala_db["orden"],
              ["doors:c", "doors:a", "doors:b"])
    nodos.set_room_miembro(sid, "doors:c", etiqueta="")
    c.cierto("quitar la etiqueta limpia la ficha",
             "doors:c" not in next(r for r in nodos.list_rooms() if r["id"] == sid)["personalizado"])
    nodos.update_room(sid, "Sala personalizable", ["doors:a", "doors:b", "doors:c"])
    c.cierto("editar miembros conserva lo personalizado",
             next(r for r in nodos.list_rooms() if r["id"] == sid)["personalizado"]["doors:b"]["oculto"])

    nodos.set_room_miembro(sid, "doors:c", etiqueta="Patio")
    sala_db = next(r for r in nodos.list_rooms() if r["id"] == sid)
    falso = SimpleNamespace(rooms=[sala_db], kiosco_room_id=sid,
                            kiosco_ref_ids=["doors:a", "doors:b", "doors:c"])
    falso._sala_kiosco = lambda: NodesState._sala_kiosco(falso)
    items = [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}, {"id": "c", "name": "C"},
             {"id": "z", "name": "Ajena"}]
    vistos = NodesState._miembros_kiosco(falso, "doors", items)
    c.revisar("la tablet oculta lo oculto, renombra, ordena y no cuela ajenos",
              [(i["id"], i["name"]) for i in vistos], [("c", "Patio"), ("a", "A")])
    return c


def ejecutar() -> list[Caso]:
    return [_miembros_de_estancia(), _limites_del_rol_kiosco(), _solo_su_habitacion(),
            _mural_de_camaras(), _sirena_de_la_tablet(), _personalizar_estancia()]
