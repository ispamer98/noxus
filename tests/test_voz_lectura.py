"""Contrato de los GET de voz: consulta autenticada y sin efectos secundarios."""
import asyncio
import hashlib
import json

from tests.comun import Caso

from noxuscmmd.domains.auth import permisos, sessions, store as auth_store
from noxuscmmd.domains.devices import voz
from noxuscmmd.domains.security import logs_store


class Peticion:
    def __init__(self, *, clave: str = "", query: dict | None = None,
                 path: dict | None = None):
        self.headers = {"x-noxus-clave": clave} if clave else {}
        self.query_params = query or {}
        self.path_params = path or {}


def _cuerpo(respuesta) -> dict:
    return json.loads(respuesta.body)


def _autenticacion_y_rol() -> Caso:
    c = Caso("API de voz de lectura: autenticación y rol")
    c.revisar("sin clave se rechaza", asyncio.run(voz.sensores_casa(Peticion())).status_code, 401)

    verificar_real = sessions.verificar_voz
    ficha_real = auth_store.dispositivo
    puede_real = permisos.puede
    try:
        sessions.verificar_voz = lambda _clave: "asistente_prueba"
        auth_store.dispositivo = lambda _id: {"nombre": "Asistente de prueba"}
        permisos.puede = lambda _id, _capacidad: False
        respuesta = asyncio.run(voz.eventos_casa(Peticion(clave="clave-prueba")))
        c.revisar("un rol sin VER se rechaza", respuesta.status_code, 403)
    finally:
        sessions.verificar_voz = verificar_real
        auth_store.dispositivo = ficha_real
        permisos.puede = puede_real
    return c


def _limites_y_lectura_pura() -> Caso:
    c = Caso("API de voz de lectura: límites y sin escrituras")
    autorizar_real = voz._autorizar_lectura
    consultar_real = logs_store.eventos_solo_lectura
    try:
        voz._autorizar_lectura = lambda _request, _ademas=None: ("asistente_prueba", None)
        llamadas = []

        def capturar(**kwargs):
            llamadas.append(kwargs)
            return []

        logs_store.eventos_solo_lectura = capturar
        respuesta = asyncio.run(voz.eventos_casa(Peticion(query={"n": "999"})))
        c.revisar("n se limita a 100", (respuesta.status_code, llamadas[0]["limite"]), (200, 100))
        llamadas.clear()
        respuesta = asyncio.run(voz.estado_alarma(Peticion(query={"n": "999"})))
        c.revisar("los eventos de alarma se limitan a 50",
                  (respuesta.status_code, llamadas[0]["limite"]), (200, 50))
        c.revisar("n inválido da 400", asyncio.run(
            voz.eventos_casa(Peticion(query={"n": "muchos"}))).status_code, 400)
    finally:
        voz._autorizar_lectura = autorizar_real
        logs_store.eventos_solo_lectura = consultar_real

    # La consulta real abre el histórico en mode=ro; su contenido no puede
    # cambiar por pedir eventos. Se mide el fichero temporal, nunca el vivo.
    antes = hashlib.sha256(logs_store.RUTA.read_bytes()).hexdigest()
    try:
        voz._autorizar_lectura = lambda _request, _ademas=None: ("asistente_prueba", None)
        respuesta = asyncio.run(voz.eventos_casa(Peticion(query={"n": "1"})))
        despues = hashlib.sha256(logs_store.RUTA.read_bytes()).hexdigest()
        c.revisar("consultar el histórico no lo escribe", (respuesta.status_code, despues), (200, antes))
    finally:
        voz._autorizar_lectura = autorizar_real
    return c


def _camaras_paradas() -> Caso:
    c = Caso("API de voz de lectura: cámara parada")
    autorizar_real = voz._autorizar_lectura
    leer_real = voz.nodes_store.read_all
    foto_real = voz._foto_go2rtc
    try:
        voz._autorizar_lectura = lambda _request, _ademas=None: ("asistente_prueba", None)
        voz.nodes_store.read_all = lambda: {"cameras": [
            {"id": "cam_prueba", "name": "Cámara de prueba", "kind": "go2rtc", "url": "prueba"},
        ]}

        async def parada(_src):
            return None, "La cámara está parada o no responde."

        voz._foto_go2rtc = parada
        respuesta = asyncio.run(voz.foto_camara(Peticion(path={"id": "cam_prueba"})))
        c.revisar("explica que la cámara está parada", (respuesta.status_code, _cuerpo(respuesta)["mensaje"]),
                  (503, "La cámara está parada o no responde."))
    finally:
        voz._autorizar_lectura = autorizar_real
        voz.nodes_store.read_all = leer_real
        voz._foto_go2rtc = foto_real
    return c


def _camaras_exigen_permiso() -> Caso:
    c = Caso("API de voz de lectura: cámaras exigen CAMARAS")
    quien_real, puede_real = voz._quien, voz.permisos.puede
    try:
        voz._quien = lambda _request, _cuerpo: ("asistente_prueba", "Asistente")
        voz.permisos.puede = lambda _id, capacidad: capacidad == voz.permisos.VER
        respuesta = asyncio.run(voz.camaras_casa(Peticion()))
        c.revisar("sin CAMARAS devuelve 403", respuesta.status_code, 403)
        voz.permisos.puede = lambda _id, capacidad: True
        _, error = voz._autorizar_lectura(Peticion(), voz.permisos.CAMARAS)
        c.revisar("con CAMARAS autoriza", error, None)
    finally:
        voz._quien, voz.permisos.puede = quien_real, puede_real
    return c


def ejecutar() -> list[Caso]:
    return [_autenticacion_y_rol(), _limites_y_lectura_pura(), _camaras_paradas(),
            _camaras_exigen_permiso()]
