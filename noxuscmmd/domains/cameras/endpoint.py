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
from starlette.responses import FileResponse, JSONResponse, Response
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


async def autorizado_camaras(request):
    """Portero para el proxy inverso: `GET /api/camaras/autorizado`.

    No devuelve nada util. Solo dice `204` si quien pregunta puede ver camaras,
    y `401`/`403` si no. Lo llama el middleware **ForwardAuth** de Traefik antes
    de dejar pasar a `/cam`, que es go2rtc.

    POR QUE EXISTE. Hasta el 20/09/2026 el directo vivia en
    `cam.noxuscmmd.uk` y lo protegia **Cloudflare Access**. Al salir de
    Cloudflare, esa puerta desaparece, y go2rtc **no trae autenticacion propia
    que herede quien es cada uno**. Sin esto, publicar el directo seria dejar las
    camaras del interior de la casa colgando de internet con la URL por toda
    llave.

    Se reutiliza la sesion del panel a proposito: el directo pasa a estar en
    `panel.noxuscmmd.uk/cam`, o sea **el mismo origen**, asi que el navegador
    manda la cookie sin que haya que inventar nada. Ni segunda contrasena, ni
    token en la URL, ni otra lista de quien puede que.

    Pide **CAMARAS**, el mismo permiso que el mural y que los fotogramas. Un
    INVITADO entra al panel pero no ve el salon en directo.

    Responde 204 y no 200 porque no hay cuerpo que devolver, y asi ni siquiera
    hay que pensar en que se cachea.
    """
    id_dispositivo = _quien(request)
    if not id_dispositivo:
        return Response(status_code=401)
    if not permisos.puede(id_dispositivo, permisos.CAMARAS):
        return Response(status_code=403)
    return Response(status_code=204)


RUTAS = [
    Route("/api/fotograma/{nombre}", ver_fotograma, methods=["GET"]),
    # El portero del directo. GET y HEAD: ForwardAuth de Traefik usa el mismo
    # metodo que la peticion original, y el navegador manda HEAD para el video.
    Route("/api/camaras/autorizado", autorizado_camaras, methods=["GET", "HEAD"]),
]
