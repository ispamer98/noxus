"""
Qué avisos "de sistema" recibe cada dispositivo (movimiento, alarma,
desconocido) — el filtro por categoría de notifications/push.enviar_notificacion
y su guardado en dispositivos.json (auth/store.categorias_desactivadas).

No se prueba el envío real (pywebpush, suscriptores.json): eso tocaría avisar
de verdad a los móviles de la casa, justo lo que comun.py prohíbe. Lo que
importa aquí es la DECISIÓN — a quién se le habría filtrado el aviso—, y esa
decisión sale solo de dispositivos.json, que ya vive aislado en la casa de
pruebas.
"""
from tests.comun import Caso

from noxuscmmd.domains.auth import store
from noxuscmmd.domains.notifications import categorias
from noxuscmmd.domains.notifications.push import _categoria_bloqueada


def ejecutar() -> list[Caso]:
    c = Caso("Avisos: catálogo de categorías")
    c.cierto("hay al menos movimiento, alarma y desconocido",
             {categorias.MOVIMIENTO, categorias.ALARMA, categorias.DESCONOCIDO}
             <= set(categorias.CATEGORIAS))
    c.cierto("cada categoría tiene una etiqueta de verdad, no vacía",
             all(categorias.CATEGORIAS.values()))

    return [c, _preferencias_por_dispositivo(), _filtro_en_el_envio(),
            _icono_de_partida()]


def _icono_de_partida() -> Caso:
    """El icono que se PROPONE para un aparato según su nombre — lo que hace
    que un «iPhone Ana» nazca con forma de móvil en vez de con un icono
    genérico igual para todos. Se puede cambiar a mano después
    (AuthAdminState.elegir_icono); esto es solo el punto de partida."""
    from noxuscmmd.domains.auth.admin_state import (
        ICONOS_DISPOSITIVO, _icono_de_partida as propuesto)

    c = Caso("Dispositivos: el icono que se propone por el nombre")
    for nombre, esperado in (
        ("iPhone Ruben", "smartphone"),
        ("Portatil Ruben", "laptop"),
        ("Portátil de Marta", "laptop"),
        ("MacBook", "laptop"),
        ("PC Ruben", "monitor"),
        ("iPad de Gaby", "tablet"),
        ("TV del salon", "tv"),
    ):
        c.revisar(f"«{nombre}»", propuesto(nombre), esperado)

    # Lo que no se reconoce cae en el caso más común de una casa, y nunca en
    # un icono que no esté entre los elegibles: la rejilla no podría marcarlo.
    c.revisar("un nombre que no dice nada cae en móvil",
              propuesto("chisme raro"), "smartphone")
    c.revisar("y sin nombre, también", propuesto(""), "smartphone")
    c.cierto("todo lo que propone está entre los iconos elegibles",
             all(propuesto(n) in ICONOS_DISPOSITIVO
                 for n in ("iPhone", "PC", "iPad", "TV", "portatil", "")))
    return c


def _preferencias_por_dispositivo() -> Caso:
    c = Caso("Avisos: qué tiene cada aparato silenciado")

    store.alta("dev1", nombre="Móvil de prueba", rol=store.FAMILIA)
    c.revisar("recién dado de alta, no tiene nada silenciado",
              store.categorias_desactivadas("dev1"), [])

    store.actualizar("dev1", categorias_desactivadas=[categorias.MOVIMIENTO])
    c.revisar("guarda lo que se silencia",
              store.categorias_desactivadas("dev1"), [categorias.MOVIMIENTO])

    # Basura del fichero (una categoría que ya no existe) no puede dejar un
    # aviso bloqueado sin que se vea por qué en ningún sitio de la interfaz.
    store.actualizar("dev1", categorias_desactivadas=[categorias.ALARMA, "esto-ya-no-existe"])
    c.revisar("filtra categorías que no están en el catálogo",
              store.categorias_desactivadas("dev1"), [categorias.ALARMA])

    c.revisar("un dispositivo que no existe no tiene nada silenciado",
              store.categorias_desactivadas("no-existe"), [])
    return c


def _filtro_en_el_envio() -> Caso:
    """Lo que de verdad hace `enviar_notificacion` con la categoría: filtrar
    por NOMBRE del suscriptor, buscando su ficha en dispositivos.json."""
    c = Caso("Avisos: el filtro que aplica enviar_notificacion")

    store.alta("dev2", nombre="iPhone Prueba", rol=store.FAMILIA)
    store.actualizar("dev2", categorias_desactivadas=[categorias.MOVIMIENTO])

    c.revisar("con la categoría silenciada, se bloquea",
              _categoria_bloqueada("iPhone Prueba", categorias.MOVIMIENTO), True)
    c.revisar("otra categoría del mismo aparato sigue pasando",
              _categoria_bloqueada("iPhone Prueba", categorias.ALARMA), False)
    c.revisar("un nombre que no está en dispositivos.json no se bloquea "
              "—no puede perder avisos por no estar vinculado todavía",
              _categoria_bloqueada("Nadie con ese nombre", categorias.MOVIMIENTO), False)
    return c
