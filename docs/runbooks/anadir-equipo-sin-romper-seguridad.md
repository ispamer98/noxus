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
4. El broker MQTT (`mosquitto`) escucha en: `127.0.0.1:1883` (anónimo, solo el panel),
   `100.98.98.1:1883` (Tailscale, **con usuario y contraseña**: Raspberry) y
   `0.0.0.0:1884` (LAN, **con usuario y contraseña**: ESP32, que no corren Tailscale).
   El `1883` ya no escucha en la LAN. Nunca hay acceso anónimo desde fuera de la máquina.
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
   - **ESP32 (LAN)**: broker = IP LAN del servidor de casa (`ip -4 -br a`; reservarla en
     el router para que no cambie), puerto **`1884`**. **Pi (Tailscale)**: `100.98.98.1`, puerto `1883`.
   - **Usuario = slug**, contraseña del paso 2. Un ESP32 no puede usar Tailscale (no hay
     cliente), por eso tiene su puerto de LAN.
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
   mosquitto_sub -h <IP-LAN> -p 1884 -u esp32_salon -P "$P" -t 'casa/esp32_salon/#' -v -C 1 -W 10   # llega su estado
   mosquitto_sub -h <IP-LAN> -p 1884 -t 'casa/#' -C 1 -W 3         # sin credenciales → «not authorised»
   ```
6. Si es un nodo de prueba que se retira: `scripts/mqtt_nodo.sh quitar <slug>`.

Pines de entrada (alarma, tamper) siguen necesitando estar en `PROTEGIDOS` de
`gpio_mqtt.py`, como antes.

## Guía rápida: sensor magnético (contacto NC) o tamper

Convención del panel: **`ON` = abierto/activo (alarma)**, `OFF` = cerrado. Un contacto NC
(cerrado con la puerta cerrada) da además alarma si alguien corta el cable.

**Raspberry** (es lo que está montado hoy; `scripts/sensor_mqtt.py`, `Button(pin, pull_up=False)`):

```
3,3 V (pin físico 1 ó 17) ──[ 1 kΩ ]──┬── GPIO (BCM)
                                      └── contacto NC ── GND (pin físico 6, 9, 14…)
```

- Puerta = BCM 27 (pin físico 13), tamper del PC = BCM 23 (pin físico 16). Cada sensor
  usa su GPIO; **comparten** el 3,3 V y la GND. **Nunca 5 V** en un GPIO.
- Contacto cerrado → GPIO a GND → `OFF`. Puerta abierta o cable cortado → 1 kΩ lo sube a
  3,3 V → `ON`.
- **NC y NO se cablean igual pero NO se comportan igual** (aquí «NC/NO» = estado con la
  puerta CERRADA, como en alarmas):

  | Contacto | Puerta cerrada | Puerta abierta | Cable cortado | Con el script actual |
  |---|---|---|---|---|
  | **NC** (cerrado) | circuito cerrado → `OFF` | abierto → `ON` | abierto → `ON` (**alarma**) | correcto |
  | **NO** (abierto) | circuito abierto → `ON` | cerrado → `OFF` | abierto → `ON` (nadie se entera) | **invertido** |

  El script supone NC (`ON` = abierto). Un NO daría alarma con la puerta cerrada y
  silencio al abrirla, y además no detecta el corte de cable. **Usa siempre NC.** Si algún
  día hubiera que usar un NO, habría que añadir una marca de inversión por sensor en
  `sensor_mqtt.py` (hoy no existe). Los dos tamper (puerta y caja del PC) son NC.
- **Cómo saber cuál tienes** (sin conectar nada): polímetro en continuidad entre los dos
  cables, con el imán **pegado** al sensor (puerta cerrada). Pita = NC; no pita = NO.
  Comprueba también que al separar el imán cambia.
- Sensor nuevo en la Pi: tupla en `SENSORES` de `sensor_mqtt.py` + el pin en `PROTEGIDOS` de
  `gpio_mqtt.py` + reiniciar ambos servicios (con cuidado: los relés están en esa Pi).

**ESP32** (ESPHome; contrastado con su documentación): contacto entre el GPIO y **GND**,
sin resistencia externa (pull-up interno), y **sin** `inverted` (así abierto = `ON`).
Evita los pines de arranque 0, 2, 5, 12 y 15 (Espressif). **Solo para ESP32 con wifi, sin
Ethernet**: 4, 13, 14, 16–19, 21–23, 25–27, 32, 33. **En una placa con Ethernet NO uses
esos 18, 19, 21, 22, 23, 25, 26, 27 (ni el 0): son del Ethernet** → sección siguiente.
Los GPIO 34–39 son solo entrada y **no tienen pull-up interno** (Espressif): ahí hace falta
1 kΩ–10 kΩ externa a 3,3 V, igual que en la Raspberry.

```yaml
mqtt:
  broker: <IP-LAN-del-servidor>
  port: 1884
  username: esp32_habitacion_3          # = slug del nodo
  password: !secret mqtt_password
  topic_prefix: casa/esp32_habitacion_3
  discovery: false
binary_sensor:
  - platform: gpio
    name: puerta_hab3
    pin: {number: GPIO13, mode: {input: true, pullup: true}}
    filters: [{delayed_on_off: 300ms}]
    state_topic: casa/esp32_habitacion_3/puerta_hab3   # el panel lee casa/<slug>/<nombre>
```

Después, en el panel: nodo `esp32_habitacion_3` (si no existe) y el sensor con ese topic.

### ESP32 con Ethernet (ESP32-ETH, WT32-ETH01, Olimex POE/EVB…)

Cableado por LAN: el ESP32 se conecta al `1884` del servidor (guía A.3), sin wifi.
**Antes de comprar o cablear, confirma el modelo exacto**: los pines libres cambian con la placa.

**Pines que ocupa el Ethernet en un ESP32 clásico con LAN8720** (tabla RMII de Espressif,
«fijos, no se pueden cambiar», salvo el reloj; MDC/MDIO por defecto de ESPHome):

| Función | GPIO |
|---|---|
| REF_CLK (reloj; según placa) | 0 (WT32-ETH01, Olimex EVB) · 17 (Olimex POE) |
| TXD0 · TX_EN · TXD1 | 19 · 21 · 22 |
| RXD0 · RXD1 · CRS_DV | 25 · 26 · 27 |
| MDC · MDIO | 23 · 18 |
| Extra de la placa (`power_pin`) | WT32-ETH01: **16** · Olimex POE: **12** |

**WT32-ETH01** (README de egnor/wt32-eth01, contrastado con ESPHome):
- Libres con pull-up interno, **los buenos para un contacto: IO4, IO14, IO32, IO33.**
- IO35, IO36, IO39: solo entrada, sin pull-up → resistencia externa a 3,3 V.
- No usar: IO0, IO2, IO5, IO12, IO15 (arranque; **IO12 con pull-up a 3,3 V al arrancar impide
  que el chip funcione**), IO1/IO3 (puerto serie), IO16 (oscilador), IO18 y IO23 (Ethernet) e IO17 (la README lo marca como reservado; no
  confirmado para qué).
- Se alimenta por `3V3` **o** por `5V`, nunca por los dos a la vez.

**Olimex ESP32-POE / EVB**: ESPHome confirma lo ocupado (tabla de arriba). Los pines libres
del conector **NO están confirmados contra el esquema del fabricante** — por eliminación
quedarían 4, 13, 14, 16, 32, 33, pero pueden estar cableados a UEXT/SD: mirar el pinout de
la placa antes de soldar.

Cableado del contacto NC (igual que con wifi, sin resistencia si el pin tiene pull-up interno):
`GPIO ── contacto NC ── GND`, `ON` = abierto, sin `inverted`.

```yaml
ethernet:                      # WT32-ETH01 (config de la doc de ESPHome); otras placas: ver su ejemplo
  type: LAN8720
  mdc_pin: GPIO23
  mdio_pin: GPIO18
  clk: {pin: GPIO0, mode: CLK_EXT_IN}
  phy_addr: 1
  power_pin: GPIO16
mqtt:
  broker: <IP-LAN-del-servidor>
  port: 1884
  username: esp32_habitacion_3
  password: !secret mqtt_password
  topic_prefix: casa/esp32_habitacion_3
  discovery: false
binary_sensor:
  - platform: gpio
    name: puerta_hab3
    pin: {number: GPIO4, mode: {input: true, pullup: true}}
    filters: [{delayed_on_off: 300ms}]
    state_topic: casa/esp32_habitacion_3/puerta_hab3
```

Notas: sin `api:` no hay reinicio por falta de cliente de la API; ESPHome reinicia si pierde
el MQTT durante `reboot_timeout` (15 min por defecto, desactivable con `0s`). Al programar la
WT32-ETH01 por serie, GPIO0 debe ir a GND durante la carga (y soltarse después).

### Capacidad por nodo: hasta 4 entradas de alarma + 4 relés

**Opción 1 — todo en una WT32-ETH01: SÍ viable, pero sin margen** (8 de los 8 pines
utilizables; si falta uno, no hay plan B en la misma placa).

| Uso | GPIO | Condición |
|---|---|---|
| Entradas ×3 | **35, 36, 39** | Solo entrada y **sin pull-up interno** (Espressif): **1 kΩ externa a 3,3 V** en cada una (igual que la Pi) |
| Entrada ×1 | **14** | Pull-up interno. Saca una señal al arrancar (fuente secundaria), inocua en una entrada |
| Relés ×4 | **2, 4, 32, 33** | Ver abajo: **módulo de relés activo en ALTO** |

Por qué esos: IO4/IO32/IO33 no son de arranque; IO2 arranca en BAJO (pull-down interno) y la
README de la WT32 lo da por usable como salida tras el arranque. Se **descartan para relés**
los pines que sacan señal al arrancar (1, 3, 5, 14, 15; Random Nerd Tutorials, fuente
secundaria no contrastada con el datasheet de Espressif) y el 12 (si se sube a 3,3 V al
arrancar, el chip no arranca). Un relé de puerta que da un golpe al encender NO es admisible.

Condiciones que NO son opcionales:
1. **Relés en ALTO**: un módulo «activo en BAJO» (los azules típicos) se activaría con el pin en
   BAJO durante el arranque en IO2. Usa un módulo/driver activo en ALTO (o verifica su jumper
   con el polímetro antes de conectarlo a una cerradura).
2. `restore_mode: ALWAYS_OFF` en cada relé (es el valor por defecto de ESPHome, pero ponlo
   explícito) y **nunca retener `/set`**.
3. Módulo de relés con **alimentación propia** (no de la WT32; su regulador no es fiable por
   encima de ~6 V) y **GND común** con la WT32.
4. Con IO2 conectado, el módulo no debe forzarlo a ALTO al arrancar (programar por serie exige
   IO2 flotante o en BAJO).
5. Sin pines libres: nada de I²C, SD ni UART extra en ese nodo.

```yaml
switch:
  - platform: gpio
    name: rele_1
    pin: GPIO4
    restore_mode: ALWAYS_OFF
    command_topic: casa/esp32_habitacion_3/4/set     # patrón del panel: casa/<slug>/<pin>/set
    state_topic: casa/esp32_habitacion_3/4           # estado retenido
```

**Opción 2 — relés en una placa Ethernet independiente: SÍ viable.** Existe (comprobado en
Waveshare y en ESPHome Devices): **Waveshare ESP32-S3-ETH-8DI-8RO** — 8 relés (≤10 A 250 V CA /
30 V CC), 8 entradas digitales, Ethernet W5500, alimentación 7–36 V CC o 5 V USB-C, existe
variante PoE (`ESP32-S3-POE-ETH-8DI-8RO`) y tiene configuración ESPHome publicada (relés por
expansor I²C TCA9554 en la dirección 0x20; entradas en GPIO4–11 con `INPUT_PULLUP` e
`inverted`). Matices:
- Es de **8 canales**, no de 4 (no he verificado ninguna de 4 con Ethernet).
- **NO confirmado**: el estado de los relés al arrancar (la ficha no lo dice) y el tipo exacto
  de sus entradas (aislamiento y tensión): no asumir que un contacto seco funciona directo.
- Usa ESPHome, así que puede hablar nuestro patrón `casa/<slug>/<pin>/set`.

**Recomendación:** WT32-ETH01 **solo para las 4 entradas** (IO4, IO14, IO32, IO33 con pull-up
interno, sin resistencias) y los relés en placa aparte; es lo más limpio y sin pines al límite.

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
| ESP32 no conecta por LAN | Puerto equivocado (`1883` no escucha en la LAN) o IP del servidor cambiada | Usar `<IP-LAN>:1884`; reservar la IP en el router |
| Se renombró el nodo en el panel y dejó de responder | El slug cambió, la ACL es del antiguo | `quitar` el viejo, `alta` el nuevo, actualizar firmware |
| Móvil nuevo no recibe avisos | Sigue `pendiente` / sin `VER` | Darle rol en Dispositivos y accesos |
| Invitado «no puede» algo nuevo | Falta capacidad en `_POR_ROL` (`permisos.py`) | Decidirlo y añadirlo; no abrir el portero |
| `test_portero` falla en `_cobertura` | Manejador nuevo sin permiso | Ver C.4 |
| Tablet no puede lanzar un evento nuevo | No está en la lista `kiosco` | Ver C.6 |
| Pi: servicio activo pero sin publicar | `.mqtt_cred` ausente o mal | `journalctl -u gpio-mqtt -u sensor-mqtt` (si falta el fichero, no arranca) |

## Qué NO hacer

- Volver a `listener 1883 0.0.0.0` ni `allow_anonymous true` fuera de `127.0.0.1` (la LAN ya
  tiene el `1884` autenticado).
- Reutilizar la clave de otro nodo, pegarla en el repo (**es público**) o en `.env` versionado.
- Dar al nodo una ACL más ancha que `casa/<slug>/#`.
- Retener un `/set`.
- Añadir un manejador a `portero_revisados.txt` sin haberlo leído.

## Vuelta atrás del broker

`/etc/mosquitto/conf.d/default.conf.bak-2026-10-02` es la configuración anterior (anónima
en `0.0.0.0`). Restaurar y `sudo systemctl restart mosquitto` **reabre el agujero**: solo
como emergencia y por poco tiempo.
