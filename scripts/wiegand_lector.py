#!/usr/bin/env python3
"""Lector Wiegand -> ID de tarjeta.

Raspberry Pi Zero 2 W + lector Desico LPDO21 en modo Wiegand.
Decodifica tramas de cualquier longitud (26, 34, 37, 56 bits...) y
para Wiegand 26 saca ademas facility code y numero de tarjeta.

Uso:  python3 scripts/wiegand_lector.py
"""
import threading
import time

import lgpio

D0 = 23  # BCM 23 -> pin fisico 16  (borne D0 del lector)
D1 = 24  # BCM 24 -> pin fisico 18  (borne D1 del lector)
# Bornes LG / LR / BUZZ son entradas de control de led y zumbador: no se usan.
# Bornes A / B son el RS485: no se tocan.

FIN_TRAMA = 0.040  # 40 ms sin pulsos = la tarjeta ha terminado de enviar

_bits = []
_lock = threading.Lock()
_ultimo = 0.0


def _cb(chip, gpio, level, tick):
    global _ultimo
    with _lock:
        _bits.append(0 if gpio == D0 else 1)
        _ultimo = time.monotonic()


def decodifica(bits):
    n = len(bits)
    crudo = int("".join(str(b) for b in bits), 2)
    if n == 26:
        facility = int("".join(str(b) for b in bits[1:9]), 2)
        tarjeta = int("".join(str(b) for b in bits[9:25]), 2)
        return {
            "formato": "W26",
            "bits": n,
            "facility": facility,
            "tarjeta": tarjeta,
            "id": f"{facility:03d}{tarjeta:05d}",
            "crudo": crudo,
            "hex": f"{crudo:X}",
        }
    return {"formato": f"W{n}", "bits": n, "id": str(crudo), "crudo": crudo, "hex": f"{crudo:X}"}


def on_tarjeta(datos):
    """Aqui es donde enganchas tu logica (comparar con control_accesos.json,
    publicar por MQTT, abrir la puerta, etc.)."""
    print(f"[TARJETA] {datos}")


def main():
    h = lgpio.gpiochip_open(0)
    for pin in (D0, D1):
        # Linea de 3,3 V: sin pull interno, el lector ya fija ambos niveles
        lgpio.gpio_claim_alert(h, pin, lgpio.FALLING_EDGE, lFlags=lgpio.SET_BIAS_DISABLE)
    cbs = [lgpio.callback(h, pin, lgpio.FALLING_EDGE, _cb) for pin in (D0, D1)]

    print("Escuchando lector Wiegand.  Ctrl+C para salir.\n")
    try:
        while True:
            time.sleep(0.005)
            with _lock:
                if _bits and (time.monotonic() - _ultimo) > FIN_TRAMA:
                    trama = list(_bits)
                    _bits.clear()
                else:
                    trama = None
            if trama:
                on_tarjeta(decodifica(trama))
    except KeyboardInterrupt:
        print("\nSaliendo.")
    finally:
        for cb in cbs:
            cb.cancel()
        lgpio.gpiochip_close(h)


if __name__ == "__main__":
    main()
