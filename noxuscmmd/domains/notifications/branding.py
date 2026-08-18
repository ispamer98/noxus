"""
El nombre con el que se presenta la aplicación — el "De ..." que sale debajo
de cada notificación.

Ese texto no lo pone el aviso: lo pone el sistema operativo, y lo saca del
nombre de la aplicación instalada, que a su vez sale del manifest de la PWA. Es
decir, no se puede cambiar desde el contenido de la notificación por mucho que
se retoque el título — hay que cambiar el manifest.

Y el manifest es un fichero estático que se copia al compilar el frontend, así
que tocar solo assets/manifest.json no cambiaría lo que se sirve hasta la
siguiente compilación. Por eso al guardar se reescriben las dos cosas: el
original de assets/ (que es lo que sobrevive a un rebuild) y la copia que hay
publicada ahora mismo (que es lo que se descarga un teléfono hoy).

Aviso importante para quien lea esto esperando que el cambio se vea al
momento: NO se ve. Android y iOS leen el manifest al INSTALAR el acceso
directo y no vuelven a mirarlo; para que un dispositivo vea el nombre nuevo hay
que quitar el acceso directo de la pantalla de inicio y volver a añadirlo. Eso
es del sistema operativo y no hay forma de forzarlo desde aquí.
"""
import json
import os
from pathlib import Path

ARCHIVO = Path(os.getenv("AJUSTES_APP_FILE", "ajustes_app.json"))
POR_DEFECTO = "Noxus"

# El original y las copias publicadas. Se escriben todas las que existan: en
# desarrollo el frontend sirve desde .web/public y en producción desde el
# build, y no merece la pena adivinar en cuál estamos.
_MANIFESTS = (
    Path("assets/manifest.json"),
    Path(".web/public/manifest.json"),
    Path(".web/build/client/manifest.json"),
)

# Lo único que este módulo decide es el NOMBRE. Todo lo demás del manifest
# (colores, iconos, atajos del icono) vive en assets/manifest.json y se
# respeta tal cual.
#
# Antes había aquí una copia literal del resto del manifest, y eso era una
# trampa: cambiar assets/manifest.json parecía funcionar hasta que alguien
# renombraba la aplicación desde Ajustes, momento en el que esta copia —que
# nadie recordaba actualizar— pisaba el fichero bueno y devolvía el fondo
# blanco y los iconos viejos. Leyendo la base del propio fichero hay una sola
# fuente de verdad y el problema no puede repetirse.
_CAMPOS_DE_NOMBRE = ("name", "short_name", "description")

# Solo por si assets/manifest.json falta o está corrupto: sin esto, un fichero
# ilegible dejaría a la aplicación instalada sin iconos.
_BASE_RESPALDO = {
    "start_url": "/panel",
    "scope": "/",
    "display": "standalone",
    "background_color": "#05070a",
    "theme_color": "#05070a",
    "icons": [
        {"src": "/icono-192.png", "sizes": "192x192", "type": "image/png",
         "purpose": "any"},
        {"src": "/icono-512.png", "sizes": "512x512", "type": "image/png",
         "purpose": "any"},
        {"src": "/icono-maskable-512.png", "sizes": "512x512",
         "type": "image/png", "purpose": "maskable"},
    ],
}


def _base() -> dict:
    """El manifest actual sin los campos de nombre — lo que se conserva."""
    try:
        datos = json.loads(_MANIFESTS[0].read_text())
        if isinstance(datos, dict) and datos.get("icons"):
            return {k: v for k, v in datos.items() if k not in _CAMPOS_DE_NOMBRE}
    except Exception as e:
        print(f"⚠️ manifest ilegible ({e}); se usa el de respaldo")
    return dict(_BASE_RESPALDO)


def _leer() -> dict:
    try:
        return json.loads(ARCHIVO.read_text()) if ARCHIVO.exists() else {}
    except Exception:
        return {}


def nombre_app() -> str:
    return (_leer().get("nombre_app") or "").strip() or POR_DEFECTO


def descripcion_app() -> str:
    return (_leer().get("descripcion_app") or "").strip() or "Centro de control de la casa"


def escribir_manifests(nombre: str, descripcion: str) -> list[str]:
    """Reescribe el manifest allá donde esté. Devuelve las rutas tocadas."""
    contenido = json.dumps(
        {"name": nombre, "short_name": nombre, "description": descripcion,
         **_base()},
        indent=2, ensure_ascii=False,
    ) + "\n"
    escritos = []
    for ruta in _MANIFESTS:
        # Solo se escribe donde ya había uno: crear .web/... a mano si no
        # existe significaría que el frontend no está compilado, y dejar ahí un
        # fichero suelto no ayuda a nadie.
        if ruta == _MANIFESTS[0] or ruta.exists():
            try:
                ruta.parent.mkdir(parents=True, exist_ok=True)
                ruta.write_text(contenido)
                escritos.append(str(ruta))
            except Exception as e:
                print(f"❌ No se pudo escribir {ruta}: {e}")
    return escritos


def guardar(nombre: str, descripcion: str = "") -> str:
    """Guarda el nombre y deja los manifests al día. Devuelve el nombre que
    quedó (vacío = se vuelve al de fábrica)."""
    nombre = (nombre or "").strip() or POR_DEFECTO
    descripcion = (descripcion or "").strip() or descripcion_app()
    datos = _leer()
    datos["nombre_app"] = nombre
    datos["descripcion_app"] = descripcion
    ARCHIVO.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n")
    escribir_manifests(nombre, descripcion)
    return nombre
