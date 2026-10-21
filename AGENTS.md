# noxuscmmd

Panel domotico Reflex 0.8.28 que controla una casa real: alarma, accesos y dispositivos. Un fallo puede afectar al mundo fisico. Servicio `noxus-panel` (front :3000, back :8000). Repositorio publico `ispamer98/noxus`.

## Mapa del codigo y orden de lectura

- `noxuscmmd/core/`: conectividad e infraestructura compartida.
- `noxuscmmd/domains/<dominio>/state.py`: logica de negocio; reutiliza servicios y modelos comunes antes de crear abstracciones.
- `noxuscmmd/ui/dashboard/` y `noxuscmmd/ui/pages/`: presentacion; no deciden logica de negocio.
- `tests/`: pruebas propias, ejecutadas por `tests/ejecutar.py` (no pytest).
- `.web/` es generado: no leer ni editar.
- Orden para orientarse: `docs/estado.md` si existe; despues el modulo afectado, su `state.py` o servicio comun, la pagina/componente que lo usa y sus pruebas. No explorar el repo entero si basta un recorrido focalizado.

## Verificacion

- Python 3.11 del proyecto: usar siempre `.venv/bin/python`, nunca `python3` suelto.
- Analisis rapido: `.venv/bin/python -m pyflakes noxuscmmd/ tests/`.
- Compilar la pagina para detectar errores de componentes/Vars: `.venv/bin/python -c "from noxuscmmd.ui.pages.dashboard import dashboard_page; dashboard_page()"`.
- Pruebas: `.venv/bin/python tests/ejecutar.py`; empezar por pruebas focalizadas y ampliar segun riesgo. No usar pytest.
- No basta con compilar: comprobar el comportamiento funcional solicitado. En cambios significativos, ejecutar las comprobaciones pertinentes, `git diff --check`, revisar `git diff` y `git status`.
- Logs: `journalctl -u noxus-panel -n 50 --no-pager`.

## Despliegue y reinicio

- La publicacion sale por el VPS; no hay tuneles de Cloudflare. Para publicar, seguir la skill `publicar-en-vps`; el mapa global de servicios esta en `~/.agents/ECOSISTEMA.md`.
- Claude reinicia `noxus-panel` despues de cada cambio verificado y lo comunica en una linea. Codex nunca reinicia servicios. No reiniciar durante trabajo intermedio.
- El VPS reenvía a `:8000` lo que empiece por `/api`, `/_event`, `/_upload`, `/ping`, `/_health` o `/_all_routes`, y el resto a `:3000`. Una ruta HTTP propia **fuera de `/api/`** exige tocar también el router del VPS o dará 404 (skill `migracion-hostinger`).
- Para desplegar cambios del panel, seguir la skill `despliegue` y sus comprobaciones; no asumir que compilar equivale a validar en runtime.

## Seguridad y repositorio publico

- Los JSON de la raiz son datos vivos de la casa: no escribirlos en pruebas; usar copias en `/tmp` y variables de entorno. Las escrituras productivas son atomicas (temporal + `os.replace`).
- El historico vive en `historico.db` (SQLite WAL, `domains/security/logs_store.py`). `logs.json` es una copia congelada: no leer ni escribir. En pruebas usar `HISTORICO_DB=/tmp/<nombre>.db`; los ficheros `-wal` y `-shm` son parte de la base de datos.
- `fotogramas/` contiene imagenes privadas. No moverlas a `assets/`; servirlas solo por `/api/fotograma/<nombre>`, que valida la sesion.
- `rxconfig.py` lleva `cors_allowed_origins=["https://panel.noxuscmmd.uk"]`: al panel se entra siempre por ese dominio. Si vuelve el acceso por IP de la LAN, hay que añadir ese origen.
- `rxconfig.py` conserva `state_auto_setters=False`: declarar explicitamente con `@rx.event` los setters necesarios y prefijar con `_` lo que no deba llegar al cliente.
- Los permisos estan siempre en vigor: eventos que actuan o escriben requieren `permisos.denegar` o regla en `core/portero.py`; `tests/test_portero.py` comprueba cobertura. Los avisos push solo llegan a aparatos con `VER`.
- `.env`, `tinytuya.json` y `webos_key.json` contienen credenciales: no leer sin motivo ni incluir en Git. Revisar `git status` antes de staging; este repo es publico.
- Preservar cambios del usuario; antes de editar, revisar `git status` y `git diff`. No usar comandos destructivos para limpiar cambios.

## MQTT y nodos

- Mosquitto escucha en 1883 para conexiones locales y por tailnet, y en 1884 en `0.0.0.0` con autenticacion para equipos de la LAN. No describir 1883 como puerto LAN ni como unico listener.
- MQTT usa credenciales por nodo y ACL por topico; nunca publicar claves en el repo. Para alta y configuracion de un nodo, seguir `docs/runbooks/anadir-equipo-sin-romper-seguridad.md` y la skill `nodos-mqtt` (Raspberry y ESP32).
