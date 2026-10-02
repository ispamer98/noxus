# Movimiento en cámaras → alarma (2026-09-29)

## 1. Qué hace
Con el sistema **armado** (`shared_state.get_sistema_armado`), una persona
detectada por una cámara vigilada ya no manda el aviso suave «Movimiento
detectado»: dispara la **alarma**, igual que un sensor abierto.

- Push de alarma a todos, con «Visto / Silenciar 30 min / Ver cámara».
- Pendiente en `alertas` → se repite cada minuto si nadie confirma y hace
  sonar la sirena de las tablets (`AlertasState.hay_pendientes`).
- Evento `GRUPO_ALERTA` en el registro, con el fotograma colgado.

## 2. Dónde
- `domains/security/watcher.py` → `alertar_movimiento(camara_id, nombre, detalle)`.
  Clave `alerta:<grupo principal>:<cámara>` (la zona es el grupo principal).
- `domains/cameras/movimiento_motor.py` → `_mirar` decide: armado → alarma;
  si no → `_avisar_movimiento` (aviso de siempre).

## 3. Excepciones a propósito
- **Retardo de entrada corriendo** (`retardos.leer()["entradas"]` no vacío):
  no salta; alguien ha abierto la puerta y va a desarmar. Si no lo hace, salta
  por la puerta. Queda el aviso suave de movimiento.
- **Silenciada** esa clave: se registra con foto, sin push ni sirena.
- Sigue haciendo falta que el detector de personas lo confirme
  (`movimiento.hay_persona`) y el enfriamiento de 60 s por cámara.
- Retardo de salida: mientras corre, la casa aún no está armada → no salta.

## 4. Probar sin tocar la casa
Simular `enviar_notificacion`, `alertas.*`, `logs.registrar`,
`groups_store.get_principal` y `retardos.leer` en el módulo `watcher` y llamar
a `asyncio.run(watcher.alertar_movimiento("cam_fija", "Salón", "3%"))`.
