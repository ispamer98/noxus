"""Inventario de la red: todo lo que hay instalado en la casa, en una lista.

Tres piezas:

- `red`:       lo que se puede averiguar solo (tabla ARP y Tailscale).
- `store`:     lo que hay que escribir a mano (modelo, ubicación, notas) y los
               elementos que el panel no controla pero están ahí (un router, un
               lector de tarjetas, un switch).
- `catalogo`:  junta lo que ya hay dado de alta en el panel con las dos cosas
               de arriba y lo agrupa por familias.

La regla de oro: **el inventario no es una segunda base de datos**. Un sensor
sigue viviendo en nodos_dinamicos.json y aquí solo se le añaden los campos que
allí no existen. Nada de esto duplica lo que el panel ya sabe, porque dos
copias de la misma verdad acaban discrepando y entonces no vale ninguna.
"""
