"""
Detección de movimiento comparando fotogramas de go2rtc.

Se piden dos fotogramas de la misma cámara separados un par de segundos y se
mira QUÉ ha cambiado. Ni la cámara ni go2rtc tienen que saber nada de esto.

LO DIFÍCIL NO ES VER QUE LA IMAGEN CAMBIA: es distinguir a alguien entrando en
el salón de la luz que se enciende, del amanecer, o de la cámara saltando a
infrarrojos por la noche. Todo eso cambia la imagen entera, y una primera
versión de esto avisaba con las cuatro cosas. Lo que separa una de otras:

  · UNA PERSONA ES UNA MANCHA. Ocupa una zona contigua de la imagen y deja el
    resto igual. Un cambio de luz mueve la imagen ENTERA a la vez.
  · IGUALAR LUZ Y GANANCIA. Antes de restar, la segunda imagen se lleva a la
    media y al contraste de la primera. Eso cancela que se encienda una lámpara
    o que la cámara cambie de exposición: si todo sube o baja a la vez, no
    queda diferencia. Con solo igualar la media no bastaba —el salto a
    infrarrojos no cambia el brillo, cambia el CONTRASTE de todo.
  · UN CAMBIO DEMASIADO GRANDE NO ES UNA PERSONA. Si cambia más de dos tercios
    de la imagen, no hay nadie: ha cambiado la escena (luz, infrarrojos, la
    cámara se ha movido). Eso se descarta en vez de avisar.

Y sobre lo pequeño: se reduce a 64x64 y se desenfoca, que es lo que quita el
grano del sensor y de la compresión —los que disparaban solos de noche— y lo
que hace que todo esto cueste microsegundos en vez de megabytes.

`analizar` sigue sin saber qué es una persona: solo dice «algo con cuerpo se ha
movido ahí», y eso también lo dice una lámpara que ilumina de forma desigual un
rincón del salón (el filtro de arriba solo cancela un cambio de luz UNIFORME).
Por eso `hay_persona` es una segunda fase, más cara, que solo se llama cuando
`analizar` ya encontró una mancha candidata: mira el fotograma de verdad — no
la resta entre dos — con el detector de peatones de OpenCV (HOG + SVM) y
confirma que lo que se movió tiene forma de persona antes de avisar.
"""
import io
from collections import namedtuple

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageFilter, ImageStat

# Tamaño al que se reduce todo antes de comparar. 64x64 = 4096 celdas: bastante
# para que una mancha tenga forma reconocible y para que el ruido de una celda
# suelta no cuente.
LADO = 64

# Cuánto tiene que cambiar una celda (0-255) para contar como cambiada. Por
# debajo de esto es ruido del sensor o de la compresión JPEG.
RUIDO = 28

# Porcentaje de imagen cambiada por encima del cual esto ya NO es alguien
# moviéndose: es la escena entera cambiando (se ha encendido la luz, ha entrado
# el modo noche, han movido la cámara). Una persona, incluso cerca, deja buena
# parte del cuadro intacta.
TOPE_CAMBIO_GLOBAL = 65.0

# Cuánto se deja corregir el contraste al igualar. Sin tope, una escena casi
# plana se amplificaría hasta convertir su propio grano en «movimiento».
GANANCIA_MAXIMA = 2.0

# Porcentaje de la imagen que tiene que ocupar la mancha para considerarla
# movimiento. Es el número que el usuario mueve con la sensibilidad.
UMBRAL_POR_DEFECTO = 2.0

# El resultado de mirar dos fotogramas:
#   hay    -> si se avisa
#   mancha -> % de imagen de la zona contigua más grande que ha cambiado
#   total  -> % de imagen cambiada en total, contando todo suelto
#   motivo -> por qué se decidió eso, para el registro y para depurar
Analisis = namedtuple("Analisis", "hay mancha total motivo")


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


def _igualar_luz(referencia: Image.Image, otra: Image.Image) -> Image.Image:
    """Lleva `otra` al mismo brillo Y al mismo contraste que la referencia.

    Las dos cosas, no solo el brillo. Encender una lámpara sube la media, y con
    igualar la media bastaba; pero la cámara saltando a infrarrojos deja la
    media parecida y cambia el CONTRASTE de toda la escena, y eso se colaba como
    movimiento. Igualando también la ganancia, un cambio de luz uniforme se
    cancela y lo que se ha movido de verdad sobrevive.
    """
    est_ref = ImageStat.Stat(referencia)
    est_otra = ImageStat.Stat(otra)
    media_ref, media_otra = est_ref.mean[0], est_otra.mean[0]
    desv_ref, desv_otra = est_ref.stddev[0], est_otra.stddev[0]

    ganancia = 1.0
    if desv_otra > 0.5:
        ganancia = desv_ref / desv_otra
        ganancia = max(1.0 / GANANCIA_MAXIMA, min(GANANCIA_MAXIMA, ganancia))
    if abs(ganancia - 1.0) < 0.02 and abs(media_ref - media_otra) < 0.5:
        return otra
    return otra.point(
        lambda v: max(0, min(255, int((v - media_otra) * ganancia + media_ref))))


def _mancha_mayor(marcadas: list[bool]) -> int:
    """Celdas de la zona CONTIGUA más grande que ha cambiado.

    Es lo que separa a alguien del ruido: una persona deja un borrón de celdas
    pegadas unas a otras, mientras que el grano de la cámara deja celdas
    sueltas repartidas por todo el cuadro. Contando solo la mancha más grande,
    lo primero cuenta y lo segundo no, aunque sumen lo mismo.

    Vecindad de 8 y recorrido con pila propia: sin recursión, que con 4096
    celdas todas cambiadas se saldría del límite de Python.
    """
    visto = bytearray(len(marcadas))
    mayor = 0
    for inicio in range(len(marcadas)):
        if not marcadas[inicio] or visto[inicio]:
            continue
        visto[inicio] = 1
        pila = [inicio]
        tamano = 0
        while pila:
            celda = pila.pop()
            tamano += 1
            fila, columna = divmod(celda, LADO)
            for df in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    f, c = fila + df, columna + dc
                    if 0 <= f < LADO and 0 <= c < LADO:
                        vecina = f * LADO + c
                        if marcadas[vecina] and not visto[vecina]:
                            visto[vecina] = 1
                            pila.append(vecina)
        if tamano > mayor:
            mayor = tamano
    return mayor


def analizar(antes: bytes, ahora: bytes,
             umbral: float = UMBRAL_POR_DEFECTO) -> Analisis:
    """Mira los dos fotogramas y decide si hay alguien.

    El `umbral` se aplica a la MANCHA, no al total de celdas cambiadas: da igual
    cuánta imagen haya cambiado en total si no hay ninguna zona con cuerpo.
    """
    a, b = _preparar(antes), _preparar(ahora)
    b = _igualar_luz(a, b)
    diferencias = ImageChops.difference(a, b).getdata()
    marcadas = [v >= RUIDO for v in diferencias]
    celdas = len(marcadas)

    total = round(100.0 * sum(marcadas) / celdas, 2)
    if total >= TOPE_CAMBIO_GLOBAL:
        # La escena entera. Nadie ocupa esto: luz, infrarrojos o la cámara
        # movida. Se devuelve para poder verlo en el log, pero no se avisa.
        return Analisis(False, total, total, "cambio de luz o de escena")

    mancha = round(100.0 * _mancha_mayor(marcadas) / celdas, 2)
    if mancha >= umbral:
        return Analisis(True, mancha, total, "algo se ha movido")
    return Analisis(False, mancha, total, "solo ruido")


# ── Compatibilidad ──────────────────────────────────────────────────────────
# Lo que había antes de que esto distinguiera manchas. Se mantiene porque es
# como se lee mejor desde fuera y porque las pruebas lo usan.
def hay_movimiento(antes: bytes, ahora: bytes,
                   umbral: float = UMBRAL_POR_DEFECTO) -> tuple[bool, float]:
    resultado = analizar(antes, ahora, umbral)
    return resultado.hay, resultado.mancha


def diferencia(antes: bytes, ahora: bytes) -> float:
    """Cuánto ha cambiado la imagen, en porcentaje de celdas (0-100). Sin
    interpretar nada: el número crudo."""
    a, b = _preparar(antes), _preparar(ahora)
    b = _igualar_luz(a, b)
    celdas = list(ImageChops.difference(a, b).getdata())
    movidas = sum(1 for v in celdas if v >= RUIDO)
    return round(100.0 * movidas / len(celdas), 2)


# ── Confirmación: ¿de verdad hay una persona? ───────────────────────────────
# Ancho al que se lleva el fotograma antes de buscarla. HOG necesita detalle
# real —no los 64x64 de comparar manchas—, pero pasado esto solo cuesta más
# CPU sin ganar acierto: 480 px de ancho deja de sobra sitio para que alguien
# de pie quepa en la ventana de detección (64x128) con margen.
ANCHO_HOG = 480

# El detector de peatones que trae OpenCV de fábrica (HOG + SVM lineal). Se
# crea una sola vez porque cargar el SVM no es gratis y esto se llama por
# fotograma. opencv-python-headless fijado por debajo de 5: la serie 5.x quitó
# HOGDescriptor de los bindings de Python.
_hog = cv2.HOGDescriptor()
_hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())


def hay_persona(datos: bytes) -> bool:
    """¿Hay una silueta de persona en este fotograma?

    Nunca levanta: un fotograma que no se puede decodificar cuenta como «no
    hay nadie», igual que el resto de este módulo trata lo que no puede leer.
    """
    if not datos:
        return False
    # A diferencia de PIL en _preparar, cv2.imdecode no lanza con un búfer
    # vacío: revienta con un AssertionError de C++. Basura que sí tiene bytes
    # (JPEG corrupto) devuelve None sin levantar, y eso ya lo cubre el `if`
    # de abajo.
    imagen = cv2.imdecode(np.frombuffer(datos, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if imagen is None:
        return False
    alto, ancho = imagen.shape
    if ancho > ANCHO_HOG:
        imagen = cv2.resize(imagen, (ANCHO_HOG, round(alto * ANCHO_HOG / ancho)))
    detecciones, _ = _hog.detectMultiScale(
        imagen, winStride=(8, 8), padding=(8, 8), scale=1.05)
    return len(detecciones) > 0
