"""
La ruta que sirve un fotograma guardado: `GET /api/fotograma/<nombre>`.

POR QUÉ UNA RUTA Y NO UN ESTÁTICO. Lo fácil sería escribir los JPEG dentro de
`assets/`, que Reflex ya publica, y apuntar el `<img>` ahí. Pero `assets/` se
sirve a quien lo pida, sin mirar quién es: cualquiera con la URL —y las URL son
adivinables, llevan la fecha y el número del evento— tendría la foto del interior
de la casa. Además `assets/` es parte del repositorio, que es público, así que un
despiste con `git add` publicaría las imágenes de verdad.

Así que las fotos viven fuera (`fotogramas/`, en .gitignore) y se piden por aquí,
con la MISMA cookie firmada que el resto del panel (domains/auth/sessions.py).
Mismo patrón que notifications/endpoint.py.

El nombre del fichero llega por la URL, o sea que lo escribe quien quiera:
`fotogramas.ruta()` solo acepta el formato exacto que genera `guardar()`, así que
un «../../etc/passwd» no pasa de ahí. La validación está en ese módulo y no aquí
a propósito — es la misma que hace falta en cualquier sitio que resuelva un
nombre, y repetirla es como se acaba olvidando en uno.
"""
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

from ..auth import permisos, sessions, store as auth_store
from . import fotogramas


def _quien(request) -> str:
    """Id del dispositivo según la cookie, o "" si no vale."""
    testigo = request.cookies.get(sessions.NOMBRE_COOKIE, "")
    id_dispositivo = sessions.verificar(testigo)
    if not id_dispositivo:
        return ""
    return "" if auth_store.dispositivo(id_dispositivo) is None else id_dispositivo


async def ver_fotograma(request):
    id_dispositivo = _quien(request)
    if not id_dispositivo:
        return JSONResponse({"ok": False, "mensaje": "No identificado."},
                            status_code=401)
    # CAMARAS, el mismo permiso que el directo. Una foto de hace un rato no
    # puede pedir menos que el mural: es la misma imagen del interior de la
    # casa, solo que de antes.
    #
    # Estuvo pidiendo VER, que es únicamente «puede entrar al panel», y eso
    # dejaba a un INVITADO pedir fotogramas del salón —justo lo que dice
    # auth/permisos.py que no puede hacer: «Mirar ya es acceso»—. Las URL
    # llevan fecha y número de evento, así que son de adivinar.
    if not permisos.puede(id_dispositivo, permisos.CAMARAS):
        return JSONResponse({"ok": False, "mensaje": "Sin acceso."},
                            status_code=403)

    ruta = fotogramas.ruta(request.path_params.get("nombre", ""))
    if ruta is None:
        # Nombre inválido y foto caducada dan lo mismo por fuera. No hay por qué
        # ayudar a distinguir "no existe" de "no te la doy".
        return JSONResponse({"ok": False, "mensaje": "Ese fotograma ya no está."},
                            status_code=404)
    return FileResponse(
        ruta, media_type="image/jpeg",
        # Se puede cachear en el navegador: el fichero NUNCA cambia (su nombre
        # lleva el instante y el evento). `private` para que no la guarde ningún
        # intermediario — esto no es un estático cualquiera.
        headers={"Cache-Control": "private, max-age=86400"},
    )


RUTAS = [Route("/api/fotograma/{nombre}", ver_fotograma, methods=["GET"])]
