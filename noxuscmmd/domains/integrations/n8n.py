"""
La salida de la casa hacia n8n: cada evento que se apunta en el registro se
reenvía a un webhook.

POR QUÉ CUELGA DEL REGISTRO Y NO DE CADA ACCIÓN. Todo lo que pasa en la casa
—una luz que se enciende, una puerta que se abre, la alarma que se arma— ya
pasa por `security/logs.registrar`, y allí llega con las cinco cosas que hacen
falta para contar el hecho: cuándo, quién, qué, sobre qué y de qué familia.
Enganchar ahí significa que un evento nuevo sale hacia n8n el día que se
registra, sin que nadie tenga que acordarse de avisar también por aquí. Ir
acción por acción es como se acaba con la mitad de la casa fuera del flujo.

SALE TODO Y FILTRA n8n. No hay lista de acciones interesantes en este lado a
propósito: decidir qué importa es justo el trabajo del workflow, y una lista
aquí obligaría a tocar Python (y a reiniciar el panel) cada vez que se quiere
automatizar algo distinto. Lo único que no sale son los ecos del propio puente
—ver NO_SALEN.

NUNCA BLOQUEA NI FALLA HACIA ARRIBA. `logs.registrar` se llama desde el
vigilante de la alarma, desde los manejadores de la interfaz y desde el motor
de automatizaciones; que n8n esté caído, lento o a medio reiniciar no puede
retrasar ni un milisegundo el encendido de una luz. Por eso `emitir` solo deja
el evento en una cola y vuelve: el envío de verdad lo hace un hilo aparte, y
si la cola se llena se tiran los eventos nuevos en lugar de esperar. Un evento
perdido es un renglón que le falta a n8n; un `registrar` bloqueado es la casa
entera parada.

APAGADO SI NO SE CONFIGURA. Sin `N8N_WEBHOOK_URL` en el `.env` esto no hace
nada y no arranca ningún hilo, así que el panel funciona exactamente igual que
antes de que este módulo existiera.
"""
import json
import os
import queue
import threading
import time
import urllib.request

from dotenv import load_dotenv

load_dotenv()

# Cuántos eventos caben esperando a que n8n conteste. 500 son de sobra para
# aguantar un reinicio de n8n sin perder nada; lo que llegue con la cola llena
# se descarta, que es la única alternativa a bloquear a quien registra.
COLA_MAX = 500

# Segundos que se espera a n8n antes de dar el envío por perdido.
ESPERA = 5.0

# Reintentos por evento. Uno solo, y corto: cubre el hueco de un n8n que se
# está reiniciando sin convertir la cola en un atasco cuando está caído del
# todo.
REINTENTOS = 1
ESPERA_REINTENTO = 2.0

# Acciones que NO salen hacia n8n. Son las que genera el propio puente al
# recibir algo de n8n (ver integrations/endpoint.py). Sin esto, "n8n manda un
# aviso" se apunta en el registro, el apunte sale hacia n8n, n8n vuelve a
# mandar el aviso... y lo único que separaría a la casa de un bucle infinito
# sería que el filtro del workflow estuviera bien escrito. Se corta aquí, que
# es donde no depende de la configuración de nadie.
NO_SALEN = frozenset({"AVISO_N8N", "INTENTO_ACCESO"})


def url() -> str:
    """El webhook de n8n al que se manda todo. Vacío = integración apagada."""
    return os.getenv("N8N_WEBHOOK_URL", "").strip()


def token() -> str:
    """El secreto compartido con n8n. Viaja en `X-Noxus-Token` en los dos
    sentidos: aquí lo ponemos al salir, y `endpoint.py` lo exige al entrar."""
    return os.getenv("N8N_TOKEN", "").strip()


def activo() -> bool:
    return bool(url())


_COLA: "queue.Queue[dict]" = queue.Queue(maxsize=COLA_MAX)
_hilo: threading.Thread | None = None
_candado = threading.Lock()
_descartados = 0


def _enviar(evento: dict) -> None:
    destino = url()
    if not destino:
        return
    cabeceras = {"Content-Type": "application/json"}
    secreto = token()
    if secreto:
        cabeceras["X-Noxus-Token"] = secreto
    datos = json.dumps(evento, ensure_ascii=False).encode("utf-8")
    peticion = urllib.request.Request(destino, data=datos, method="POST",
                                      headers=cabeceras)
    with urllib.request.urlopen(peticion, timeout=ESPERA) as respuesta:
        respuesta.read()


def _bucle() -> None:
    global _descartados
    while True:
        evento = _COLA.get()
        try:
            for intento in range(REINTENTOS + 1):
                try:
                    _enviar(evento)
                    break
                except Exception as e:
                    if intento == REINTENTOS:
                        print(f"⚠️ n8n: se pierde {evento.get('accion')}: {e}")
                    else:
                        time.sleep(ESPERA_REINTENTO)
        except Exception as e:          # el bucle no se muere por nada
            print(f"⚠️ n8n: fallo inesperado enviando: {e}")
        finally:
            _COLA.task_done()
        if _descartados:
            # Se dice UNA vez por atasco, al vaciarse, y no en cada descarte:
            # con n8n caído serían cientos de líneas iguales en el journal.
            perdidos, _descartados = _descartados, 0
            print(f"⚠️ n8n: {perdidos} evento(s) descartados con la cola llena")


def _asegurar_hilo() -> None:
    """Arranca el hilo de envío la primera vez que hace falta.

    Perezoso y no en el arranque del proceso porque así la integración apagada
    no cuesta ni un hilo, y porque `logs.registrar` se llama desde sitios muy
    tempranos (la importación del histórico) donde todavía no hay nada montado.
    """
    global _hilo
    if _hilo is not None and _hilo.is_alive():
        return
    with _candado:
        if _hilo is not None and _hilo.is_alive():
            return
        _hilo = threading.Thread(target=_bucle, name="n8n-webhook", daemon=True)
        _hilo.start()


def payload(*, evento_id: int, categoria: str, accion: str,
            accion_legible: str, usuario: str, detalle: str, grupo: str,
            entidad: str, ahora: float | None = None) -> dict:
    """El evento tal y como lo ve n8n.

    Se separa de `emitir` para poder verlo en una prueba sin mandar nada.

    `fecha` y `hora` van partidas además del `timestamp` entero porque el
    workflow las escribe en columnas distintas del registro, y hacerlo con una
    expresión de n8n obliga a pelearse con zonas horarias que aquí ya están
    resueltas: la hora es la LOCAL de la casa, la misma que sale en la pestaña
    Registros.

    `elemento` es el sujeto del evento («Habitación»), que es la primera parte
    del detalle — el resto son añadidos («Raspberry pin 5»). Se parte aquí para
    que el workflow no tenga que conocer ese convenio.
    """
    momento = time.time() if ahora is None else ahora
    local = time.localtime(momento)
    sujeto, _, extra = (detalle or "").partition(" · ")
    return {
        "origen": "noxus",
        "evento_id": evento_id,
        "ts": int(momento),
        "fecha": time.strftime("%Y-%m-%d", local),
        "hora": time.strftime("%H:%M:%S", local),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", local),
        "categoria": categoria,
        "accion": accion,
        "accion_legible": accion_legible,
        "usuario": usuario,
        "elemento": sujeto.strip(),
        "detalle_extra": extra.strip(),
        "detalle": detalle,
        "entidad": entidad,
        "grupo": grupo,
    }


def emitir(*, evento_id: int, categoria: str, accion: str,
           accion_legible: str, usuario: str, detalle: str = "",
           grupo: str = "", entidad: str = "") -> None:
    """Encola un evento para n8n. Vuelve enseguida y no levanta nunca.

    `accion_legible` se recibe hecha en vez de calcularla aquí para no importar
    `security/logs`, que es justo quien llama a esto: el puente no puede
    depender del módulo del que cuelga."""
    global _descartados
    if not activo() or accion in NO_SALEN:
        return
    try:
        _asegurar_hilo()
        _COLA.put_nowait(payload(
            evento_id=evento_id, categoria=categoria, accion=accion,
            accion_legible=accion_legible, usuario=usuario, detalle=detalle,
            grupo=grupo, entidad=entidad))
    except queue.Full:
        _descartados += 1
    except Exception as e:
        # Apuntar un evento es SIEMPRE lo secundario de la acción que lo
        # provoca, y mandarlo a n8n todavía más. Misma regla que en logs.py.
        print(f"⚠️ n8n: no se pudo encolar {accion}: {e}")
