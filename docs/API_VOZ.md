# API de voz: lectura para Noxus

La API bajo `/api/voz` sirve al asistente local sin darle una sesión del panel.
Todas estas rutas son `GET`, no actúan sobre la casa y requieren una clave de
voz en la cabecera `X-Noxus-Clave`. La clave se genera para el dispositivo en
el panel; no se pasa por la URL ni se guarda en scripts o repositorios.

El rol se valida en cada petición con la capacidad `VER` (la misma de
`GET /api/voz` y `GET /api/voz/estado`); `/camaras` y `/camaras/{id}/foto` exigen
además `CAMARAS`. La clave es la misma que la de `POST /api/voz`, que sí actúa:
el dispositivo de Noxus debe tener un rol sin `ARMAR` ni `PUERTAS` si solo ha de leer. Una clave revocada o de un dispositivo
sin acceso recibe `401` o `403`. Las rutas comparten la infraestructura y los
límites de la API de voz existente; los listados añaden topes propios para no
devolver un histórico ilimitado.

```bash
PANEL='https://panel.noxuscmmd.uk'
CLAVE_VOZ='<tu-clave-de-voz>'
curl -sS -H "X-Noxus-Clave: $CLAVE_VOZ" "$PANEL/api/voz/sensores"
```

## Sensores

`GET /api/voz/sensores` lista los sensores del catálogo: `id`, `nombre`,
`estancia`, `tipo` (`door`, `tamper`, `pir` o `generic`), `estado` y la marca
del último cambio (`cambio` y `cambio_ts`). Un contacto magnético se expresa
como `abierto`/`cerrado`; tamper, PIR y genéricos como `disparado`/`normal`.
Si aún no hay un cambio registrado, la marca es `null`.

## Alarma

`GET /api/voz/alarma?n=20` devuelve el armado general, modo, grupos, las zonas
abiertas de cada grupo y `zonas_abiertas_que_impiden_armar`, además de los
últimos eventos de alarma. `n` vale de 1 a 50 (el exceso se recorta a 50).
Cada evento trae la acción, la hora, el grupo y quién lo realizó.

## Histórico

`GET /api/voz/eventos?desde=&tipo=&dispositivo=&n=` consulta `historico.db` en
modo de solo lectura. `desde` acepta segundos epoch o ISO-8601; `tipo` coincide
exactamente con categoría o acción; `dispositivo` es el id de entidad. `n`
vale de 1 a 100 (por defecto 50). No se incluyen fotogramas ni valores que
parezcan PIN, claves, tokens o contraseñas.

```bash
curl -sS -H "X-Noxus-Clave: $CLAVE_VOZ" \
  "$PANEL/api/voz/eventos?tipo=alarma&n=25"
```

## Cámaras

`GET /api/voz/camaras` lista `id`, nombre, estancia, si go2rtc tiene un
productor activo (`en_linea`) y si admite foto. Solo una cámara de tipo go2rtc
puede generar una instantánea:

```bash
curl -sS -H "X-Noxus-Clave: $CLAVE_VOZ" \
  -o foto.jpg "$PANEL/api/voz/camaras/ID_DE_CAMARA/foto"
```

`GET /api/voz/camaras/{id}/foto` entrega únicamente un JPEG con `Cache-Control:
no-store`, máximo 2 MiB y espera máxima de 2 segundos. Si la cámara está
parada, no tiene fuente o no responde, devuelve JSON con un error claro; no
expone la URL ni credenciales del stream.
