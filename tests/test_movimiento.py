"""
Detección de movimiento: que una imagen igual no dispare, que una figura que
cruza sí, y que un cambio de luz general NO se confunda con movimiento.

Las imágenes se generan aquí con PIL: no hace falta ninguna cámara, y así el
comportamiento se comprueba siempre igual en vez de depender de lo que se vea
por la ventana.
"""
import io
import random

from PIL import Image, ImageDraw

from tests.comun import Caso

from noxuscmmd.domains.cameras import movimiento as mov


def _escena(figuras=(), brillo=90, ruido=6, semilla=1) -> bytes:
    """Una escena de mentira, con grano como el de una cámara de verdad."""
    azar = random.Random(semilla)
    img = Image.new("L", (320, 240), brillo)
    pintor = ImageDraw.Draw(img)
    # Algo de decorado fijo, para que las dos imágenes no sean lisas.
    pintor.rectangle([20, 160, 300, 240], fill=max(0, brillo - 25))
    pintor.rectangle([40, 40, 90, 150], fill=min(255, brillo + 30))
    for caja in figuras:
        pintor.rectangle(caja, fill=min(255, brillo + 90))
    px = img.load()
    for y in range(0, 240, 2):
        for x in range(0, 320, 2):
            px[x, y] = max(0, min(255, px[x, y] + azar.randint(-ruido, ruido)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=75)
    return buf.getvalue()


def ejecutar() -> list[Caso]:
    c = Caso("Detección de movimiento")

    quieta_1 = _escena(semilla=1)
    quieta_2 = _escena(semilla=2)          # misma escena, otro grano
    persona = _escena(figuras=[(150, 90, 205, 225)], semilla=3)
    mas_luz = _escena(brillo=125, semilla=4)  # se enciende una luz: NO es movimiento

    hay, cambio_quieto = mov.hay_movimiento(quieta_1, quieta_2)
    c.revisar("una escena quieta no dispara", hay, False)

    hay, cambio_persona = mov.hay_movimiento(quieta_1, persona)
    c.cierto("alguien cruzando sí dispara", hay)
    c.cierto("y cambia bastante más que el grano",
             cambio_persona > cambio_quieto * 3)

    hay_luz, cambio_luz = mov.hay_movimiento(quieta_1, mas_luz)
    c.revisar("encender la luz no cuenta como movimiento", hay_luz, False)
    c.cierto("la persona mueve más celdas que el cambio de luz",
             cambio_persona > cambio_luz)

    # La sensibilidad tiene que servir de algo en los dos sentidos.
    c.cierto("con el umbral muy bajo, hasta el grano dispara",
             mov.hay_movimiento(quieta_1, quieta_2, umbral=0.0)[0])
    c.revisar("con el umbral altísimo no dispara ni una persona",
              mov.hay_movimiento(quieta_1, persona, umbral=99.0)[0], False)

    # La cámara «fija» de esta casa contesta 200 con cero bytes: no puede
    # reventar el bucle de vigilancia, tiene que ser un error tratable.
    for caso, datos in (("vacío", b""), ("basura", b"esto no es un jpeg")):
        try:
            mov.diferencia(quieta_1, datos)
            c.revisar(f"un fotograma {caso} protesta", "no protestó", "NoSePuedeComparar")
        except mov.NoSePuedeComparar:
            c.cierto(f"un fotograma {caso} protesta", True)

    c.cierto("comparar una imagen consigo misma da casi cero",
             mov.diferencia(quieta_1, quieta_1) == 0.0)
    return [c, _ajustes(), _ritmo()]


def _ajustes() -> Caso:
    """Lo que se guarda de la pantalla, y que arranque apagada."""
    from noxuscmmd.domains.cameras import movimiento_store as st

    c = Caso("Ajustes de la detección")
    # Sin fichero, apagada: nunca se pone a mirar cámaras por su cuenta.
    st.ARCHIVO.unlink(missing_ok=True)
    d = st.leer()
    c.revisar("arranca apagada", d["activada"], False)
    c.revisar("y sin cámaras", d["camaras"], [])
    c.revisar("solo con la casa armada por defecto", d["solo_armado"], True)

    st.escribir({"activada": True, "camaras": ["cam_ptz"], "umbral": 1.4,
                 "solo_armado": False})
    d = st.leer()
    c.revisar("guarda las cámaras", d["camaras"], ["cam_ptz"])
    c.revisar("guarda el umbral", d["umbral"], 1.4)
    c.revisar("guarda el «siempre»", d["solo_armado"], False)

    st.poner("activada", False)
    c.revisar("apagarla no borra lo demás",
              (st.leer()["activada"], st.leer()["camaras"]), (False, ["cam_ptz"]))

    # Un fichero ilegible no puede dejar la vigilancia encendida a ciegas.
    st.ARCHIVO.write_text("{roto")
    c.revisar("con el fichero roto queda apagada", st.leer()["activada"], False)
    st.ARCHIVO.unlink(missing_ok=True)
    return c


def _ritmo() -> Caso:
    """Cuándo mira el motor y con qué compara.

    Las dos reglas de aquí salieron de una noche de pruebas con la cámara de la
    habitación desconectada y la del salón contestando «0 bytes» a ratos:

      · una cámara caída no puede seguir pidiéndose en cada vuelta. Se comía los
        4 s enteros del temporizador y convertía una vuelta de 12 s en una de
        17-19, o sea que la cámara ROTA retrasaba la vigilancia de la BUENA.
      · no se compara contra un fotograma rancio. Si una cámara se salta varias
        vueltas, la foto guardada acaba siendo de hace minutos y lo que se mide
        ya no es movimiento, es que ha cambiado la luz. De ahí salió un aviso
        sin nada detrás.

    Se prueba la decisión, no la cámara: aquí no se pide ni una imagen.
    """
    from noxuscmmd.domains.cameras import movimiento_motor as motor

    c = Caso("Movimiento: a quién se le pide y con qué se compara")

    ojo = motor._Ojo("cam_prueba")
    c.revisar("una cámara sana no está caída", ojo.caida(), False)

    for _ in range(motor.FALLOS_PARA_RENDIRSE - 1):
        ojo.fallos += 1
    c.revisar("con fallos pero sin llegar al tope, sigue sana", ojo.caida(), False)
    ojo.fallos += 1
    c.revisar("al llegar al tope se da por caída", ojo.caida(), True)

    ahora = 10_000.0
    ojo.ultimo_intento = ahora
    c.revisar("recién intentada, no toca insistir",
              ojo.toca_reintentar(ahora + 1), False)
    c.revisar("a la mitad del minuto, tampoco",
              ojo.toca_reintentar(ahora + motor.REINTENTO_CAIDA / 2), False)
    c.revisar("pasado el minuto, se prueba otra vez",
              ojo.toca_reintentar(ahora + motor.REINTENTO_CAIDA), True)

    # El enfriamiento: tras avisar se calla un rato, para no mandar un aviso por
    # vuelta mientras alguien pasea por el salón.
    ojo2 = motor._Ojo("cam_prueba")
    c.revisar("sin haber avisado nunca, no está en enfriamiento",
              ojo2.en_enfriamiento(ahora), False)
    ojo2.ultimo_aviso = ahora
    c.revisar("justo después de avisar, se calla",
              ojo2.en_enfriamiento(ahora + 1), True)
    c.revisar("pasado el enfriamiento, vuelve a avisar",
              ojo2.en_enfriamiento(ahora + motor.ENFRIAMIENTO), False)

    # La caducidad se mide contra el periodo: si se cambia uno, el otro le sigue.
    c.cierto("la foto anterior caduca después de varias vueltas",
             motor.CADUCIDAD_ANTERIOR > motor.PERIODO)
    return c
