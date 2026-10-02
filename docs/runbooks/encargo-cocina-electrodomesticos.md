# Encargo: electrodomésticos simulados + paneles de actuación (2026-09-29)

Encargo escrito por Claude para Codex. Se guarda como guía: para añadir otro
tipo de electrodoméstico o rehacer un panel, repetir este mismo esquema.

## Objetivo
Una familia nueva de elementos, **electrodomésticos** (lavadora, nevera, placa de
inducción, horno, extractor, freidora de aire), SIMULADOS (sin hardware), con
paneles de actuación bonitos en el panel (ventana flotante del plano) y en la
tablet (hoja a pantalla completa). Y un rediseño común de los paneles de
actuación existentes (equipo/PC, puerta, aparato) con el mismo lenguaje visual.

## Contexto (proyecto Reflex 0.8.28, ver CLAUDE.md y AGENTS/skills `reflex`, `python-experto`)
- Datos: `noxuscmmd/domains/nodes/store.py` (colecciones en `nodos_dinamicos.json`,
  `_COLLECTIONS`, `_apply_defaults`, `_add/_update/_delete`, `_mutate` atómico,
  `floor_fields`, `_en_plano`). Referencias de estancia `"<colección>:<id>"`
  (`rooms[].entidades`, `referencia_en_estancia`).
- Estado del plano: `noxuscmmd/domains/nodes/state.py` (NodesState: `*_on_floor`,
  `kiosco_*`, `_miembros_kiosco`, catálogos de colecciones colocables en el plano).
  Seguir de punta a punta cómo está hecha la colección `ir_remotes` o `hosts`
  (alta en catálogo del plano, marcador, ventana, miembros de estancia, kiosco).
- Marcadores: `noxuscmmd/ui/views/device_list.py` (`_marker`, listas `rx.foreach(NodesState.*_on_floor ...)` del panel y del kiosco).
- Ventanas flotantes: `noxuscmmd/ui/dashboard/windows.py` (`floating_windows_layer`,
  `_equipo_window`, `_puerta_window`, `_aparato_window`, `_chip`, `_boton_icono`).
- Tablet: `noxuscmmd/ui/pages/kiosco.py` (hojas `_hoja`, `KioscoState.abrir_overlay`
  en `domains/nodes/kiosco_state.py`, baldosas `_quick_action`).
- Permisos: `domains/auth/permisos.py` (`denegar`, `denegar_entidad`) y el portero
  `core/portero.py` (lista cerrada de eventos del kiosco + `requiere`).
- Estilos: `assets/nx.css` (tema Obsidiana, tokens `--nx-*`: `--nx-s1..3`,
  `--nx-line*`, `--nx-text*`, `--nx-muted`, `--nx-info/safe/guard/lamp/warn` y sus
  `-rgb`). Al cambiarlo, subir `?v=` en `noxuscmmd/noxuscmmd.py`. JS en `assets/nx.js`
  (subir `_NX_JS` en `ui/pages/dashboard.py`).
- Iconos propios: `ui/dashboard/components/icono_propio.py` (`icono()`).
- Bucle de fondo: una tarea POR SESIÓN que no muere se come la CPU; usar
  `core/sesiones.guardia` como `SecurityState.sync_loop`, y `self` dentro es StateProxy.

## Qué hacer
1. **Datos** (`store.py`): colección `electrodomesticos` (`_add(..., "electro", ...)`),
   campos `name`, `tipo` ∈ {lavadora, nevera, placa, horno, extractor, freidora},
   `node_id`, `node_name`, `simulado: True`, campos de plano (`floor_fields`,
   `plano`), `estado: dict`. `add_electro/update_electro/delete_electro`,
   `set_electro_estado(id, estado)`.
2. **Simulador puro** `noxuscmmd/domains/electro/simulador.py` (NO importa reflex):
   `comando(item, accion, valor, ahora) -> estado` que valida y aplica; y
   `vista(item, ahora) -> dict` que deriva fase, restante (s), `fin` (epoch ms) y
   textos. Tiempos guardados como epoch; lo derivado se calcula al leer.
   - lavadora: programas (algodón 180 min, sintéticos 90, rápido 30, delicado 60,
     eco 210, centrifugado 15), temp (frío/30/40/60/90), rpm (800/1000/1200/1400);
     elegir_programa/temp/rpm, iniciar, pausar, reanudar, cancelar; fases lavado →
     aclarado → centrifugado por fracción de tiempo; terminado; puerta bloqueada en marcha.
   - nevera: consigna nevera 1..8 (4), congelador −24..−16 (−18); super_frío,
     super_congelación, vacaciones; puerta abierta (simulable) con aviso si > 60 s
     y temperatura «actual» que sube un poco con la puerta abierta.
   - placa: 4 zonas, nivel 0..9 por zona (+/− y directo), boost, temporizador por
     zona (min, apaga al acabar), bloqueo niños, apagar todo, calor residual «H»
     5 min tras apagar.
   - horno: encendido, modo (convencional, aire, grill, grill+aire, solo abajo,
     descongelar), temperatura 50..250 paso 5, temporizador (min) que apaga al
     acabar y deja «Terminado», precalentando hasta alcanzar temperatura (≈10 °C/min), luz.
   - extractor: velocidad 0..4 (4 = intensivo), luz, apagado temporizado (min).
   - freidora: encendido, temperatura 80..200, tiempo 1..60 min, programas
     (patatas 200/20, pollo 180/25, pescado 160/12, verduras 170/15, recalentar
     150/5), iniciar/pausar/reanudar/cancelar, aviso «agitar» a mitad.
   Nunca hay MQTT/SSH: deja un comentario de dónde irá el hardware real.
3. **Estado Reflex** `noxuscmmd/domains/electro/state.py` (`ElectroState`): lista para
   plano y kiosco con la vista derivada; `electro_cmd(electro_id, accion, valor: str)`
   con `permisos.denegar_entidad(self, permisos.EQUIPOS, f"electrodomesticos:{id}")`,
   registro en logs (`security/audit.registrar`, categoría equipos o la que encaje),
   y refresco periódico ligero (≤ cada 10 s y solo con sesión viva) para que se vea
   el cambio de fase. Cuenta atrás en el cliente: elementos con clase `nx-cuenta` y
   `data-fin` (epoch ms) que actualiza `assets/nx.js` cada segundo (mm:ss / h:mm:ss).
4. **Plano y estancias**: colocables en el plano como el resto (catálogo del modo
   edición), marcador con icono por tipo (lucide: washing-machine, refrigerator,
   flame / cooking-pot, microwave o oven si existe en el LUCIDE_ICON_LIST instalado,
   fan, air-vent…; comprobar con `reflex.components.lucide.icon.LUCIDE_ICON_LIST`),
   color ámbar cuando está en marcha. Clic → ventana flotante en el panel; en el
   kiosco → hoja (`overlay_kind == "electro"`). Miembros de estancia
   `electrodomesticos:<id>`; sección «Cocina» en los controles del kiosco.
5. **Paneles bonitos** (componente común nuevo, p. ej.
   `ui/dashboard/components/panel_control.py` + bloque CSS «Paneles de control» en
   nx.css): cabecera con icono grande y píldora de estado; anillo de progreso con el
   restante; chips de programa; controles segmentados; steppers +/− grandes; la placa
   dibujada como 4 círculos 2×2 que brillan en rojo según el nivel. Escritorio y
   móvil; en la tablet, dianas ≥ 44 px. Sin librerías nuevas.
6. **Rediseñar con ese mismo componente** los paneles existentes: `_equipo_window`
   (PC: encender, apagar, reiniciar, botones propios), `_puerta_window`,
   `_aparato_window` en windows.py, y en la tablet `_equipo_contenido` (el selector
   de acciones de PC es feo) y las hojas. Mismos eventos que ahora.
7. **Tablet: cerradura de puertas**. Hoy la baldosa de puerta solo hace pulso y pasa
   `puerta["id"]` (id de la Puerta del plano) a `NodesState.open_door`, que espera el
   id de la cerradura (`lock_id`): comprobar y corregir. La baldosa abre una hoja
   (`overlay_kind == "puerta"`) con estado (abierta/cerrada, cerradura
   liberada/bloqueada, maniobra) y tres acciones: Abrir (pulso), Mantener abierta
   (desbloqueada), Mantener cerrada (bloqueada). Permitir `NodesState.set_door_hold`
   al kiosco en el portero y añadirle a `set_door_hold` la comprobación
   `denegar_entidad` igual que `open_door` (que la cerradura sea de SU estancia;
   verificar que `referencia_en_estancia` acepta la cerradura de una Puerta del plano
   que está en la estancia).
8. **Pruebas** (`tests/`, se lanzan con `.venv/bin/python tests/ejecutar.py`, no es
   pytest): `tests/test_electro.py` con el simulador (cada tipo: comandos válidos e
   inválidos, restante y fin, apagado por temporizador) y actualizar
   `tests/test_portero.py` (el kiosco ya puede `set_door_hold`; `ElectroState.electro_cmd`
   permitido). Registrar el módulo en `tests/ejecutar.py`.

## Restricciones
- Hay muchos cambios del usuario sin commitear: no revertir nada ajeno, no `git
  checkout/reset/stash`, no commitear.
- No escribir en los JSON vivos de la raíz (`nodos_dinamicos.json`…) ni en
  `historico.db`; las pruebas usan la casa de pruebas de `tests/comun.py`.
- No reiniciar servicios. No tocar `.web/`. Python del `.venv`.
- `state_auto_setters=False`: cualquier setter, a mano con `@rx.event`.
- Lo que no deba ir al cliente, con `_` delante.

## Hecho cuando
- `.venv/bin/python -m pyflakes noxuscmmd/ tests/` sin avisos nuevos.
- `.venv/bin/python -c "from noxuscmmd.ui.pages.dashboard import dashboard_page; from noxuscmmd.ui.pages.kiosco import kiosco_page; dashboard_page(); kiosco_page()"` compila.
- `.venv/bin/python tests/ejecutar.py` sin fallos nuevos (hoy falla solo
  «descarta el día de la migración», ajeno).
- Entrega: resumen en 5 líneas y lista de archivos cambiados.

## Segunda tanda: aire acondicionado como panel (no como mando)
Tipo nuevo `aire` en el simulador, el estado y los paneles, con las funciones de un
mando de pared de split: encendido; modo (frío, calor, seco, ventilación, auto)
con su color (frío azul, calor ámbar); consigna 16–30 °C en pasos de 0,5 con
stepper grande y lectura tipo termostato (temperatura ambiente simulada que se
acerca a la consigna con el tiempo); ventilador (auto, 1, 2, 3, turbo); lamas
(fijo, oscilar); eco; modo noche; temporizador de apagado (30 min, 1 h, 2 h,
4 h, 8 h) con cuenta atrás; icono lucide `air-vent`. Misma estética que el resto
de paneles (componente común). Pruebas en `tests/test_electro.py`.
