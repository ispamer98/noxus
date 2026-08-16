"""
Catálogo de cámaras para el Mural de vídeo: junta las de fábrica (cam_fija,
cam_ptz) y las dadas de alta desde la web en UNA sola lista, cada una ya con
la URL de vídeo lista para meter en un iframe — el mural puede tener varias
en pantalla a la vez, así que conviene resolverlas todas de una sentada en
vez de una por una al pintar cada hueco.

Mismo criterio de negociación que domains/cameras/state.py (nunca la URL
cruda del manifiesto, siempre la página stream.html de go2rtc — un iframe
carga documentos HTML, no manifiestos de vídeo) y misma bifurcación por
`kind` que ui/dashboard/windows.py:_dynamic_camera_window para las cámaras
dinámicas — aquí se hace una vez por cámara, no una vez por hueco.
"""
from ..devices import registry
from ..nodes import store as nodes_store

_STREAM_MODES_PC = "webrtc,mse,hls,mp4"
_STREAM_MODES_MOBILE = "mse,hls,mp4"


def _modes(cam_mode: str) -> str:
    return _STREAM_MODES_MOBILE if cam_mode == "mobile" else _STREAM_MODES_PC


def catalogo_camaras(cam_mode: str = "pc") -> list[dict]:
    """[{"id", "name", "icon", "kind", "stream_url", "playable"}] — playable
    es False solo para RTSP (los navegadores no lo reproducen; el hueco
    enseña la URL para copiar, como ya hace la ventana flotante de cámara
    suelta)."""
    modo = _modes(cam_mode)
    salida: list[dict] = []

    for cid, cam in registry.visible_cameras().items():
        src = cid.replace("cam_", "")
        salida.append({
            "id": cid, "name": cam.name, "icon": getattr(cam, "icon", None) or "video",
            "kind": "factory",
            "stream_url": f"https://cam.noxuscmmd.uk/stream.html?src={src}&mode={modo}",
            "playable": True,
        })

    for c in nodes_store.read_all()["cameras"]:
        kind = c.get("kind", "embed")
        if kind == "go2rtc":
            url = f"https://cam.noxuscmmd.uk/stream.html?src={c.get('url', '')}&mode={modo}"
            playable = True
        elif kind == "rtsp":
            url = c.get("url", "")
            playable = False
        else:
            url = c.get("url", "")
            playable = True
        salida.append({
            "id": c["id"], "name": c["name"], "icon": c.get("icon") or "video",
            "kind": kind, "stream_url": url, "playable": playable,
        })

    return salida
