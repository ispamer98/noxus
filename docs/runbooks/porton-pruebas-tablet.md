# Portón con maniobra, pantalla Pruebas y armado desde la tablet (2026-09-29)

## Capítulo 1 — Maniobra de una puerta/portón
- Ficha de la cerradura (`doors`): `modo` (`pulso` | `dos_pulsos`,
  `store.MODOS_CERRADURA`), `apertura_s`, `espera_s`, `cierre_s` (todo a 0 =
  puerta normal). Se editan en Accesos → añadir/editar puerta.
- Hardware: `operations.pulse_door` (en `dos_pulsos` da el pulso de cierre al
  acabar apertura+espera) y `operations.hold_door` (mantener; en `dos_pulsos` un
  pulso solo si cambia de estado). Automatizaciones usan lo mismo.
- En `dos_pulsos` el eco MQTT del relé se ignora (`sensor_events.on_binary_sensor`).
- Plano: `NodesState._puerta_con_estado` da `ambar` (solo moviéndose en un
  portón), `maniobra` e `icono_plano`. Parejas de iconos cerrado/abierto en
  `_ICONOS_PUERTA`; el portón levantado (`warehouse-open`) es un SVG propio en
  `ui/dashboard/components/icono_propio.py` (añadir más ahí).
- Pruebas: `tests/test_porton.py` (relé espiado, nada sale a la casa).

## Capítulo 2 — Pantalla Pruebas (Ajustes → Pruebas)
- Estado: `domains/infra/pruebas_state.py`, tabla `_GRUPOS` (clave, título, icono,
  tabla `sensor`|`equipo`, palabras y colores de los dos estados). Un tipo nuevo =
  una fila en `_GRUPOS` y su reparto en `_refrescar`.
- Vista: `ui/dashboard/views/pruebas.py`, `<details>` nativo por grupo; estilos en
  `assets/nx.css`, bloque «Pruebas» (`nx-pr-*`). Todo simulado (core/pruebas.py).

## Capítulo 3 — Permiso nuevo para la tablet
1. `permisos._POR_ROL[store.KIOSCO]` += capacidad.
2. `core/portero.py` → añadir los eventos concretos a la lista `kiosco`
   (nunca estados enteros que editen configuración).
3. Botón en `ui/pages/kiosco.py` (cabecera o sección) y, si hay avisos, montarlos
   en su `nx-floating-notices`.
4. Actualizar `tests/test_kiosco.py` y `tests/test_portero.py`.

## Capítulo 4 — Antes de reiniciar
- `pyflakes`, compilar `dashboard_page()` y `kiosco_page()` (pyflakes no ve
  errores de Var), `tests/ejecutar.py`, subir `?v=` de nx.css/nx.js si cambiaron.
