# Montar una estancia DE PRUEBA con su plano (guía por capítulos)

Hecho así con Salón, Garaje y Habitación 3 (2026-09-28) y con la Cocina
(2026-09-29). Para otra estancia, repetir los capítulos en orden: no hace falta
volver a explorar el código.

Todo lo de prueba es **simulado**: nodo ESP32 ficticio por estancia (IP de
documentación 192.0.2.x), `simulado: true` en luces, cerraduras y mandos, y nada
escucha sus topics. Inventario único: `~/elementos-prueba-2026-09-28.json` (una
clave por tanda). El usuario pedirá algún día ocultarlos o borrarlos: se hace
desde ese inventario, no buscando por nombre.

## Capítulo 1 — La imagen del plano
- Generador: `~/planos-generados/generar.py <clave>` (Workers AI, flux-1-schnell,
  estilo cenital común en `ESTILO`; una entrada por sala en `SALAS`).
- Cupo: Workers AI gratis da **429** cuando se acaba el del día. NVIDIA NIM
  (`~/.agents/keys/nvidia.key`, flux.1-schnell) no respondió a tiempo el 29-09.
  Si no hay cupo, usar una imagen ya generada de `~/planos-generados/`.
- Mirarla en miniatura (560 px, PIL del `.venv` de noxus) para situar las zonas.
- **Método bueno (gratis, sin cuenta) cuando la distribución importa**: boceto
  SVG con la distribución exacta → `~/planos-generados/kontext_hf.py <boceto.jpg>
  <salida.jpg> <seed> [prompt]`, que usa el Space público de Hugging Face
  FLUX.1 Kontext (API gradio: `/gradio_api/upload` + `/call/infer`). Convierte el
  boceto en render 3D con el estilo del resto respetando posiciones. OJO: el cupo
  anónimo de GPU da ~1 imagen; después responde `ERROR null` hasta que se renueva.
  Pollinations sin cuenta da 768 px con marca de agua y mala calidad: no sirve.
- **Si la distribución importa** (el usuario la pide concreta), la IA gratuita no la
  respeta: dibujar el plano en SVG a mano. Plantilla: `~/planos-generados/cocina_moderna.html`
  (1024×1024, suelo de roble en patrón, cuarzo, inox, sombras con feDropShadow).
  Render: `ui-shot <html> --w 1024 --h 1024 --out <dir>` → `<dir>/desktop.jpg`.
  Las coordenadas del SVG /1024 dan directamente el % de cada marcador.
- Cambiar la imagen de un plano existente: `planos.guardar` + `store._mutate` que
  actualice `imagen/ancho/alto` del plano, y borrar el fichero viejo de `planos/`.

## Capítulo 2 — Datos con el almacén (nunca editando el JSON a mano)
- Copia antes: `cp nodos_dinamicos.json ~/nodos_dinamicos.pre-<qué>-<fecha>.json`.
- Script modelo: `docs/runbooks/crear_estancia_cocina.py` (copiar y cambiar nombres, pines y posiciones). Usa `planos.guardar` + `store.add_plano`
  (el plano se llama como la estancia en minúsculas: así el plano abre la
  estancia), `store.add_room`, `add_light`, `add_sensor`, `add_door`,
  `add_puerta` (Puerta del plano = magnético + cerradura), `set_floor_position`
  con el `plano_id`, y un `store._mutate` final para `simulado: true` y los
  miembros de la estancia (`rooms[].entidades` = refs `colección:id`,
  `equipos_vista` = `nodes:<nodo>`).
- **Trampa**: `add_light(..., show_on_floor=True)` también lo coloca en el plano
  PRINCIPAL (50 %/50 %). Quitar después la clave `plano_1` de `posiciones` y poner
  `floor_top/left = None`, o no pasar `show_on_floor`.
- Posiciones en %: medir sobre la miniatura (x/560, y/560).

## Capítulo 3 — Apuntarlo
- Añadir una clave nueva al inventario `~/elementos-prueba-2026-09-28.json` con
  plano, estancia, nodo, refs y copia previa.
- Memoria `elementos-de-prueba-2026-09-28` (una línea con la tanda nueva).

## Capítulo 4 — Comprobar y reiniciar
- `.venv/bin/python -m pyflakes noxuscmmd/`, compilar `dashboard_page()` y
  `kiosco_page()`, `tests/ejecutar.py`, y `sudo systemctl restart noxus-panel`.

## Cocina (2026-09-29)
- Imagen: boceto SVG `~/planos-generados/cocina_moderna.html` → `cocina_layout.jpg`
  (muebles altos sobre fregadero y microondas con sus tiras LED, isla arrimada a
  la L con placa + extractor integrado y 4 taburetes, mesa de 6 abajo a la
  derecha, nevera y lavadora al final de la L, ventana derecha, puerta abajo).
- Imagen final 3D: `~/planos-generados/cocina_3d.jpg` (Kontext HF sobre el boceto).
- Alternativa con cupo de Cloudflare (Workers AI da 4006 «daily free
  allocation» hasta las 00:00 UTC; NIM Kontext solo admite imágenes de ejemplo):
  `~/planos-generados/restilizar_cocina.sh` y, si queda bien, sustituir la imagen
  como en el capítulo 1. Las posiciones no cambian.
- Posiciones (% top/left): luz principal 44/62, tira fregadero 18/40, tira
  microondas 40/14.5, foco cocinar 29/45.5, foco mesa 59/72, puerta 92/57;
  placa 36/38.5, extractor 36/46, horno (bajo la isla) 47/55, freidora 49/17,
  nevera 71/16, lavadora 85/15.
- Electrodomésticos (lavadora, nevera, placa, horno, extractor, freidora): colección
  `electrodomesticos`, ver `encargo-cocina-electrodomesticos.md`.
