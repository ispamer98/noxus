# Permisos obligatorios (sin «rodaje») — 2026-10-02

El modo «rodaje» (`ajustes.estricto`, que apuntaba pero no impedía) ya no existe:
los permisos mandan siempre. Se quitó `store.estricto/poner_estricto`, la tarjeta
«Permisos en vigor» de Dispositivos y accesos, `alternar_bloqueo`, `AuthState._bloqueo`
y `scripts/acceso.py estricto`. La clave `ajustes.estricto` que queda en
`dispositivos.json` es inofensiva y no se lee.

- Sin ficha o sin rol con `VER`, nadie entra. Fichero ilegible → panel cerrado para todos.
- Primer alta o recuperación: `.venv/bin/python scripts/acceso.py rol <nombre> admin`.

## Agujeros cerrados en la revisión (2026-10-02)

1. **Push a desconocidos**: registrar una suscripción no exige acceso (así se identifica
   un aparato nuevo), pero `enviar_notificacion` mandaba a TODAS. Ahora solo a aparatos
   con `VER` (`push._endpoints_con_acceso`).
2. **`PushState.lanzar_alerta_global_con_subscripcion`** estaba abierta a «sin acceso» y sin
   `AVISAR`. Ahora exige `AVISAR` (manejador + portero).
3. **Edición sin permiso en el servidor** (solo la UI la escondía): guardar el plano,
   botones de mando IR/RF, ocultar/aislar entidades → `AJUSTES` en `core/portero.py`.

Pruebas: `tests/test_portero.py`.

4. **MQTT cerrado (2026-10-02)**: Mosquitto ya no escucha en `0.0.0.0`.
   `/etc/mosquitto/conf.d/default.conf` (copia: `default.conf.bak-2026-10-02`):
   `127.0.0.1:1883` anónimo para el panel y `100.98.98.1:1883` (Tailscale) con
   usuario/contraseña (`/etc/mosquitto/passwd`) y ACL por nodo (`/etc/mosquitto/acl`:
   `raspberry` → `casa/raspberry/#`). La Pi lee su contraseña de
   `/home/vpn/MQTT/.mqtt_cred` (600); copia en `~/.agents/keys/mqtt_raspberry`.
   Scripts de la Pi con copia `*.bak-2026-10-02`. **Nodo nuevo** (p. ej. ESP32): crear su
   usuario con `sudo mosquitto_passwd -b /etc/mosquitto/passwd <nodo> <clave>`, añadir
   `user <nodo>` + `topic readwrite casa/<nodo>/#` al ACL y `sudo systemctl restart mosquitto`;
   el firmware usa ese usuario contra `100.98.98.1:1883` (ya no vale la LAN).
   Vuelta atrás: restaurar `default.conf.bak-2026-10-02` y reiniciar mosquitto.
5. **Candado del portero**: `tests/test_portero.py::_cobertura` falla si aparece un
   manejador `@rx.event` sin `permisos.denegar` ni regla en el portero que no esté en
   `tests/portero_revisados.txt`. Un evento nuevo obliga a decidir.
   También con regla `AJUSTES` ahora: sirena de la tablet y duplicar reglas.

## Pendiente

- El historial de Registros (y su exportación CSV) lo ve cualquier rol con acceso:
  decisión de diseño actual («pantalla de consulta»), revisar si el invitado debe verlo.
- `ElectroState.sync_loop` aún falla con pestaña abierta («StateProxy is immutable»):
  movido `_contexto()` dentro de `async with self` sin efecto; la traza se imprime una
  vez en el journal (`grep -A15 "Error en ElectroState"`) cuando conecte una sesión.
