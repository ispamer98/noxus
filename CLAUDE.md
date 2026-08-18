# noxuscmmd — panel de domotica

Reflex 0.8.28. Controla la **alarma, los accesos y los dispositivos de una casa
real**. Un fallo aqui se nota en el mundo fisico, no en una pantalla.

Servicio `noxus-panel` (front :3000, back :8000) → https://panel.noxuscmmd.uk
Repo `ispamer98/noxus` — **PUBLICO**.

## Estructura

```
noxuscmmd/
  core/      connectivity, sensors, ssh_manager      infraestructura
  domains/   security cameras nodes access automations devices
             notifications infra                     logica (state.py en cada uno)
  ui/dashboard/  views/ components/                  solo pinta
```

La logica va en `domains/<x>/state.py`. `ui/` no toma decisiones de negocio.

## Comandos

```bash
.venv/bin/python -m pyflakes noxuscmmd/     # comprobacion rapida
journalctl -u noxus-panel -n 50 --no-pager  # logs
sudo systemctl restart noxus-panel          # AVISA ANTES: el panel esta en uso
```

Python del venv: **3.11**. Nunca `python3` suelto.

## Reglas

- Los JSON de la raiz (`estado_seguridad.json`, `nodos_dinamicos.json`,
  `grupos_armado.json`...) son **datos en vivo de la casa**. Para probar,
  copia a un temporal y apunta con las variables de entorno; no escribas sobre
  ellos. Escritura siempre atomica (`.tmp` + `os.replace`).
- El registro de eventos ya **no** es `logs.json`: vive en `historico.db`
  (SQLite en modo WAL, `domains/security/logs_store.py`) y no tiene tope de
  entradas. `logs.json` se quedo congelado como red de seguridad: se importo una
  sola vez y no se lee ni se escribe. Para probar, `HISTORICO_DB=/tmp/algo.db`.
  Los `historico.db-wal` y `-shm` son parte de la base de datos, no basura.
- `fotogramas/` son las fotos que guarda la alarma al saltar
  (`domains/cameras/fotogramas.py`): imagenes del interior de la casa. Estan en
  `.gitignore` y **no** se sirven como estatico — van por
  `/api/fotograma/<nombre>`, que comprueba la sesion. No las muevas a `assets/`.
- `rxconfig.py` lleva `state_auto_setters=False` (desde la fase 1): ya **no** se
  genera un `set_<var>` por cada var publica, asi que ningun navegador puede
  escribir en el estado por una via que no hayas escrito tu. Si una var necesita
  setter, declaralo a mano con `@rx.event`. Lo que no deba salir al cliente,
  igual que siempre: `_` delante.
- Repo publico: `tinytuya.json`, `webos_key.json` y `.env` llevan credenciales
  reales y estan en `.gitignore`. Revisa `git status` antes de cualquier `git add`.
- `.web/` es generado: ni leer ni editar.

Detalles de Reflex → skill `reflex`. Despliegue → skill `despliegue`.
