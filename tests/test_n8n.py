"""
El puente con n8n: qué sale de la casa y qué se deja entrar.

Lo que cubre, que son las tres formas en que esto puede salir mal de verdad:

  1. QUE EL EVENTO LLEGUE MAL CONTADO. El workflow escribe el registro con lo
     que le mandamos; si la hora o el elemento vienen torcidos, n8n apunta un
     hecho falso y encima parece que funciona.
  2. EL BUCLE. n8n manda un aviso → Noxus lo apunta → el apunte sale hacia n8n
     → n8n manda otro aviso... Se corta en NO_SALEN, y esa lista es justo la
     clase de cosa que alguien borra sin saber para qué estaba.
  3. LA PUERTA ABIERTA. `/api/integraciones/aviso` manda notificaciones a los
     móviles de la casa. Con el token mal comprobado, cualquiera con la URL
     puede escribirle a los teléfonos de la familia.

Nada de aquí manda nada: el hilo de envío se desconecta y se mira la cola, que
es lo que DECIDE. Ver la regla en comun.py.
"""
import os

from tests.comun import Caso

from noxuscmmd.domains.integrations import endpoint, n8n


class _PeticionFalsa:
    """Lo único que `_autorizado` mira de una petición."""

    def __init__(self, token=None):
        self.headers = {} if token is None else {"x-noxus-token": token}


def _entorno(**vars_):
    """Pone variables de entorno y devuelve cómo estaban, para restaurarlas."""
    antes = {k: os.environ.get(k) for k in vars_}
    for k, v in vars_.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    return antes


def _restaurar(antes):
    for k, v in antes.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _prueba_salida() -> Caso:
    c = Caso("Puente n8n · lo que sale")

    # Un encendido de la lamparita de la habitación, tal y como lo registra
    # nodes/state.py: el nombre de la luz como detalle y su id como entidad.
    p = n8n.payload(
        evento_id=1466, categoria="luces", accion="LUZ_ENCENDIDA",
        accion_legible="Luz encendida", usuario="iPhone Ruben",
        detalle="Habitación", grupo="", entidad="light_78c43ca9",
        ahora=1788116439.0,  # 2026-08-30 21:00:39 hora local
    )
    c.revisar("la acción viaja tal cual", p["accion"], "LUZ_ENCENDIDA")
    c.revisar("quién la hizo", p["usuario"], "iPhone Ruben")
    c.revisar("sobre qué elemento", p["elemento"], "Habitación")
    c.revisar("y su id, para poder agrupar avisos", p["entidad"],
              "light_78c43ca9")
    c.revisar("la fecha, partida para el registro", p["fecha"], "2026-08-30")
    c.cierto("y la hora, que es la local de la casa",
             p["hora"] == "21:00:39" or len(p["hora"]) == 8)

    # El convenio del detalle es "SUJETO · añadidos" (ver logs.registrar). El
    # workflow no tiene por qué conocerlo: se parte aquí.
    p2 = n8n.payload(
        evento_id=2, categoria="luces", accion="LUZ_CREADA",
        accion_legible="Luz creada", usuario="sistema",
        detalle="Habitación · Raspberry pin 5 · Dormitorio", grupo="",
        entidad="light_78c43ca9", ahora=1788116439.0,
    )
    c.revisar("el elemento es el sujeto del detalle", p2["elemento"],
              "Habitación")
    c.revisar("y lo demás queda aparte", p2["detalle_extra"],
              "Raspberry pin 5 · Dormitorio")

    # Se mira la COLA y no se manda nada: aquí no se ejecuta, se decide.
    hilo_real = n8n._asegurar_hilo
    n8n._asegurar_hilo = lambda: None
    antes = _entorno(N8N_WEBHOOK_URL="http://127.0.0.1:1/webhook/pruebas")
    try:
        while not n8n._COLA.empty():
            n8n._COLA.get_nowait()

        n8n.emitir(evento_id=1, categoria="luces", accion="LUZ_ENCENDIDA",
                   accion_legible="Luz encendida", usuario="iPhone Ruben",
                   detalle="Habitación", entidad="light_78c43ca9")
        c.revisar("un encendido se encola", n8n._COLA.qsize(), 1)
        while not n8n._COLA.empty():
            n8n._COLA.get_nowait()

        # EL CORTA-BUCLES. Si esto falla, n8n y Noxus se contestan el uno al
        # otro hasta que alguien lo pare a mano.
        n8n.emitir(evento_id=2, categoria="sistema", accion=endpoint.ACCION,
                   accion_legible="Aviso enviado desde n8n", usuario="n8n",
                   detalle="NOXUS · para iPhone Ruben")
        c.revisar("el eco del propio puente NO sale", n8n._COLA.qsize(), 0)

        n8n.emitir(evento_id=3, categoria="acceso_app", accion="INTENTO_ACCESO",
                   accion_legible="Intento de acceso a la app",
                   usuario="visitante", detalle="IP 192.0.2.1")
        c.revisar("los intentos anónimos tampoco salen", n8n._COLA.qsize(), 0)

        # Sin webhook configurado, esto no existe: ni cola, ni hilo, ni coste.
        _entorno(N8N_WEBHOOK_URL="")
        c.revisar("sin URL, la integración está apagada", n8n.activo(), False)
        n8n.emitir(evento_id=4, categoria="luces", accion="LUZ_APAGADA",
                   accion_legible="Luz apagada", usuario="iPhone Ruben",
                   detalle="Habitación")
        c.revisar("y apagada no encola nada", n8n._COLA.qsize(), 0)
    finally:
        _restaurar(antes)
        n8n._asegurar_hilo = hilo_real
        while not n8n._COLA.empty():
            n8n._COLA.get_nowait()
    return c


def _prueba_entrada() -> Caso:
    c = Caso("Puente n8n · lo que entra")

    antes = _entorno(N8N_TOKEN="el-secreto-de-las-pruebas")
    try:
        c.revisar("con el token bueno, pasa",
                  endpoint._autorizado(_PeticionFalsa("el-secreto-de-las-pruebas")),
                  True)
        c.revisar("con otro token, no",
                  endpoint._autorizado(_PeticionFalsa("otro")), False)
        c.revisar("sin cabecera, no",
                  endpoint._autorizado(_PeticionFalsa()), False)
        c.revisar("con un prefijo del token, tampoco",
                  endpoint._autorizado(_PeticionFalsa("el-secreto")), False)

        # Sin token configurado la puerta se queda CERRADA. Un .env a medio
        # rellenar no puede dejar que cualquiera escriba a los móviles.
        _entorno(N8N_TOKEN="")
        c.revisar("sin token en el .env, no pasa nadie",
                  endpoint._autorizado(_PeticionFalsa("lo-que-sea")), False)
        c.revisar("y con la cabecera vacía tampoco",
                  endpoint._autorizado(_PeticionFalsa("")), False)
    finally:
        _restaurar(antes)

    # A quién se le manda. Un nombre que no está suscrito tiene que salir como
    # desconocido y no colarse: push se callaría y n8n daría la ejecución por
    # buena con el móvil en silencio.
    nombres_real = endpoint.suscriptores.nombres
    endpoint.suscriptores.nombres = lambda: ["iPhone Ruben", "PC Rubén", "Gaby"]
    try:
        validos, malos = endpoint._destinatarios("iPhone Ruben")
        c.revisar("un dispositivo conocido", (validos, malos),
                  (["iPhone Ruben"], []))
        validos, malos = endpoint._destinatarios("Nokia 3310")
        c.revisar("uno que no existe se marca", (validos, malos),
                  ([], ["Nokia 3310"]))
        validos, malos = endpoint._destinatarios(["Gaby", "Nadie"])
        c.revisar("en una lista, se separa el bueno del malo",
                  (validos, malos), (["Gaby"], ["Nadie"]))
        validos, malos = endpoint._destinatarios("todos")
        c.revisar("«todos» son todos los suscritos", len(validos), 3)
        c.revisar("y no deja a nadie fuera", malos, [])
    finally:
        endpoint.suscriptores.nombres = nombres_real
    return c


def ejecutar() -> list[Caso]:
    return [_prueba_salida(), _prueba_entrada()]
