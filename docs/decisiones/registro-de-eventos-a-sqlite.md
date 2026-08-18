---
tipo: decision
fecha: 2026-08-17
proyecto: noxuscmmd
estado: aceptada
---

# El registro de eventos pasa a SQLite

## Contexto

`logs.json` era una lista que se reescribía **entera** en cada evento, con
`flock` alrededor y tope de 1.500 entradas. Dos techos ya tocados:

- **Tres semanas de memoria.** A los ~70 eventos diarios de esta casa, 1.500
  entradas son veintitantos días. Sirve para «qué pasó anoche»; no sirve para
  gráficas por hora y día, ni para deducir los horarios reales de las últimas
  semanas (simulación de presencia).
- **El coste de escribir crecía con lo guardado.** Abrir una puerta
  reserializaba los 286 KB del fichero completo.

## Decisión

**SQLite en modo WAL** (`historico.db`, `domains/security/logs_store.py`), sin
tope de entradas. `logs.py` se queda con el vocabulario (categorías, etiquetas,
interpretación de las entradas antiguas) y delega la persistencia.

`logs.json` se importó **una vez** y quedó congelado: no se lee ni se escribe.
Es la red para volver atrás.

## Alternativas descartadas

| Alternativa | Por qué no |
|---|---|
| Seguir con JSON y subir el tope | No arregla nada: el coste de escribir es el fichero entero, así que subir el tope lo empeora. |
| JSONL (una línea por evento, append) | Arregla escribir, no leer: filtrar por fechas o contar por categoría obliga a recorrerlo todo en Python en cada recarga y por sesión. |
| Rotar ficheros por mes | Consultar un rango que cruce meses pasa a ser trabajo del que consulta. Es reinventar un índice a mano. |
| Postgres / base externa | Un servicio más que puede estar caído cuando salta la alarma. SQLite es un fichero: si el panel arranca, el registro está. |

## Consecuencias

- **Las copias de seguridad necesitan trato aparte.** Un `.db` con WAL no se
  copia con `shutil` (la copia saldría sin lo que aún viva en el `-wal`), no se
  valida con `json.load` y **no se restaura sustituyendo el fichero**: dejar un
  `.db` nuevo con el `-wal` del anterior al lado no es restaurar, es corromper.
  `backups.py` copia con `VACUUM INTO`, valida con `integrity_check` y restaura
  volcando dentro de la base viva.
- **Quien pinta una lista tiene que acotar.** `SecurityState.logs_recientes` es
  una Var pública: mandaba el histórico entero al navegador de cada sesión, y
  cabía solo porque el fichero tenía tope. Ahora va a 200. La pestaña Registros
  carga una ventana de 3.000 y lo dice en pantalla si el intervalo tiene más;
  la exportación a CSV sí va al intervalo completo.
- **El `sync_loop` ya no relee para comparar.** Compara una marca de dos
  números (`logs_store.senal()`) y solo relee si algo cambió.
- `*.db`, `*.db-wal` y `*.db-shm` al `.gitignore`: el repo es público y esto es
  el histórico de una casa.

## Cómo revertirla

Volver los cinco ficheros a la versión anterior. `logs.json` sigue completo a
fecha del cambio; se perderían del listado los eventos guardados en la base
entre el estreno y la vuelta atrás. `historico.db` no hace falta borrarlo.

## Rastro

Fase 5.1 del plan. Estrenado el 2026-08-17: 1.465 eventos importados, 176 KB de
base frente a 286 KB de JSON. Relacionado: [[setters-automaticos-siguen-activos]].
