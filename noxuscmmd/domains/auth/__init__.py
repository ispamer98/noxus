"""Quién es cada dispositivo y qué puede tocar.

Tres piezas:

- `sessions`: la cookie firmada. Dice QUÉ dispositivo es este navegador.
- `store`:    dispositivos.json. Dice qué ROL tiene ese dispositivo.
- `permisos`: qué puede hacer cada rol, y la comprobación que usan los
              manejadores del resto de dominios.

La separación entre las dos primeras no es un capricho: la cookie lleva
únicamente el identificador, nunca el rol. Si llevara el rol, cambiarlo o
retirarlo no tendría efecto hasta que el dispositivo volviera a entrar —
justo lo que no se quiere de una casa donde alguien deja de tener acceso.
Preguntando el rol en cada acción, quitarlo surte efecto en el acto.
"""
