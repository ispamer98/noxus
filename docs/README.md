# noxuscmmd

Panel de domótica autoalojado. Reúne en una sola interfaz web los cacharros de
una casa —luces, enchufes, climatización, televisores, cámaras y una alarma con
sus grupos de armado— y los expone en un panel al que se entra desde el móvil.

Construido con [Reflex](https://reflex.dev): Python de punta a punta, sin escribir
JavaScript. Corre en un servidor propio de la casa, no en la nube de nadie.

## Cómo está organizado

El código se reparte **por dominios**, no por tipo de archivo. Cada dominio es una
parcela del problema con su propio estado y su propia lógica:

```
noxuscmmd/
├── core/          conectividad, sensores y acceso por SSH a otras máquinas
├── domains/       una carpeta por área, cada una con su state.py
│   ├── security/      alarma, grupos de armado
│   ├── cameras/       cámaras y videowall
│   ├── nodes/         máquinas de la red
│   ├── devices/       registro de aparatos
│   ├── access/        control de accesos
│   ├── automations/   automatizaciones
│   ├── notifications/ avisos push
│   └── infra/         estado de la infraestructura
└── ui/dashboard/  vistas y componentes — solo pintan
```

La regla que sostiene todo: **la lógica vive en `domains/<x>/state.py` y la
interfaz solo dibuja**. Si un componente de `ui/` empieza a decidir cosas de
negocio, está en el sitio equivocado.

## El estado vive en archivos, no en una base de datos

Los `.json` de la raíz del proyecto guardan la situación real de la casa en cada
momento. Se leen y se escriben en caliente mientras el panel funciona, así que
**toda escritura tiene que ser atómica** (a un `.tmp` y luego `os.replace`): un
JSON cortado a medias impide que el servicio arranque.

Esos archivos no están en el repositorio —contienen la configuración concreta de
una instalación real— y por eso el proyecto arranca vacío al clonarlo.

## Arrancar

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/reflex run
```

El panel escucha en el 3000 y su backend en el 8000. En el servidor de casa corre
como servicio de systemd y sale a internet por un túnel de Cloudflare, sin abrir
ni un puerto en el router.

## Documentación

- [`decisiones/`](decisiones/) — decisiones tomadas y por qué, incluida la que
  afecta a la seguridad del estado expuesto al navegador.
- [`runbooks/`](runbooks/) — procedimientos repetibles.
- [`depuracion/`](depuracion/) — averías resueltas.
