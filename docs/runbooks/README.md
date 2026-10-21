# Runbooks de noxus — índice

Cada cambio de cierto tamaño deja aquí su guía por capítulos, para repetir algo
parecido otro día sin volver a explorar el código.

| Guía | Para qué |
|---|---|
| [estancia-de-prueba.md](estancia-de-prueba.md) | Estancia de prueba con plano, luces, puerta (Salón, Garaje, Habitación 3, Cocina) |
| [porton-pruebas-tablet.md](porton-pruebas-tablet.md) | Maniobra del portón (1 o 2 pulsos), pantalla Pruebas, armar desde la tablet |
| [movimiento-dispara-alarma.md](movimiento-dispara-alarma.md) | Movimiento en cámaras con la casa armada dispara la alarma |
| [humidificador-ir.md](humidificador-ir.md) | Mando IR y accesorio «Humidificador» (Simpeak 550 ml), pendientes de aprender las señales |
| [layout-plano-menus.md](layout-plano-menus.md) | Plano + menús: altura máxima = plano, dos columnas, edición a la derecha, botón de ajustes (engranaje) |
| [permisos-obligatorios.md](permisos-obligatorios.md) | Fin del rodaje: permisos siempre en vigor + agujeros cerrados en la revisión del 2026-10-02 |
| [anadir-equipo-sin-romper-seguridad.md](anadir-equipo-sin-romper-seguridad.md) | Receta única para añadir un nodo MQTT, un aparato o código nuevo sin chocar con permisos/MQTT autenticado |

## Logo → volver arriba

El logo de escritorio y móvil devuelve el contenedor principal al principio de la vista.
También resetea un `PopoverContent` desplazable de detalle si está abierto.
Funciona con clic, Enter y Espacio; respeta `prefers-reduced-motion`.
