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
    return [c, _ajustes()]


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
