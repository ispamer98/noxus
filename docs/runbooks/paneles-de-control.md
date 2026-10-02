# Paneles de control y electrodomésticos simulados (2026-09-29)

Guía para añadir un tipo de electrodoméstico nuevo o rehacer el panel de algo
del plano. Base hecha por Codex (encargo en `encargo-cocina-electrodomesticos.md`;
se paró a medias sin cupo) y rematada por Claude.

## Capítulo 1 — Piezas
- Datos: colección `electrodomesticos` en `nodes/store.py` (`TIPOS_ELECTRO`,
  `ICONOS_ELECTRO`, `add/update/delete_electro`, `set_electro_estado`). Posiciones
  por plano como el resto (`COLECCIONES_EN_PLANO`, `_sincronizar_planos`).
- Simulador puro: `domains/electro/simulador.py`: `comando(item, accion, valor,
  ahora)` valida y devuelve el estado a guardar; `vista(item, ahora)` deriva fase,
  `texto`, `restante` (s), `fin` (epoch ms), `en_marcha`, `progreso`. Tipos:
  lavadora, nevera, placa, horno, extractor, freidora, aire.
- Estado: `domains/electro/state.py` (`ElectroState.electro_cmd`, permiso EQUIPOS
  + estancia de la tablet; refresco cada 10 s con `sesiones.guardia`).
- UI: `ui/dashboard/components/panel_control.py` (cabecera, botón, segmentado,
  stepper, anillo) y `electro_panel.py` (un panel por tipo). CSS: bloque
  «Paneles de control» de `assets/nx.css` (`nx-control-*`, `nx-placa-*`,
  `nx-aire-*`; tonos con `data-tono` safe/warn/guard/info/lamp). Cuenta atrás en
  el cliente: `.nx-cuenta[data-fin]` en `assets/nx.js`.
- Plano: `_electro_marker_de` en `ui/views/device_list.py` (filtra por
  `NodesState.plano_actual` en el cliente). Ventana: `electro_windows_layer` en
  `ui/dashboard/windows.py`. Tablet: sección «Cocina y aparatos» y hoja
  `overlay_kind == "electro"` en `ui/pages/kiosco.py`.

## Capítulo 2 — Añadir un tipo (p. ej. lavavajillas)
1. `simulador.py`: nombre en `TIPOS`, valores por defecto en `_estado`, un
   `_comando_<tipo>` y un `_vista_<tipo>`, y registrarlos en los dos diccionarios.
2. `store.py`: `TIPOS_ELECTRO` e `ICONOS_ELECTRO` (comprobar el icono en
   `LUCIDE_ICON_LIST`).
3. `electro_panel.py`: `_<tipo>(e, eid)` con las piezas de `panel_control` y una
   entrada en `rx.match`. Usar `e["estado"].to(dict)` (sin `.to` no compila).
4. `tests/test_electro.py` (tiempos con `T0`: 0 es «sin fecha» para el simulador).
5. Crear el elemento con `store.add_electro` + `set_floor_position` + miembro de la
   estancia (`electrodomesticos:<id>`), como en `estancia-de-prueba.md`.

## Capítulo 3 — Paneles rehechos con el mismo lenguaje
- `equipo_contenido`, `puerta_contenido`, `_aparato_window` en `windows.py`; la
  tablet reutiliza `equipo_contenido` y `puerta_contenido` (hoja «puerta»: Abrir,
  Mantener abierta = desbloqueada, Mantener cerrada = bloqueada).
- Tablet y cerraduras: `set_door_hold` permitido en el portero y con
  `denegar_entidad` (la cerradura debe ser de una Puerta de SU estancia).

## Trampas pagadas
- `icono()` necesita color por defecto (`currentColor`) para usarse sin color.
- `anillo(progreso=0)` con un int: el estilo no puede llamar a `.to`.
- El store llamaba a `_asegurar_posiciones` (de mandos) para electros: KeyError.
- Codex en segundo plano puede quedarse parado sin cupo sin avisar: si su log no
  avanza en ~10 min, cancelar y rematar a mano.
