"""
Aquí vivía `fan_thermostat_loop`: un termostato escrito a mano que encendía el
relé "ventilador" al llegar la Raspberry a 80 °C y lo apagaba a 75 °C.

Se ha retirado por dos motivos.

El primero es que ya no hace falta: cualquiera puede montar exactamente eso
—y con más finura— desde la pestaña Automatizaciones, sin tocar código y sin
reiniciar. El disparador "supera una temperatura" sobre la Raspberry y una
acción de escribir un pin hacen lo mismo, editables desde la web.

El segundo es más serio, y es la razón de que NO se haya migrado solo a una
regla equivalente: el relé "ventilador" está declarado en
devices/registry.py:103 sobre la Raspberry, **pin 17**, y ese mismo pin es el
de la puerta "Puerta habitación" en nodos_dinamicos.json. Mientras este bucle
existió, cada vez que la CPU pasaba de 80 °C se escribía ese pin. Crear
automáticamente una regla que siguiera haciéndolo habría sido peor que
quitarlo: una regla activándose sola sobre el pin de una puerta.

Antes de rehacer el termostato desde la web, hay que decidir en qué pin está
de verdad el ventilador y corregir el que no corresponda.
"""
