"""
Detección de movimiento comparando fotogramas de go2rtc.

No hay nada mágico: se piden dos fotogramas de la misma cámara separados unos
segundos y se mira cuánto ha cambiado la imagen. Ni la cámara ni go2rtc tienen
que saber nada de esto.

CÓMO SE COMPARA, y por qué así:
  · a gris y reducido a 48x48. Reducir es lo que quita el ruido de sensor y el
    grano de la compresión, que si no disparan solos de noche; y es lo que hace
    que comparar cueste microsegundos en vez de megabytes.
  · se IGUALA EL BRILLO de las dos antes de restarlas. Sin esto, encender una
    luz —o el amanecer, o el infrarrojo de la cámara al saltar— cambia la imagen
    entera y se cuenta como movimiento: con la primera versión de esto, subir el
    brillo de una escena quieta disparaba la alarma. Igualando la media, un
    cambio de luz uniforme se cancela y lo que se ha movido de verdad sobrevive.
  · se cuenta el PORCENTAJE DE CELDAS que cambian de verdad, no la diferencia
    media. Una persona cruzando ocupa poca imagen pero cambia mucho esas celdas;
    un cambio de luz general mueve la media entera sin que se haya movido nada.
    Contando celdas, lo primero se ve y lo segundo no.

LO QUE NO PRETENDE SER: esto no distingue una persona de un gato, ni de una
cortina, ni de una nube. Es una señal de «ahí se ha movido algo», que es lo que
hace falta para guardar un fotograma y avisar.
"""
import io

from PIL import Image, ImageChops, ImageFilter, ImageStat

# Tamaño al que se reduce todo antes de comparar. 48x48 = 2304 celdas: suficiente
# para que una persona a media distancia ocupe varias, y bastante para que el
# ruido de un píxel suelto no cuente.
LADO = 48

# Cuánto tiene que cambiar una celda (0-255) para contar como cambiada. Por
# debajo de esto es ruido del sensor o de la compresión JPEG.
RUIDO = 28

# Porcentaje de celdas cambiadas a partir del cual se considera movimiento. Es
# el número que el usuario mueve con la sensibilidad de la pantalla.
UMBRAL_POR_DEFECTO = 2.0


class NoSePuedeComparar(Exception):
    """Alguno de los dos fotogramas no es una imagen legible. Pasa a menudo con
    la cámara «fija», que contesta 200 con cero bytes."""


def _preparar(datos: bytes) -> Image.Image:
    if not datos:
        raise NoSePuedeComparar("fotograma vacío")
    try:
        imagen = Image.open(io.BytesIO(datos))
        imagen = imagen.convert("L").resize((LADO, LADO), Image.BILINEAR)
        # Un desenfoque suave más: mata el grano que sobrevive al reducido, que
        # es justo el que dispara falsas alarmas con poca luz.
        return imagen.filter(ImageFilter.GaussianBlur(radius=1))
    except NoSePuedeComparar:
        raise
    except Exception as e:
        raise NoSePuedeComparar(str(e)) from e


def _igualar_brillo(referencia: Image.Image, otra: Image.Image) -> Image.Image:
    """Sube o baja `otra` hasta que tenga el mismo brillo medio que la de
    referencia. Es lo que separa «se ha encendido la luz» de «se ha movido algo»."""
    media_ref = ImageStat.Stat(referencia).mean[0]
    media_otra = ImageStat.Stat(otra).mean[0]
    ajuste = media_ref - media_otra
    if abs(ajuste) < 0.5:
        return otra
    return otra.point(lambda v: max(0, min(255, int(v + ajuste))))


def diferencia(antes: bytes, ahora: bytes) -> float:
    """Cuánto ha cambiado la imagen, en porcentaje de celdas (0-100)."""
    a, b = _preparar(antes), _preparar(ahora)
    b = _igualar_brillo(a, b)
    cambio = ImageChops.difference(a, b)
    celdas = list(cambio.getdata())
    movidas = sum(1 for v in celdas if v >= RUIDO)
    return round(100.0 * movidas / len(celdas), 2)


def hay_movimiento(antes: bytes, ahora: bytes,
                   umbral: float = UMBRAL_POR_DEFECTO) -> tuple[bool, float]:
    cambio = diferencia(antes, ahora)
    return cambio >= umbral, cambio
