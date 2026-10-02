# Plano + menús: altura, dos columnas y botón de ajustes

## Regla
Los menús de la derecha del plano (`Ahora mismo`, `Luces y aparatos`, `Equipos`; en
modo edición la tarjeta con pestañas, ver el último apartado) **nunca son más altos que el plano**
(su altura máxima es la del lienzo cuadrado) y van **centrados en
vertical** respecto a él. Si no caben en una columna pasan a **dos** (menú
secundario); si ni así, **scroll interno** estrecho (último recurso). Nunca estiran
la página. Sin sitio a la derecha (móvil, ventana estrecha) caen debajo, como antes.

## Cómo está hecho
- Estructura (`ui/dashboard/views/floor_plan.py`, `_lateral()`):
  `aside.nx-plano-lateral-der > .nx-plano-menu > .nx-plano-cols > .nx-plano-col ×2`.
  Normal: col A = Ahora mismo + Luces, col B = Equipos. Edición: A = En el plano,
  B = Añadir al plano. El modo edición usa el MISMO aside que el normal.
- CSS (`assets/nx.css`, bloque «Plano + menús»): el marco exterior cuadrado limita el tamaño
  por altura `dvh/svh` y ancho disponible; la imagen conserva su proporción nativa en un
  contenedor interno centrado. El aside no aporta altura (su `.nx-plano-menu` es `position:absolute`, con
  `inset: var(--nx-plano-top) 0 var(--nx-plano-bot) 0` = franja del lienzo: borde+relleno
  del marco 9 px + cabecera 48 px arriba). `.nx-plano-cols` se centra con
  `margin-block:auto` (centrado si cabe, arriba con scroll si no).
- Condiciones: `@media (min-width:901px)` y `@container nxplano` (el
  `.nx-plano-vista`): lado a lado desde 720 px; si no, `display:contents` y todo apilado.
- Dos columnas (`assets/nx.js`, último bloque «Plano: menús…»): mide la suma de alturas de
  los paneles en una columna frente a la altura del plano y pone `data-cols="2"` en el
  aside si no cabe **y** queda sitio para un plano mínimo de 500 px. La banda de histéresis
  evita oscilaciones al cambiar el tamaño. El ancho del aside no cambia al usar dos columnas.
  Sin JS: una columna con scroll.
- Medidas compartidas CSS/JS: `--nx-lat-col`, `--nx-lat-gap`, `--nx-plano-top/bot` en
  `.nx-plano-layout`. Si cambias el relleno del marco o el alto de la cabecera, cambia
  `--nx-plano-top/bot` (y `.nx-plano-cabecera` fija 48 px en escritorio).
- Subir versiones: `?v=` de `nx.css` en `noxuscmmd/noxuscmmd.py` y `_NX_JS` en
  `ui/pages/dashboard.py`.

## Botón de ajustes (sin lápiz ni «Editar»)
`ui/dashboard/components/boton_ajustes.py` → `boton_ajustes(on_click, titulo=..., activo=Var)`.
Icono `settings` (`settings-2` y `sliders-horizontal` no existen en la lista de Lucide de
Reflex 0.8.28). Solo engranaje; el nombre va en `aria-label`/`title`. Con `activo` muestra
«Listo» mientras el modo está activo. Estilo `.nx-ajustes-btn`. Usado en: plano (ajustes
del plano), Luces y aparatos, Equipos, Resumen (Personalizar), Modos, Inventario, Voz.
Diálogos y menús ⋮ también dicen «Ajustes…» (`actions_menu`, `form_dialog_content`).

## Probarlo (maqueta, ui-shot no ve el panel logueado)
HTML estático que carga `assets/nx.css` y `nx.js` con el mismo DOM/clases (normal y
edición, listas cortas/largas, 1440/1920/1180/900/390, plano 4:3), medido con Playwright
(altura del menú = altura del plano, `data-cols`, desborde horizontal) y una hoja de
contacto. Comprobado: menú == plano (mismo top y alto), centrado, 2 columnas con listas
largas, edición a la derecha en ≥880 px de contenedor, apilado debajo en estrecho.
No comprobado en el panel real: filas reales de «En el plano» (selector de icono de 90 px)
en la columna de 360 px.

## Ajuste 2026-10-02
- En escritorio, el marco exterior del plano conserva proporción 1:1. La imagen y `.nx-plan-container` mantienen la proporción propia del plano (`object-fit: contain`), centrados dentro del lienzo, para no deformar ni recortar y conservar las coordenadas de los marcadores.
- El lado del marco queda limitado por la altura de viewport restante (topbar, pestañas/cabecera y respiración) y el ancho disponible tras reservar el aside. Ambas vistas usan el mismo ancho de aside y la misma fila; la barra de edición ocupa la cabecera ya reservada.
- Los menús son como máximo la altura del marco, centrados en vertical y con scroll interno como último recurso. Dos columnas solo redistribuyen el contenido dentro del ancho fijo del aside, sin cambiar el tamaño del plano. El cambio usa una banda de histéresis para evitar oscilaciones al redimensionar.
- El selector visual de iconos aumenta solo el panel abierto: rejilla de 6 columnas, casillas grandes, límite de altura y scroll interno; trigger cerrado sin cambios.
- Suelos responsive: `--nx-side-min: 460px` y `--nx-col-min: 270px`; JS apila hasta que quepan plano + una columna, y solo permite dos columnas si caben ambas completas.
- Bajo 460 px de alto útil el marco conserva su suelo y el scroll vuelve al flujo vertical de la página; el aside mantiene centrado vertical cuando hay altura suficiente.
- En el aside, títulos no parten línea y las baldosas ocultan el estado en escritorio estrecho para reservar nombre elíptico e interruptor dentro de su tarjeta.

## Modo edición: una tarjeta con pestañas (2026-10-02)
- Antes: `En el plano` y `Añadir al plano` eran dos columnas pegadas y `Planos` un cajón
  `position:absolute` que flotaba encima: textos solapados y filas fuera de su tarjeta.
- Ahora el aside de edición es UNA tarjeta `.nx-plano-editor` (`_editor_plano()` en
  `floor_plan.py`) con tres pestañas segmentadas (`role=tablist`, flechas/Home/End en `nx.js`):
  **En el plano**, **Añadir** y **Planos** (ya no hay `_gestion_planos` fuera del layout). La pestaña
  activa es `NodesState.pestana_edicion_plano` (defecto `plano`, evento `elegir_pestana_edicion`).
- Altura: la tarjeta ocupa la franja del lienzo (≤ plano) y SOLO `.nx-ed-cuerpo` hace scroll
  (cadena flex con `min-height:0`). Sin sitio a la derecha cae debajo, a ancho completo y sin scroll interno.
- Ancho = el del aside normal (`--nx-lat-col: clamp(270px, 30cqw, 392px)`): `nx.js` copia a la edición
  las columnas que la vista normal usó (`window.__nxColsNormal`), así el plano mide LO MISMO en los dos modos.
- Filas (`.nx-ed-fila`): `container-type:inline-size` en la tarjeta (`nxedit`). Estrecha: línea 1 = icono +
  nombre con elipsis + familia, línea 2 = selector de icono, color, integrado, copiar y quitar (≥32 px de
  toque). ≥500 px: una línea. ≤340 px se oculta la familia, ≤400 los contadores de las pestañas.
  Todo hijo flex/grid lleva `min-width:0`; las listas son `grid-template-columns:minmax(0,1fr)`.
- Cabecera del plano en edición: `.nx-plano-instruccion` encoge y los botones no (`flex:none`).
  `nx.js` sube el scroll a 0 si la página llegó a desplazarse antes de pasar a `data-flujo="alto"`
  (`overflow-y:hidden` dejaba la fila de pestañas de plano cortada por arriba).
- Maqueta: `/tmp/.../scratchpad/maq2/` (`sync.sh` copia `nx.css`/`nx.js` frescos y regenera con `gen.py` el
  DOM literal de normal y de las 3 pestañas; `medir.sh '{json}'` = Playwright en la imagen de `ui-shot`:
  desbordes por tarjeta, solapes, `aside ≤ plano`). Si se pierde, rehacerla copiando clases y estilos de
  `floor_plan.py` y cargando el CSS de Radix Themes. Tamaños: 1575×896, 1913×1027, 1394×885, 1180×700,
  980×510, 390×844 (+360, 1280×1000, 1100×900, 768×1024).
- No comprobado en el panel real: filas con datos reales (nombres, planos) y los desplegables de Radix
  (iconos, color, copiar) sobre la tarjeta; la maqueta no los abre.
