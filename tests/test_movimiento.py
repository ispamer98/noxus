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
    return [c, _ajustes(), _ritmo(), _persona_o_luz(), _confirmacion_hog()]


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

    # La caducidad tiene que dar margen a varios disparos fallidos seguidos.
    c.cierto("la foto anterior caduca después de varios disparos",
             motor.CADUCIDAD_ANTERIOR > motor.DISPARO * 4)

    # Los disparos van solapados, así que el número 7 puede volver antes que el
    # 6. Comparar el 6 contra el 7 mediría el movimiento al revés.
    ojo3 = motor._Ojo("cam_prueba")
    c.revisar("el primer fotograma no llega tarde", ojo3.llega_tarde(1), False)
    ojo3.orden_anterior = 7
    c.revisar("el 6, que vuelve después del 7, se descarta",
              ojo3.llega_tarde(6), True)
    c.revisar("y el 7 repetido también", ojo3.llega_tarde(7), True)
    c.revisar("el 8 sí se mira", ojo3.llega_tarde(8), False)

    # Y que solapar sirva de algo: hay que disparar más a menudo de lo que
    # tarda una captura (1,4 s en esta casa), o no se gana nada.
    c.cierto("se dispara más a menudo de lo que tarda una captura",
             motor.DISPARO < 1.4)
    return c


def _persona_o_luz() -> Caso:
    """Lo que de verdad importa: una persona sí, la luz no.

    Estas son las cuatro formas en que esto avisaba sin motivo, y por las que se
    reescribió el comparador:

      · se enciende una lámpara            -> sube el brillo de todo
      · la cámara salta a infrarrojos      -> cambia el CONTRASTE de todo, no el
                                              brillo, así que igualar la media
                                              no lo cancelaba
      · grano del sensor con poca luz      -> muchas celdas sueltas repartidas
      · la escena entera cambia            -> nadie ocupa la imagen entera

    Y la que NO puede fallar en el otro sentido: alguien que aparece.
    """
    from PIL import Image
    import io as _io

    c = Caso("Movimiento: una persona sí, un cambio de luz no")

    quieta = _escena(semilla=11)

    def _ir(datos: bytes) -> bytes:
        """La misma escena como la ve la cámara en modo noche: se aplasta el
        contraste y se levanta el negro, dejando la media parecida."""
        im = Image.open(_io.BytesIO(datos)).convert("L")
        im = im.point(lambda v: int(v * 0.45 + 55))
        buf = _io.BytesIO()
        im.save(buf, format="JPEG", quality=75)
        return buf.getvalue()

    def _puntos_sueltos(datos: bytes, cuantos: int, semilla: int) -> bytes:
        """La misma escena salpicada de puntitos separados unos de otros.

        Suman bastante imagen cambiada, pero ninguno tiene cuerpo: es la forma
        del ruido nocturno y de la compresión, y lo que NO puede disparar. Van
        bien separados a propósito, que es lo que los distingue de una persona.
        """
        azar = random.Random(semilla)
        im = Image.open(_io.BytesIO(datos)).convert("L")
        pintor = ImageDraw.Draw(im)
        for _ in range(cuantos):
            x = azar.randrange(10, 300)
            y = azar.randrange(10, 220)
            pintor.rectangle([x, y, x + 7, y + 7], fill=azar.choice((5, 250)))
        buf = _io.BytesIO()
        im.save(buf, format="JPEG", quality=75)
        return buf.getvalue()

    # 1) El infrarrojo. Antes de igualar la ganancia, esto disparaba siempre.
    noche = mov.analizar(quieta, _ir(quieta), umbral=0.8)
    c.revisar("el salto a infrarrojos NO dispara", noche.hay, False)

    # 2) La lámpara.
    luz = mov.analizar(quieta, _escena(brillo=140, semilla=12), umbral=0.8)
    c.revisar("encender una luz NO dispara", luz.hay, False)

    # 3) Puntos sueltos repartidos: cambian celdas de sobra para superar el
    #    umbral SUMADAS, pero ninguna zona tiene cuerpo. Antes esto disparaba,
    #    porque lo que se miraba era el total.
    grano = mov.analizar(quieta, _puntos_sueltos(quieta, 30, 13), umbral=0.8)
    c.revisar("el ruido repartido NO dispara", grano.hay, False)
    c.cierto("y eso que sumado pasaría del umbral", grano.total >= 0.8)
    c.cierto("lo que lo salva es que ninguna mancha tiene cuerpo",
             grano.mancha < grano.total)
    c.revisar("con su motivo", grano.motivo, "solo ruido")

    # 4) La escena entera cambiada: nadie ocupa el cuadro completo.
    negro = _escena(brillo=10, ruido=2, semilla=14)
    entera = mov.analizar(quieta, negro, umbral=0.8)
    c.revisar("un cambio de escena entera NO dispara", entera.hay, False)

    # 5) Y lo que SÍ tiene que saltar: alguien de pie en el salón.
    persona = mov.analizar(quieta, _escena(figuras=[(150, 90, 205, 225)],
                                           semilla=15), umbral=0.8)
    c.revisar("una persona SÍ dispara", persona.hay, True)
    c.cierto("y se ve como una mancha con cuerpo", persona.mancha >= 0.8)
    c.revisar("con el motivo puesto", persona.motivo, "algo se ha movido")

    # 6) Alguien pequeño al fondo, que es el caso justo: tiene que seguir
    #    saltando con la sensibilidad alta.
    lejos = mov.analizar(quieta, _escena(figuras=[(250, 120, 275, 175)],
                                         semilla=16), umbral=0.8)
    c.revisar("alguien más lejos también dispara", lejos.hay, True)
    c.cierto("y deja una mancha menor que el de cerca",
             lejos.mancha < persona.mancha)
    return c


def _confirmacion_hog() -> Caso:
    """La segunda fase: confirmar con el detector de personas de OpenCV.

    No se prueba aquí que HOG reconozca una persona de verdad — los rectángulos
    de estas escenas no tienen la silueta ni la textura de un cuerpo, así que un
    detector entrenado con gente real no los reconoce, y fingir que sí sería una
    prueba falsa. Lo que sí se comprueba es el contrato: nunca revienta, y una
    escena sin nadie no la confunde con una persona."""
    c = Caso("Movimiento: confirmación con el detector de personas")

    vacia = _escena(semilla=20)
    c.revisar("una escena vacía no tiene persona", mov.hay_persona(vacia), False)

    for caso, datos in (("vacío", b""), ("basura", b"esto no es un jpeg")):
        c.revisar(f"un fotograma {caso} no revienta ni cuenta como persona",
                  mov.hay_persona(datos), False)
    return c
