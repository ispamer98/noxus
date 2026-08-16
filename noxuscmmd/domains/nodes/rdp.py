"""
Escritorio remoto: se genera el fichero .rdp y se DESCARGA en el navegador de
quien pulsa el botón.

Antes las acciones "RDP" de los equipos lanzaban un script en el servidor
(subprocess.Popen("/home/spamer/portatil_to_pc.sh") — ficheros que ya ni
existen). Eso abría, como mucho, una ventana en el propio servidor, que es
justo donde nadie está mirando. Quien quiere el escritorio remoto es la
persona que tiene el panel abierto, en su Mac o en su portátil, así que lo
único que puede funcionar es mandarle a ELLA un .rdp: lo abre su cliente
(Windows App / Microsoft Remote Desktop en Mac, mstsc en Windows) y la
conexión sale de su equipo, no de aquí.

Hay dos formas de dárselo, y las dos hacen falta:

- evento_abrir: enlace rdp://, el cliente se abre solo. Es lo normal.
- evento_descarga: el .rdp como fichero. Es el plan B para cuando el sistema
  no tiene ningún programa asociado al esquema rdp:// — ahí el enlace no hace
  absolutamente nada y no hay manera de detectarlo desde el navegador, así que
  el botón de descargar tiene que seguir estando a la vista.

La IP que se pone en los dos casos es la del equipo tal cual está dado de alta
—en esta casa, la de Tailscale—, así que solo sirven dentro de la VPN: quien
lo abra sin estar en el tailnet no llega a ningún sitio.
"""
import base64
import json
from urllib.parse import quote

import reflex as rx

PUERTO = 3389

# Ajustes del .rdp. Se mandan siempre los mismos: son los que hacen que la
# sesión se vea bien en un Mac (resolución dinámica al redimensionar la
# ventana, portapapeles compartido) sin pedir nada raro que algunos clientes
# no entiendan y descarten el fichero entero.
_AJUSTES = (
    ("screen mode id", "i", "2"),          # pantalla completa
    ("use multimon", "i", "0"),
    ("dynamic resolution", "i", "1"),      # la sesión se adapta al redimensionar
    ("smart sizing", "i", "1"),
    ("session bpp", "i", "32"),
    ("audiomode", "i", "0"),               # el sonido suena en el equipo de quien se conecta
    ("redirectclipboard", "i", "1"),
    ("redirectprinters", "i", "0"),
    ("drivestoredirect", "s", ""),
    ("authentication level", "i", "2"),
    # A propósito NO se manda "prompt for credentials on client": con esa
    # opción puesta el cliente vuelve a pedir la contraseña en cada conexión y
    # el "recordar contraseña" del Mac deja de servir de nada. Sin ella, la
    # primera vez pregunta, se marca "recordar" y a partir de ahí entra sola
    # (Windows App la guarda en el Llavero, asociada a equipo + usuario).
    ("negotiate security layer", "i", "1"),
    ("networkautodetect", "i", "1"),
    ("bandwidthautodetect", "i", "1"),
    ("connection type", "i", "7"),
    ("compression", "i", "1"),
    ("videoplaybackmode", "i", "1"),
    ("autoreconnection enabled", "i", "1"),
    ("gatewayusagemethod", "i", "0"),
    ("administrative session", "i", "0"),
)


def puede_rdp(host: dict) -> bool:
    """Solo los equipos a los que se les ha puesto una cuenta de RDP a mano.

    Deliberadamente NO basta con que el equipo sea Windows. Aquí casi todo se
    maneja por SSH y no hay escritorios remotos montados: si el botón saliera
    en todo lo que es Windows, la mitad de los equipos enseñarían un botón que
    no lleva a ninguna parte. Rellenar el campo es lo que dice "este equipo sí
    tiene escritorio remoto de verdad"."""
    return bool((host.get("rdp_user") or "").strip())


def _direccion(ip: str, puerto: int) -> str:
    """El puerto solo se escribe si NO es el de siempre.

    Parece cosmético y no lo es: el cliente guarda las credenciales asociadas a
    la dirección tal cual está escrita, así que "100.98.98.2" y
    "100.98.98.2:3389" son dos conexiones distintas para él. Poniendo el puerto
    siempre, cada vez que se abría esto pedía la contraseña otra vez aunque ya
    estuviera guardada para ese mismo equipo, porque la que tenía guardada era
    la de la dirección sin puerto."""
    return ip if puerto == PUERTO else f"{ip}:{puerto}"


def construir(ip: str, usuario: str = "", puerto: int = PUERTO) -> str:
    """Contenido del .rdp. `usuario` puede ir vacío: entonces el cliente lo
    pregunta, que es lo correcto cuando el equipo lo comparten varias
    personas."""
    lineas = [f"full address:s:{_direccion(ip, puerto)}"]
    if usuario.strip():
        lineas.append(f"username:s:{usuario.strip()}")
    lineas += [f"{clave}:{tipo}:{valor}" for clave, tipo, valor in _AJUSTES]
    return "\r\n".join(lineas) + "\r\n"


def a_bytes(contenido: str) -> bytes:
    """UTF-16 LE con BOM, que es como escribe Windows los .rdp y lo que todos
    los clientes leen seguro. No es cosmético: si el nombre de la cuenta lleva
    algo fuera del ASCII, en UTF-8 pelado hay clientes que se comen el nombre
    de usuario o descartan el fichero entero sin decir por qué."""
    return b"\xff\xfe" + contenido.encode("utf-16-le")


def nombre_fichero(nombre_equipo: str, usuario: str = "") -> str:
    """Nombre "bonito" y sin sorpresas para la carpeta de descargas: solo
    letras, números, guiones y espacios. Un nombre de equipo con una barra
    dentro llegaría al navegador como una ruta."""
    crudo = f"{nombre_equipo} {usuario}".strip() if usuario.strip() else nombre_equipo
    limpio = "".join(c if (c.isalnum() or c in " -_") else "" for c in crudo).strip()
    return f"{(limpio or 'escritorio-remoto').replace(' ', '-')}.rdp"


def uri(ip: str, usuario: str = "", puerto: int = PUERTO) -> str:
    """Enlace rdp:// — abre el cliente directamente, sin pasar por la carpeta
    de descargas.

    El formato es el que documenta Microsoft para los clientes de macOS, iOS y
    Android: los mismos ajustes de un .rdp pegados detrás de "rdp://",
    separados por & y con la clave codificada ("full address" -> "full%20
    address"). Los dos puntos de la dirección van LITERALES, sin codificar: así
    es como aparece en la documentación y hay clientes que con %3A no parsean
    el puerto y acaban intentando conectar al equipo "100.98.98.2%3A3389".

    Solo se mandan dirección y usuario. Lo demás (pantalla, sonido,
    portapapeles) se queda a lo que tenga configurado el cliente, que es lo
    razonable: quien se conecta ya lo ha ajustado a su gusto en su Mac."""
    partes = [f"full%20address=s:{_direccion(ip, puerto)}"]
    if usuario.strip():
        partes.append("username=s:" + quote(usuario.strip(), safe=""))
    return "rdp://" + "&".join(partes)


# Clientes de escritorio remoto de macOS, del nuevo al viejo: "Windows App" es
# como se llama desde 2024 lo que antes era "Microsoft Remote Desktop".
CLIENTES_MAC = ("Windows App", "Microsoft Remote Desktop")


def comando_lanzar() -> str:
    """Orden de shell que levanta el cliente de escritorio remoto en el equipo
    lanzador, para mandarla por SSH.

    Levanta el CLIENTE y no una conexión concreta, y eso es a propósito aunque
    parezca que se queda corto. Windows App solo entra sin pedir la contraseña
    cuando la conexión está guardada DENTRO de la app, con su credencial
    asociada; todo lo que le llegue de fuera —un .rdp en el disco, un enlace
    rdp://— lo trata como una conexión de usar y tirar, pregunta la contraseña
    cada vez y no guarda nada. Comprobado sobre la propia base de datos de la
    app: después de una tanda de aperturas desde fuera seguía teniendo una sola
    conexión y una sola credencial, las de siempre.

    O sea que abrir la conexión desde aquí garantiza que pida la contraseña, y
    abrir la app garantiza que no la pida. Sale más a cuenta un doble clic en
    el PC ya guardado que escribir la clave cada vez.

    Los dos nombres se prueban en orden por si el Mac todavía tiene la app
    antigua; `open -a` además trae la ventana al frente si ya estaba abierta."""
    intentos = " || ".join(f'open -a "{nombre}"' for nombre in CLIENTES_MAC)
    return f"({intentos}) && echo LANZADO"


def evento_abrir(host: dict | None):
    """Abre el cliente de escritorio remoto en el equipo de quien pulsa. Es la
    acción principal del botón: descargar el .rdp obliga a ir a la carpeta de
    descargas y abrirlo a mano cada vez, y eso es justo lo que no quiere quien
    solo pretende meterse en su sesión.

    Se hace creando un <a> y pulsándolo, que parece un rodeo absurdo teniendo
    window.location, pero es que las otras dos vías fallan las dos:

    - window.location.href = "rdp://..." revienta con "SyntaxError: Invalid
      URL" en Safari. La culpa es del formato que pide Microsoft: después de
      "rdp://" viene "full%20address=s:100.98.98.2:3389", y el analizador de
      URLs del navegador lee eso como servidor + puerto, intenta interpretar
      "100.98.98.2:3389" como número de puerto y se rinde. Al asignar a
      location la URL se analiza YA, así que ni llega a intentarse abrir.
    - window.open lo bloquea el navegador como ventana emergente, porque para
      cuando llega la respuesta del servidor ya no cuenta como reacción
      directa al clic.

    El href de un <a>, en cambio, se guarda tal cual sin analizarlo, y al
    pulsarlo el navegador le pasa la dirección al sistema operativo. Así la
    URI llega intacta y con el formato exacto que documenta Microsoft."""
    if not host or not (host.get("ip") or "").strip():
        return None
    destino = uri(host["ip"].strip(), (host.get("rdp_user") or "").strip())
    return rx.call_script(
        "(() => {"
        "  const a = document.createElement('a');"
        f" a.href = {json.dumps(destino)};"
        "  document.body.appendChild(a);"
        "  a.click();"
        "  a.remove();"
        "})()"
    )


def evento_descarga(host: dict | None):
    """El rx.download listo para devolver desde un manejador, o None si el
    equipo no existe o no tiene IP. Se devuelve None en vez de lanzar para que
    quien llame pueda poner un mensaje de estado en lugar de romper el evento
    y dejar la UI esperando."""
    if not host or not (host.get("ip") or "").strip():
        return None
    usuario = (host.get("rdp_user") or "").strip()
    contenido = construir(host["ip"].strip(), usuario)
    return rx.download(
        data=a_bytes(contenido),
        filename=nombre_fichero(host.get("name") or host.get("id", "equipo"), usuario),
        mime_type="application/x-rdp",
    )
