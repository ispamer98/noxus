#!/usr/bin/env python3
"""Diagnostico de cableado Wiegand.

Muestra en vivo el nivel en reposo de D0 y D1 y cuenta los flancos de
bajada de cada linea. Sirve para saber si el lector esta realmente
transmitiendo Wiegand, algo que un polimetro no puede ver porque los
pulsos duran solo ~50 microsegundos.

Al acercar una tarjeta deberias ver el total subir de golpe unos 26
pulsos repartidos entre D0 y D1.

Uso:  python3 scripts/wiegand_test_pulsos.py
"""
import time

import lgpio

D0 = 23  # BCM 23 -> pin fisico 16
D1 = 24  # BCM 24 -> pin fisico 18

contador = {D0: 0, D1: 0}


def _cb(chip, gpio, level, tick):
    contador[gpio] += 1


h = lgpio.gpiochip_open(0)
for pin in (D0, D1):
    # Sin pull interno: el divisor de tension ya fija ambos niveles
    lgpio.gpio_claim_alert(h, pin, lgpio.FALLING_EDGE, lFlags=lgpio.SET_BIAS_DISABLE)

cbs = [lgpio.callback(h, pin, lgpio.FALLING_EDGE, _cb) for pin in (D0, D1)]

print("En reposo D0 y D1 deben marcar nivel 1.")
print("Acerca una tarjeta y observa la columna 'pulsos'.")
print("Ctrl+C para salir.\n")
print("  nivel D0   nivel D1   pulsos D0   pulsos D1   total")

try:
    previo = None
    while True:
        n0, n1 = lgpio.gpio_read(h, D0), lgpio.gpio_read(h, D1)
        c0, c1 = contador[D0], contador[D1]
        estado = (n0, n1, c0, c1)
        if estado != previo:
            print(f"      {n0}          {n1}       {c0:6d}      {c1:6d}   {c0 + c1:6d}")
            previo = estado
        time.sleep(0.2)
except KeyboardInterrupt:
    print("\nSaliendo.")
finally:
    for cb in cbs:
        cb.cancel()
    lgpio.gpiochip_close(h)
