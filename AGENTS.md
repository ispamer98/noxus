# noxuscmmd

Panel domotico Reflex 0.8.28 que controla una casa real.
Servicio `noxus-panel` (front :3000, back :8000).
Repositorio publico `ispamer98/noxus`.

## Arquitectura

- `noxuscmmd/core/`: conectividad e infraestructura.
- `noxuscmmd/domains/<dominio>/state.py`: logica de negocio.
- `noxuscmmd/ui/dashboard/`: presentacion; no decide logica de negocio.
- `.web/`: generado; no leer ni editar.

Antes de crear una abstraccion nueva, buscar si ya existe una equivalente.
Preferir extender servicios/modelos comunes frente a crear implementaciones paralelas.

## Invariantes operativos

- Los JSON de la raiz son datos en vivo. No escribirlos en pruebas; copiar a
  `/tmp` y redirigir con variables de entorno. Escritura productiva atomica:
  temporal + `os.replace`.
- El historico vive en `historico.db` (SQLite WAL,
  `domains/security/logs_store.py`). `logs.json` es una copia congelada: no se
  lee ni escribe. En pruebas usar `HISTORICO_DB=/tmp/<nombre>.db`. Los archivos
  `-wal` y `-shm` no son basura.
- `fotogramas/` contiene imagenes privadas. No mover a `assets/`; servir solo
  mediante `/api/fotograma/<nombre>`, que valida la sesion.
- `rxconfig.py` mantiene `state_auto_setters=False`. Crear setters necesarios
  explicitamente con `@rx.event`; prefijar con `_` lo que no deba llegar al
  cliente.
- `.env`, `tinytuya.json` y `webos_key.json` contienen secretos. Revisar
  `git status` antes de cualquier staging y nunca incluirlos en Git.
- Hay cambios de usuario frecuentes: preservarlos y no tocar archivos ajenos a
  la tarea.
- No usar comandos Git destructivos para limpiar cambios existentes.

## Metodo de trabajo

Antes de modificar:
- leer `git status`;
- inspeccionar el codigo relacionado con la tarea;
- revisar `git diff` si existen cambios pendientes;
- reutilizar abstracciones existentes.

No explorar todo el repositorio si la tarea puede resolverse de forma focalizada.

Para tareas grandes:
- identificar primero los puntos de entrada y dependencias;
- implementar por bloques coherentes;
- verificar cada bloque antes de ampliar el alcance.

No declarar una tarea terminada solo porque compile.
Comprobar los criterios funcionales pedidos por el usuario.

## Verificacion y operacion

- Python: `.venv/bin/python` (3.11), nunca `python3` suelto.
- Comprobacion rapida: `.venv/bin/python -m pyflakes noxuscmmd/`.
- Ejecutar primero pruebas focalizadas.
- Ampliar pruebas solo según riesgo y alcance.
- Antes de finalizar cambios significativos:
  - ejecutar pruebas relevantes;
  - ejecutar `git diff --check`;
  - revisar `git diff`;
  - revisar `git status`.
- Logs: `journalctl -u noxus-panel -n 50 --no-pager`.
- Avisar antes de reiniciar `noxus-panel`: el panel esta en uso.
- No reiniciar el servicio durante trabajo intermedio salvo que sea necesario
  para validar comportamiento en runtime.