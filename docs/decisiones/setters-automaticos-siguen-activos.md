---
tipo: decision
fecha: 2026-08-16
proyecto: noxuscmmd
estado: resuelta
---

# Los setters automáticos: cerrados

## Contexto

Reflex crea un evento `set_<nombre>` por **cada variable pública** de una clase de
estado. Ese evento viaja por el websocket y puede invocarlo cualquier navegador
conectado al panel, no solo los botones que hay en la interfaz.

`Calendario` desactivó ese comportamiento a propósito
([[setters-automaticos-desactivados]]). `noxuscmmd` no lo había hecho: su
`rxconfig.py` no declaraba `state_auto_setters`, y en Reflex 0.8.28 el valor por
defecto es `None`, que la librería trata como **activado**.

Esto importaba más aquí que en ningún otro proyecto: el panel gobierna la alarma,
los grupos de armado y los accesos de una casa real.

El caso concreto que lo volvió urgente: `PushState.current_user` es la identidad
del dispositivo, la que queda escrita en cada línea del registro. Con los setters
abiertos, `set_current_user("PC Salon")` era invocable desde cualquier navegador
— es decir, **cualquiera podía firmar sus acciones con el nombre de otro**.

## Decisión

**`state_auto_setters=False` en `rxconfig.py`.** Era la alternativa que este
mismo documento ya señalaba como la buena; lo que faltaba era comprobar que no
rompía nada.

Se comprobó cruzando los `.set_*` que aparecen en el código contra los que están
definidos a mano:

```bash
comm -23 \
 <(grep -rhoE "\.set_[a-z_]+" noxuscmmd/ui noxuscmmd/domains --include=*.py | sed 's/^\.//' | sort -u) \
 <(grep -rhoE "def set_[a-z_]+" noxuscmmd --include=*.py | sed 's/def //' | sort -u)
```

Sobreviven cuatro, y **ninguno es un setter automático de Reflex**:
`set_clipboard` y `set_multiple_values` (API de Reflex), `set_missing_host_key_policy`
y `set_socket` (paramiko). La interfaz define a mano todos los suyos, así que
apagarlos no dejó ningún botón sin evento.

Verificado después del cambio: `set_current_user` y `set_active_view` ya no
existen; `set_view`, definido a mano, sigue.

## Lo que esto NO arregla

Cerrar los setters reduce la superficie, pero **no es control de acceso**. Los
eventos definidos a mano (`conmutar_alarma`, `toggle_group_armed`, `open_door`)
siguen siendo invocables por websocket desde cualquier navegador, con botón o sin
él. Esconder un botón no es un permiso.

Por eso la comprobación de verdad vive dentro de cada manejador crítico
(`domains/auth/permisos.py:denegar`), y lo de `ui/` es solo para no enseñar lo
que no se va a poder usar.

## Rastro

Detectado el 2026-08-16 auditando el entorno. Cerrado el mismo día, al montar
los permisos por dispositivo del dominio `auth`.
