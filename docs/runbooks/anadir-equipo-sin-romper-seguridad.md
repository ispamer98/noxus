# Añadir un equipo sin romper la seguridad

Guía única para cuando entre algo nuevo (un ESP32, otra Raspberry, un móvil, una
tablet, un manejador o una pantalla). Qué se endureció y por qué:
[permisos-obligatorios.md](permisos-obligatorios.md). Si algo de esto falla, ve
a «Síntomas» al final.

## El modelo en ocho líneas

1. Un aparato que abre el panel queda con un **rol** (`pendiente` → un admin se lo
   cambia). Sin rol con `VER` no entra ni recibe avisos push.
2. Los permisos **no tienen modo rodaje**: se comprueban siempre en el servidor.
3. Cada evento del navegador pasa por `core/portero.py` y, además, el manejador
   crítico llama a `permisos.denegar`. Esconder un botón no es un permiso.
4. El broker MQTT (`mosquitto`) solo escucha en `127.0.0.1` (anónimo, para el panel)
   y en `100.98.98.1` (Tailscale, **con usuario y contraseña**). La LAN ya no.
5. Cada nodo físico tiene **su usuario** y una ACL que solo le deja `casa/<nodo>/#`.
6. El usuario del broker se llama igual que el **slug** del nodo en el panel.
7. Un test (`tests/test_portero.py::_cobertura`) falla si añades un manejador sin permiso.
8. Los avisos push (alarma, puertas…) solo llegan a aparatos con `VER`.

## A. Nodo físico nuevo (ESP32, Raspberry, Pi Zero…)

Pasos en orden; el panel no necesita reiniciarse.

1. **Elige el nombre en el panel** (Ajustes → nodos) y calcula el slug:
   «ESP32 Salón» → `esp32_salon`. Solo `a-z 0-9 _`. Si luego renombras el nodo en el
   panel, cambia el slug y **hay que repetir el alta** con el nombre nuevo (la ACL
   ya no coincidiría y las órdenes se perderían sin avisar).
2. **Alta en el broker** (en el servidor de casa):
   ```bash
   scripts/mqtt_nodo.sh alta esp32_salon     # crea usuario + ACL y recarga SIN cortar a nadie
   cat ~/.agents/keys/mqtt_esp32_salon       # la clave, para el firmware (nunca al repo)
   ```
3. **Firmware / script del nodo**:
   - Broker `100.98.98.1`, puerto `1883`, **usuario = slug**, contraseña del paso 2.
   - El nodo debe estar en el tailnet (o llegar a esa IP). **Por la LAN no entra**: si
     no puede usar Tailscale, hay que abrir un listener propio (decisión de seguridad:
     pídelo, no vuelvas a `0.0.0.0` anónimo).
   - Solo puede publicar/suscribirse a `casa/<slug>/#`. Patrón de siempre
     ([skill nodos-mqtt](../../.claude/skills/nodos-mqtt/SKILL.md) o la del sistema):
     `casa/<slug>/<pin>/set` (orden, **nunca retenida**), `casa/<slug>/<pin>` (estado,
     retenido), entradas en `casa/<slug>/<nombre>` (`ON` = abierto/activo, retenido).
   - ESPHome (contrastar con su documentación oficial): bloque `mqtt:` con `broker`,
     `username`, `password` (con `!secret`, fuera de git) y `topic_prefix: casa/<slug>`.
   - **Raspberry / Pi**: copiar `scripts/gpio_mqtt.py` y `scripts/sensor_mqtt.py`, crear
     `.mqtt_cred` junto al script con la clave (`chmod 600`). `gpio_mqtt.py` usa el nombre
     del nodo que recibe como argumento (`gpio_mqtt.py pi_zero` → usuario `pi_zero`);
     `sensor_mqtt.py` lleva `raspberry` fijo en `_credenciales()`: en otra Pi, cámbialo por su slug. No existe otro publicador: `raspberry_sensores_mqtt.py` NO está desplegado.
4. **Dar de alta el elemento en el panel** (nodo, relés, sensores) como siempre; el
   panel calcula los topics solo. Ese camino va por loopback y no necesita credenciales.
5. **Verificar** sin accionar nada real:
   ```bash
   P=$(cat ~/.agents/keys/mqtt_esp32_salon)
   mosquitto_sub -h 100.98.98.1 -u esp32_salon -P "$P" -t 'casa/esp32_salon/#' -v -C 1 -W 10   # llega su estado
   mosquitto_sub -h 100.98.98.1 -t 'casa/#' -C 1 -W 3         # sin credenciales → «not authorised»
   ```
6. Si es un nodo de prueba que se retira: `scripts/mqtt_nodo.sh quitar <slug>`.

Pines de entrada (alarma, tamper) siguen necesitando estar en `PROTEGIDOS` de
`gpio_mqtt.py`, como antes.

## B. Móvil, tablet o PC nuevo que abre el panel

- Entra siempre por `https://panel.noxuscmmd.uk` (CORS solo permite ese origen).
- Queda `pendiente` y avisa a los admins. **Un admin le pone rol** en Ajustes →
  Dispositivos y accesos (admin / familia / invitado / kiosco). Hasta entonces:
  no ve el panel y **no recibe avisos push**, aunque active las notificaciones.
- **Tablet de pared (kiosco)**: necesita rol `kiosco` **y** una estancia asignada; sin
  estancia no abre nada. Solo puede lanzar los eventos de `PERMITIDOS_KIOSCO`
  (`tablas()["kiosco"]` en `core/portero.py`).
- Recuperar el acceso si nadie es admin: `.venv/bin/python scripts/acceso.py rol <nombre> admin`.

## C. Código nuevo (manejador, estado, pantalla, endpoint)

1. **Manejador `@rx.event` que actúa o escribe** → primera línea:
   `if (no := await permisos.denegar(self, permisos.<CAPACIDAD>)): return no`
   (luces `LUCES`, puertas `PUERTAS`, armar `ARMAR`, equipos `EQUIPOS`, mandos `MANDOS`,
   cámaras `CAMARAS`, avisos `AVISAR`, configuración `AJUSTES`). Sobre un control
   concreto de una estancia: `permisos.denegar_entidad`.
2. Si delega en un auxiliar `_x()`, **el permiso va en el auxiliar o en el primero**: el
   test solo mira el texto del manejador.
3. Edición/borrado sin comprobación propia → regla en `requiere` de `core/portero.py`.
4. **El test `_cobertura` fallará** hasta que decidas: (a) pon `denegar`, (b) regla en el
   portero, o (c) si es de verdad inocuo (setter de UI, bucle de fondo), añade
   `Estado.manejador` a `tests/portero_revisados.txt` **tras leerlo**.
5. Los bucles `on_load` / `sync_loop` los usan todos los roles: no les pongas `requiere`.
6. **Tablet**: si el nuevo evento debe poder usarlo un kiosco, añádelo a `kiosco` en
   `tablas()` (si no, el portero lo rechaza).
7. **Quien no tiene acceso** solo puede lo de `sin_acceso`; no metas ahí nada que mande
   avisos o escriba (ya pasó con `lanzar_alerta_global_con_subscripcion`).
8. **Ruta HTTP propia**: bajo `/api/` (si no, el router del VPS la manda al frontend →
   404; ver skill `migracion-hostinger`), con sesión/token comprobado y
   `hmac.compare_digest` para secretos.
9. Vars con datos sensibles: privadas (`_`); `state_auto_setters=False` ⇒ un setter
   solo existe si lo escribes con `@rx.event`.
10. Antes de reiniciar: `.venv/bin/python tests/ejecutar.py` y
    `.venv/bin/python -c "from noxuscmmd.ui.pages.dashboard import dashboard_page; dashboard_page()"`.

## Síntomas

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| Nodo: «Connection Refused: not authorised» | Sin usuario/clave o clave vieja (el alta la rota) | `scripts/mqtt_nodo.sh alta <slug>` y poner la clave nueva |
| Nodo conecta pero el panel no ve nada / la orden no llega | Topic fuera de `casa/<slug>/#` o usuario ≠ slug (la ACL **descarta en silencio**) | Alinear slug, usuario y topics; `scripts/mqtt_nodo.sh listar` |
| Nodo no conecta por LAN | La LAN ya no escucha | Usar Tailscale `100.98.98.1:1883` |
| Se renombró el nodo en el panel y dejó de responder | El slug cambió, la ACL es del antiguo | `quitar` el viejo, `alta` el nuevo, actualizar firmware |
| Móvil nuevo no recibe avisos | Sigue `pendiente` / sin `VER` | Darle rol en Dispositivos y accesos |
| Invitado «no puede» algo nuevo | Falta capacidad en `_POR_ROL` (`permisos.py`) | Decidirlo y añadirlo; no abrir el portero |
| `test_portero` falla en `_cobertura` | Manejador nuevo sin permiso | Ver C.4 |
| Tablet no puede lanzar un evento nuevo | No está en la lista `kiosco` | Ver C.6 |
| Pi: servicio activo pero sin publicar | `.mqtt_cred` ausente o mal | `journalctl -u gpio-mqtt -u sensor-mqtt` (si falta el fichero, no arranca) |

## Qué NO hacer

- Volver a `listener 1883 0.0.0.0` ni `allow_anonymous true` fuera de `127.0.0.1`.
- Reutilizar la clave de otro nodo, pegarla en el repo (**es público**) o en `.env` versionado.
- Dar al nodo una ACL más ancha que `casa/<slug>/#`.
- Retener un `/set`.
- Añadir un manejador a `portero_revisados.txt` sin haberlo leído.

## Vuelta atrás del broker

`/etc/mosquitto/conf.d/default.conf.bak-2026-10-02` es la configuración anterior (anónima
en `0.0.0.0`). Restaurar y `sudo systemctl restart mosquitto` **reabre el agujero**: solo
como emergencia y por poco tiempo.
