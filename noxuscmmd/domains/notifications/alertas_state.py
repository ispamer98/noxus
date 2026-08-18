"""
Confirmar y silenciar alertas DESDE DENTRO de la aplicación.

Esto existe porque la vía que había no funciona en los móviles de esta casa. Las
alertas se confirmaban con los botones de la propia notificación (alertas.py +
endpoint.py + assets/sw.js), y los dos iPhones de la familia no pueden pintar
esos botones: WebKit no admite `actions` en showNotification, y al recibirlos
descarta la notificación entera — llega en blanco, sin título ni cuerpo, y al
pulsarla solo abre la aplicación. Comprobado el 2026-08-17 con la alarma de esta
casa: el mismo aviso llegaba vacío con botones y con su texto completo sin ellos.

Consecuencia, mientras eso no se arregló: si saltaba la alarma, la repetición
cada 60 segundos no se podía cortar desde ningún teléfono de la casa. Solo desde
un ordenador con Chrome. Una alarma que no se puede confirmar desde el móvil es
justo la que hay que poder confirmar desde el móvil.

Así que la confirmación deja de depender de que el sistema operativo del aparato
sepa pintar un botón dentro de una notificación: el aviso lleva a la aplicación y
la aplicación la enseña. El service worker sigue mandando sus botones donde SÍ se
pintan (Android/Chrome), y ese camino no cambia — este es el mismo trabajo por la
otra puerta, y los dos acaban en las mismas funciones de alertas.py.

PERMISO: ARMAR, el mismo que endpoint.py. Las dos cosas juntas importan. Que sea
ARMAR y no VER porque silenciar una alerta media hora calla los avisos de un
sensor de la alarma, y eso es de la familia de armar y desarmar, no de la de
entrar a mirar el panel: con VER, un dispositivo de rol «invitado» podía callar
la alarma de la casa. Y que sea el MISMO en los dos porque esto es una sola
acción por dos puertas — si se cambia aquí, hay que cambiarlo allí.
"""
import asyncio
import time

import reflex as rx

from . import alertas
from ..auth import permisos
from ..security import audit, logs
from ...core import sesiones

# Cada cuánto se mira si hay alertas nuevas. Igual que el resto de las
# pantallas: no hay temporizadores, se relee el disco (ver la cabecera de
# security/watcher.py).
INTERVALO = 2.0

# Minutos que calla el botón de silenciar. El mismo número que endpoint.py, y por
# el mismo motivo que el permiso: es la misma acción.
MINUTOS_SILENCIO = 30


def _hace_cuanto(desde: float) -> str:
    """"hace 40 s", "hace 3 min", "hace 2 h" — ya formateado, porque dentro de un
    rx.foreach no se puede llamar a una función de Python."""
    segundos = max(0, int(time.time() - desde))
    if segundos < 60:
        return f"hace {segundos} s"
    if segundos < 3600:
        return f"hace {segundos // 60} min"
    return f"hace {segundos // 3600} h"


class AlertasState(rx.State):
    # Todas las claves son str: una Var de dict que mezcle números y textos
    # dentro de un rx.foreach revienta el frontend en esta versión de Reflex.
    pendientes: list[dict] = []

    @rx.event
    async def on_load(self):
        self._recargar()
        yield AlertasState.sync_loop

    def _recargar(self) -> None:
        datos = alertas.leer()
        self.pendientes = [
            {
                "clave": clave,
                "titulo": ficha.get("titulo", "Alerta"),
                "cuerpo": ficha.get("cuerpo", ""),
                "cuando": _hace_cuanto(ficha.get("desde", 0)),
                # Cuántas veces se ha repetido ya sin que nadie diga nada. Se
                # enseña porque es la diferencia entre "acaba de pasar" y "lleva
                # tres minutos sonando y nadie ha mirado".
                "repeticiones": str(ficha.get("repeticiones", 0)),
            }
            for clave, ficha in datos.get("pendientes", {}).items()
        ]

    @rx.event(background=True)
    async def sync_loop(self):
        """Una alerta que salta con el panel abierto tiene que aparecer sola.

        Se compara antes de asignar: si no, cada vuelta reasignaría la lista y el
        navegador repintaría el aviso dos veces por segundo."""
        guardia = await sesiones.guardia(self)
        while True:
            try:
                if not await sesiones.espera(guardia, INTERVALO):
                    return
                datos = await asyncio.to_thread(alertas.leer)
                nuevas = list(datos.get("pendientes", {}))
                async with self:
                    if nuevas != [p["clave"] for p in self.pendientes]:
                        self._recargar()
                    else:
                        # Las mismas alertas, pero el "hace 3 min" envejece.
                        for p in self.pendientes:
                            ficha = datos["pendientes"].get(p["clave"], {})
                            p["cuando"] = _hace_cuanto(ficha.get("desde", 0))
                            p["repeticiones"] = str(ficha.get("repeticiones", 0))
                        self.pendientes = list(self.pendientes)
            except Exception as e:
                print(f"⚠️ Error en AlertasState.sync_loop: {e}")
                if not await sesiones.espera(guardia, 5):
                    return

    @rx.event
    async def confirmar(self, clave: str):
        """«Visto». Corta la repetición para todos: no hace falta que confirmen
        los cinco dispositivos, con uno basta."""
        if (no := await permisos.denegar(self, permisos.ARMAR)):
            return no
        quien = await audit.usuario_de(self)
        ficha = await asyncio.to_thread(alertas.confirmar, clave, quien)
        self._recargar()
        if ficha is None:
            # Otro se ha adelantado. No es un error: es lo que se busca.
            return rx.toast.info("Ya estaba confirmada.", position="top-center")
        logs.registrar(logs.ALARMA, "ALERTA_CONFIRMADA", quien,
                       f"{ficha['titulo']} — desde la aplicación")
        return rx.toast.success("Confirmado. Deja de repetirse.",
                                position="top-center")

    @rx.event
    async def silenciar(self, clave: str):
        """Calla los avisos de ESE elemento media hora. El evento se sigue
        registrando: silenciar es no querer el ruido, no querer que no conste
        (ver alertas.silenciar)."""
        if (no := await permisos.denegar(self, permisos.ARMAR)):
            return no
        quien = await audit.usuario_de(self)
        await asyncio.to_thread(alertas.silenciar, clave, MINUTOS_SILENCIO, quien)
        self._recargar()
        logs.registrar(logs.ALARMA, "ALERTA_SILENCIADA", quien,
                       f"{int(MINUTOS_SILENCIO)} minutos sin avisar de esto — "
                       f"desde la aplicación")
        return rx.toast.success(f"Silenciado {int(MINUTOS_SILENCIO)} minutos.",
                                position="top-center")

    @rx.var
    def hay_pendientes(self) -> bool:
        return len(self.pendientes) > 0
