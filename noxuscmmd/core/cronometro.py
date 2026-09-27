"""Cronómetro de eventos lentos: deja en el log los que pasan de UMBRAL_MS.

Existe para saber DÓNDE se va el tiempo cuando el panel "tarda en reaccionar",
en vez de adivinarlo. Envuelve dos puntos internos de Reflex 0.8.28:

- `reflex.app.process`: un evento normal que manda el navegador (esperar el
  cerrojo del estado + el manejador + calcular y enviar el delta).
- `StateProxy.__aenter__/__aexit__`: cada `async with self` de un bucle o una
  acción de fondo (esperar el cerrojo, y calcular y enviar el delta al salir).

En reposo cuesta un perf_counter por evento: solo escribe cuando algo pasa del
umbral. Si Reflex cambia estos puntos en otra versión, se desactiva solo y lo
dice en el log en vez de romper el arranque.
"""
import os
import time

UMBRAL_MS = float(os.getenv("NOXUS_UMBRAL_LENTO_MS", "120"))


def _nombre(evento) -> str:
    nombre = getattr(evento, "name", "") or "?"
    return nombre.rsplit(".", 1)[-1]


def activar() -> None:
    try:
        import reflex.app as app_mod
        from reflex.istate.proxy import StateProxy
    except Exception as e:  # pragma: no cover - depende de la versión instalada
        print(f"⚠️ Cronómetro de eventos desactivado: {e}")
        return
    if getattr(app_mod, "_noxus_cronometro", False):
        return
    app_mod._noxus_cronometro = True

    original = app_mod.process

    async def process(app, event, *args, **kwargs):
        t0 = time.perf_counter()
        envios = variables = 0
        async for update in original(app, event, *args, **kwargs):
            envios += 1
            delta = getattr(update, "delta", None) or {}
            variables += sum(len(v) for v in delta.values() if isinstance(v, dict))
            yield update
        ms = (time.perf_counter() - t0) * 1000
        if ms > UMBRAL_MS:
            print(f"⏱️ evento lento: {_nombre(event)} {ms:.0f} ms "
                  f"({envios} envío(s), {variables} variable(s) cambiadas)")

    app_mod.process = process

    entrar_original = StateProxy.__aenter__
    salir_original = StateProxy.__aexit__

    async def __aenter__(self):
        t0 = time.perf_counter()
        resultado = await entrar_original(self)
        ms = (time.perf_counter() - t0) * 1000
        if ms > UMBRAL_MS:
            print(f"⏱️ fondo esperando el cerrojo: "
                  f"{_nombre(getattr(self, '_self_event', None))} {ms:.0f} ms")
        return resultado

    async def __aexit__(self, *exc_info):
        t0 = time.perf_counter()
        resultado = await salir_original(self, *exc_info)
        ms = (time.perf_counter() - t0) * 1000
        if ms > UMBRAL_MS:
            print(f"⏱️ fondo calculando y enviando el cambio: "
                  f"{_nombre(getattr(self, '_self_event', None))} {ms:.0f} ms")
        return resultado

    StateProxy.__aenter__ = __aenter__
    StateProxy.__aexit__ = __aexit__
