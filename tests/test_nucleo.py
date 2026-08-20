"""
Lo que sostiene todo lo demás: que guardar en disco sea atómico, que los
permisos digan no a quien toca, y que los retardos de armado salgan bien.

Nada de esto acciona nada: se prueban las funciones que DECIDEN y las que
escriben en los ficheros de la casa de pruebas, nunca las que mandan por MQTT o
por SSH (ver comun.py).
"""
import json
import os
from pathlib import Path

from tests.comun import Caso

from noxuscmmd.domains.auth import permisos
from noxuscmmd.domains.nodes import store as nodes_store
from noxuscmmd.domains.security import retardos


def _escritura_atomica() -> Caso:
    c = Caso("Escritura atómica en disco")

    # El invariante: mientras se escribe, el fichero de verdad nunca se ve a
    # medias. Se comprueba que el destino queda completo y parseable y que no se
    # deja ningún .tmp tirado, que es la marca de una escritura interrumpida.
    ruta = Path(os.environ["RETARDOS_FILE"])
    retardos.poner_grupo("grupo_prueba", entrada=15, salida=30)
    c.cierto("el fichero existe tras escribir", ruta.exists())
    datos = json.loads(ruta.read_text())
    c.cierto("queda JSON válido", isinstance(datos, dict))
    c.revisar("no deja .tmp suelto", ruta.with_suffix(".tmp").exists(), False)

    # Y que lo escrito se relea igual, que es lo que falla cuando alguien
    # escribe con open() directamente y se queda a medias.
    conf = retardos.config_grupo("grupo_prueba")
    c.revisar("relee la entrada", conf["entrada"], 15)
    c.revisar("relee la salida", conf["salida"], 30)

    # nodos_dinamicos.json es el más grande y el que más manos tiene: se
    # comprueba que una lectura-escritura completa no lo rompe.
    antes = nodes_store.read_all()
    c.cierto("el almacén de nodos se lee", isinstance(antes, dict))
    c.cierto("trae las colecciones", "sensors" in antes and "lights" in antes)
    nodo = nodes_store.add_node("Nodo De Prueba", "10.0.0.99")
    despues = nodes_store.read_all()
    c.revisar("el alta se persiste",
              any(n["id"] == nodo["id"] for n in despues["nodes"]), True)
    nodes_store.delete_node(nodo["id"])
    c.revisar("la baja se persiste",
              any(n["id"] == nodo["id"] for n in nodes_store.read_all()["nodes"]),
              False)
    return c


def _permisos() -> Caso:
    c = Caso("Permisos por rol")
    # La tabla que gobierna la casa. Si alguna de estas cambia sin querer, un
    # invitado abre la puerta de la calle.
    esperado = {
        ("admin", permisos.AJUSTES): True,
        ("admin", permisos.PUERTAS): True,
        ("familia", permisos.PUERTAS): True,
        ("familia", permisos.ARMAR): True,
        ("familia", permisos.AJUSTES): False,
        ("invitado", permisos.LUCES): True,
        ("invitado", permisos.EQUIPOS): True,
        ("invitado", permisos.PUERTAS): False,
        ("invitado", permisos.ARMAR): False,
        ("invitado", permisos.CAMARAS): False,
        ("invitado", permisos.AJUSTES): False,
        ("pendiente", permisos.VER): False,
        ("bloqueado", permisos.VER): False,
    }
    for (rol, cap), debe in esperado.items():
        c.revisar(f"{rol} · {cap}", permisos.puede_rol(rol, cap), debe)
    return c


def _retardos() -> Caso:
    c = Caso("Retardos de entrada y salida")
    retardos.poner_grupo("g1", entrada=20, salida=45)
    retardos.poner_elemento("sensor_lento", entrada=60)

    c.revisar("retardo de salida del grupo", retardos.retardo_salida("g1"), 45)
    c.revisar("retardo de entrada del grupo",
              retardos.retardo_entrada("g1", "cualquiera"), 20)
    # El del elemento manda sobre el del grupo: una puerta concreta puede
    # necesitar más tiempo que el resto.
    c.revisar("el del elemento gana al del grupo",
              retardos.retardo_entrada("g1", "sensor_lento"), 60)
    c.revisar("un grupo sin configurar no inventa retardo",
              retardos.retardo_salida("grupo_que_no_existe"), 0)
    return c


def ejecutar() -> list[Caso]:
    return [_escritura_atomica(), _permisos(), _retardos(), _avisos(),
            _equipos_en_plano(), _quien_esta_en_linea()]


def _avisos() -> Caso:
    """Quién puede mandar un aviso a los móviles de la casa.

    Un aviso sale con la cara del panel, así que un invitado no lo manda; y la
    lista de destinatarios son los NOMBRES de los aparatos de la familia, que
    tampoco tiene por qué ver.
    """
    c = Caso("Permiso para avisar")
    c.cierto("admin puede avisar", permisos.puede_rol("admin", permisos.AVISAR))
    c.cierto("familia puede avisar", permisos.puede_rol("familia", permisos.AVISAR))
    c.revisar("invitado NO puede avisar",
              permisos.puede_rol("invitado", permisos.AVISAR), False)
    c.revisar("pendiente tampoco",
              permisos.puede_rol("pendiente", permisos.AVISAR), False)
    c.revisar("bloqueado tampoco",
              permisos.puede_rol("bloqueado", permisos.AVISAR), False)

    # Y que la negativa tenga texto propio: un "no" sin explicación es un fallo
    # que nadie sabe interpretar.
    c.cierto("la negativa tiene mensaje", bool(permisos.motivo(permisos.AVISAR)))
    return c


def _equipos_en_plano() -> Caso:
    """Que un equipo colocado en el plano se QUEDE colocado.

    Esto no es un detalle: `_normalizar_equipos` reconstruye cada equipo desde
    cero con las claves de CLAVES_EQUIPO —en cada lectura Y en cada escritura—,
    así que cualquier campo que no esté en esa lista desaparece solo, en
    silencio, a la primera relectura del fichero. Colocar equipos en el plano
    sin tocar esa lista habría «funcionado» hasta recargar la página.

    El segundo caso es el que se ve venir menos: editar el equipo desde su
    ficha pasa por `host_fields`, que devuelve un diccionario CERRADO sin
    campos de plano. Si la actualización pisara la ficha entera en vez de
    fusionarla, cambiarle el nombre a un equipo lo borraría del plano.
    """
    from noxuscmmd.domains.nodes import store

    c = Caso("Equipos colocados en el plano")

    equipo = store.add_host(**store.host_fields(
        name="Equipo de prueba", ip="10.0.0.254", user="alguien", mac="aa:bb:cc:dd:ee:ff"))
    try:
        c.cierto("un equipo nuevo nace sin sitio en el plano",
                 not equipo.get("posiciones") and not equipo.get("floor_top"))

        planos = store.read_all().get("planos") or []
        plano = planos[0]["id"] if planos else ""
        store.set_floor_position("hosts", equipo["id"], "40%", "60%", plano)
        store.set_floor_icon("hosts", equipo["id"], "monitor")

        def leer():
            return next(h for h in store.read_all()["hosts"] if h["id"] == equipo["id"])

        puesto = leer()
        c.revisar("se guarda dónde está", puesto["posiciones"].get(plano),
                  {"top": "40%", "left": "60%"})
        c.revisar("y con qué icono", puesto["floor_icon"], "monitor")

        # La normalización corre en cada lectura: si borrara los campos, esto
        # ya habría fallado arriba. Se relee otra vez por si acaso.
        c.revisar("sigue ahí al releer el fichero",
                  leer()["posiciones"].get(plano), {"top": "40%", "left": "60%"})

        # Y la trampa de verdad: editarlo por su ficha.
        store.update_host(equipo["id"], **store.host_fields(
            name="Equipo renombrado", ip="10.0.0.254", user="alguien"))
        tras_editar = leer()
        c.revisar("renombrarlo no lo saca del plano",
                  tras_editar["posiciones"].get(plano), {"top": "40%", "left": "60%"})
        c.revisar("ni le quita el icono", tras_editar["floor_icon"], "monitor")
        c.revisar("y el nombre sí cambia", tras_editar["name"], "Equipo renombrado")

        # Quitarlo del plano deja el equipo, no lo borra.
        store.set_floor_position("hosts", equipo["id"], None, None, plano)
        c.cierto("quitarlo del plano no borra el equipo",
                 leer()["name"] == "Equipo renombrado")
        c.revisar("y ya no tiene sitio", leer()["posiciones"].get(plano), None)
    finally:
        store.delete_host(equipo["id"])
    return c


def _quien_esta_en_linea() -> Caso:
    """Cuándo se apunta que un equipo se ha ido o ha vuelto.

    El fallo que hubo detrás: quién está en línea se comprobaba desde un bucle
    POR SESIÓN, con un global para que solo pingara el primero. Cuando los
    bucles de sesión pasaron a morir con su navegador, el global se quedaba
    puesto sin nadie detrás y NADIE volvía a pingar: el estado se congelaba
    hasta reiniciar el servicio, y un PC apagado seguía figurando en línea.
    Ahora pinga una tarea de proceso (infra/ping_motor.py) y aquí se comprueba
    su decisión, que es la parte con criterio.

    No se pinga nada: se le da el resultado a la función y se mira qué apunta.
    """
    import time as _time
    from noxuscmmd.domains.infra import ping_motor

    c = Caso("Quién está en línea")

    apuntados = []

    class _FalsoHost:
        name = "PC"
        class ssh:
            host = "100.98.98.2"

    original = ping_motor.audit.registrar_sistema
    reloj = {"t": 1000.0}
    original_reloj = _time.monotonic

    def _apuntar(categoria, accion, detalle="", grupo="", entidad=""):
        apuntados.append(accion)
        return 1

    ping_motor.audit.registrar_sistema = _apuntar
    ping_motor._PENDIENTE.clear()
    ping_motor._REGISTRADO.clear()
    _time.monotonic = lambda: reloj["t"]
    # El módulo importó `time` entero, así que basta con cambiarlo aquí.
    ping_motor.time.monotonic = lambda: reloj["t"]
    try:
        hosts = {"pc": _FalsoHost()}

        # La primera vuelta solo toma nota de por dónde anda cada equipo: si
        # apuntara, al arrancar el panel se registraría de golpe el estado de
        # todos como si acabase de cambiar.
        ping_motor._registrar_cambios_de_conexion({"pc": True}, hosts)
        c.revisar("la primera vuelta no apunta nada", apuntados, [])

        # Un ping perdido suelto NO es una desconexión: un equipo por wifi o al
        # otro lado de la VPN los pierde constantemente.
        ping_motor._registrar_cambios_de_conexion({"pc": False}, hosts)
        c.revisar("un ping perdido no se apunta", apuntados, [])

        reloj["t"] += 60
        ping_motor._registrar_cambios_de_conexion({"pc": False}, hosts)
        c.revisar("ni al minuto de estar sin responder", apuntados, [])

        # A los cinco minutos ya no es un parpadeo.
        reloj["t"] += 260
        ping_motor._registrar_cambios_de_conexion({"pc": False}, hosts)
        c.revisar("a los cinco minutos sí se apunta la desconexión",
                  apuntados, ["EQUIPO_DESCONECTADO"])

        # Y cuando vuelve basta un minuto: ahí no hay falsa alarma que evitar y
        # no interesa que un equipo ya de vuelta tarde cinco minutos en constar.
        reloj["t"] += 30
        ping_motor._registrar_cambios_de_conexion({"pc": True}, hosts)
        c.revisar("volver no se apunta a los 30 s", apuntados,
                  ["EQUIPO_DESCONECTADO"])
        # +70 sobre el instante en que VOLVIÓ (no sobre el de la
        # desconexión): la cuenta de estabilización arranca cuando cambia el
        # estado crudo, así que van 30+70 = 100 s de equipo respondiendo.
        reloj["t"] += 70
        ping_motor._registrar_cambios_de_conexion({"pc": True}, hosts)
        c.revisar("pasado el minuto sí", apuntados,
                  ["EQUIPO_DESCONECTADO", "EQUIPO_CONECTADO"])

        # Nunca dos seguidas del mismo signo, por mucho que se repita la vuelta.
        for _ in range(5):
            reloj["t"] += 400
            ping_motor._registrar_cambios_de_conexion({"pc": True}, hosts)
        c.revisar("no se repite lo ya apuntado", apuntados,
                  ["EQUIPO_DESCONECTADO", "EQUIPO_CONECTADO"])

        # Un parpadeo entero (se va y vuelve antes de los cinco minutos) no deja
        # rastro: es exactamente el ruido que llenaba el registro.
        reloj["t"] += 10
        ping_motor._registrar_cambios_de_conexion({"pc": False}, hosts)
        reloj["t"] += 120
        ping_motor._registrar_cambios_de_conexion({"pc": True}, hosts)
        reloj["t"] += 400
        ping_motor._registrar_cambios_de_conexion({"pc": True}, hosts)
        c.revisar("un parpadeo de dos minutos no deja rastro", apuntados,
                  ["EQUIPO_DESCONECTADO", "EQUIPO_CONECTADO"])
    finally:
        ping_motor.audit.registrar_sistema = original
        ping_motor.time.monotonic = original_reloj
        _time.monotonic = original_reloj
        ping_motor._PENDIENTE.clear()
        ping_motor._REGISTRADO.clear()
    return c
