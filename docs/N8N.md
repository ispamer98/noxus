# Puente con n8n

n8n corre en esta misma máquina (Docker Swarm, servicio `n8n_n8n`), escucha en
el `:5678` y sale a internet por su propio túnel: **https://n8n.noxuscmmd.uk**.

El puente tiene dos sentidos y son independientes: se puede usar uno sin el otro.

```
  ┌──────────────┐   1. sale cada evento del registro   ┌─────────┐
  │              │ ───────────────────────────────────► │         │
  │    NOXUS     │      POST <N8N_WEBHOOK_URL>          │   n8n   │
  │              │                                      │         │
  │              │ ◄─────────────────────────────────── │         │
  └──────────────┘   2. entra un aviso para un móvil    └─────────┘
                     POST /api/integraciones/aviso
```

## 1. Lo que sale: `domains/integrations/n8n.py`

Cuelga de `security/logs.registrar`, así que **sale todo lo que se apunta en el
registro de la casa** — luces, puertas, alarma, equipos, accesos. Filtrar es
trabajo del workflow: una lista de acciones interesantes en este lado obligaría
a tocar Python y reiniciar el panel cada vez que se quisiera automatizar algo
nuevo.

Volumen real de esta casa: ~65 eventos/día, unos 3 a la hora.

El envío va en un hilo aparte con una cola de 500. **Nunca bloquea ni levanta**:
que n8n esté caído no puede retrasar el encendido de una luz. Lo que no cabe se
descarta y se dice en el `journal`.

Cada evento llega a n8n así:

```json
{
  "origen": "noxus",
  "evento_id": 1466,
  "ts": 1788116439,
  "fecha": "2026-08-30",
  "hora": "21:00:39",
  "timestamp": "2026-08-30 21:00:39",
  "categoria": "luces",
  "accion": "LUZ_ENCENDIDA",
  "accion_legible": "Luz encendida",
  "usuario": "iPhone Ruben",
  "elemento": "Habitación",
  "detalle_extra": "",
  "detalle": "Habitación",
  "entidad": "light_78c43ca9",
  "grupo": ""
}
```

`fecha` y `hora` van partidas además del `timestamp` porque son las que el
workflow escribe en columnas distintas, y ya vienen en la hora **local** de la
casa: en n8n no hay que pelearse con zonas horarias.

`elemento` es el sujeto del evento. El `detalle` del registro sigue el convenio
`SUJETO · añadidos` (ver `logs.registrar`), y aquí ya viene partido para que el
workflow no tenga que conocer ese convenio.

## 2. Lo que entra: `POST /api/integraciones/aviso`

Manda un aviso Web Push a un dispositivo de la casa. **Solo avisos**: no acciona
nada. Para que n8n encienda o abra algo ya está `/api/voz`, que pasa por el
catálogo de comandos y comprueba permisos por dispositivo.

```bash
curl -X POST https://panel.noxuscmmd.uk/api/integraciones/aviso \
  -H "X-Noxus-Token: $N8N_TOKEN" -H "Content-Type: application/json" \
  -d '{"destino":"iPhone Ruben","titulo":"Luz encendida",
       "mensaje":"Has encendido «Habitación» a las 21:00.",
       "url":"/panel?vista=logs","tag":"n8n:luz:light_78c43ca9"}'
```

| campo | |
|---|---|
| `destino` | `"todos"`, un nombre de dispositivo, o una lista. **Obligatorio que exista**: un nombre que no esté suscrito devuelve 404 en vez de callarse |
| `mensaje` | el texto. Obligatorio |
| `titulo` | por defecto `NOXUS` |
| `url` | a dónde lleva al pulsarlo (`/panel?vista=logs`) |
| `tag` | agrupa: un aviso nuevo con el mismo tag sustituye al anterior |
| `silencioso` | sin sonido ni vibración |

Un destino desconocido es **error y no silencio** a propósito:
`push.enviar_notificacion` se calla si el nombre no está en la lista, y desde
n8n eso es indistinguible de «enviado» — la ejecución sale verde y al móvil no
llega nada.

## Seguridad

Las dos direcciones comparten un secreto, `N8N_TOKEN`, que viaja en la cabecera
`X-Noxus-Token`. Se compara con `secrets.compare_digest`.

- **Sin `N8N_TOKEN` en el `.env` la puerta de entrada se queda cerrada**, no
  abierta: un `.env` a medio rellenar no puede dejar que cualquiera con la URL
  escriba a los teléfonos de la casa.
- No se reutiliza la cookie de sesión ni la clave de voz porque quien llama es
  un servicio: no tiene dueño y no debe heredar los permisos de nadie.
- En n8n el token vive en una **credencial** (`Noxus token`, tipo Header Auth),
  no en el JSON del workflow. Por eso `integrations/n8n/noxus-luces.json` se
  puede tener en un repo público.

## El corta-bucles

n8n manda un aviso → Noxus lo apunta en el registro → el apunte sale hacia n8n →
n8n manda otro aviso → …

Se corta en `n8n.NO_SALEN`, que lleva la acción `AVISO_N8N` con la que se apunta
todo lo que entra por `/api/integraciones/aviso`. Está en el lado de Python y no
en el filtro del workflow **a propósito**: así no depende de que la
configuración de n8n esté bien escrita. Lo cubre `tests/test_n8n.py`.

## Configuración

En el `.env` (que está en `.gitignore`):

```
N8N_WEBHOOK_URL=http://127.0.0.1:5678/webhook/noxus-eventos
N8N_TOKEN=<secreto>
```

`N8N_WEBHOOK_URL` vacía = integración apagada, sin hilo y sin coste.

Direcciones que se alcanzan **desde el contenedor de n8n** hacia este panel
(las cuatro valen; el workflow usa la de Tailscale por ser fija):

| | |
|---|---|
| `100.98.98.1:8000` | Tailscale — la que usa el workflow |
| `172.18.0.1:8000` | `docker_gwbridge` |
| `192.168.1.x:8000` | LAN por cable |
| `panel.noxuscmmd.uk` | por internet, dando la vuelta por Cloudflare |

## El workflow «Noxus · Luces»

`integrations/n8n/noxus-luces.json`. Instalación:

```bash
bash integrations/n8n/instalar.sh
```

Crea la credencial e importa el workflow por la CLI de n8n dentro del
contenedor (la API pública pediría una API key que hay que crear a mano). Es
idempotente: volver a lanzarlo actualiza en vez de duplicar.

Lo que hace, en orden:

1. **Evento desde Noxus** — webhook `POST /webhook/noxus-eventos`, con Header Auth.
2. **¿Es una orden de luz?** — pasa `categoria == "luces"` y acción
   `LUZ_ENCENDIDA` o `LUZ_APAGADA`. `LUZ_CREADA` / `LUZ_EDITADA` / `LUZ_ERROR`
   se quedan fuera.
3. **Registrar el evento** — deja la fila normalizada en `registro`. Para
   guardarla fuera de n8n (Sheets, Postgres, Airtable), se enchufa ese nodo
   justo detrás y se mapea `registro`; no hay que tocar nada más.
4. **¿Hay equipo al que avisar?** — `sistema` es lo que dispara el propio panel
   (una automatización, un sensor) y `desconocido` una pestaña sin avisos
   activados: ninguno de los dos es un móvil.
5. **Avisar al equipo en Noxus** — vuelve por `/api/integraciones/aviso`.

Para tratar otra cosa (puertas, alarma, equipos), se duplica el workflow y se
cambia el filtro del paso 2: los eventos **ya están llegando todos**.
