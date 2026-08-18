"""
Pulsación larga sobre una tarjeta = su menú de acciones.

En el móvil, el menú «⋮» es un objetivo de 24 píxeles en la esquina de una
tarjeta que ocupa la pantalla de ancho. Mantener el dedo encima de la tarjeta es
el gesto que ya usa todo el mundo, y es mucho más fácil de acertar.

CÓMO ENCUENTRA EL MENÚ, que es lo único con truco: no hace falta marcar ni una
tarjeta. Al soltar una pulsación larga, se sube por los padres del elemento
tocado hasta encontrar el primero que CONTENGA un «⋮» (marcado con
data-nx-menu en components/actions_menu.py) y se le da un clic. Ese primer
ancestro con menú es, por construcción, la tarjeta que se está tocando. Así
cualquier tarjeta con menú gana el gesto sin tocar su código, y una tarjeta
nueva lo tiene desde el primer día.

Lo que NO dispara el gesto, y cada exclusión está por algo:

  - Un botón, un enlace, un campo o un interruptor. Mantener el dedo en el botón
    de abrir una puerta tiene que abrir la puerta, no ofrecer «Eliminar».
  - Un arrastre. En el móvil, desplazar la página empieza con un dedo apoyado:
    sin cancelar por movimiento, cada scroll abriría un menú.
  - El plano en modo edición, donde mantener el dedo es como se mueven los
    iconos.

En el ordenador se engancha además al clic derecho, que es el mismo gesto de
toda la vida para lo mismo.
"""
import reflex as rx

# 500 ms: por debajo se confunde con un toque normal y por encima se siente
# roto. Es el mismo umbral que usan iOS y Android para su propio menú.
PULSACION_LARGA = """
(function(){
    if (window.__nxLongPress) return;
    window.__nxLongPress = true;

    const RETARDO = 500;
    const TOLERANCIA = 10;   // px de movimiento que se perdonan
    let temporizador = null, inicioX = 0, inicioY = 0, objetivo = null;

    function noEsGesto(el) {
        return !!el.closest(
            'button, a, input, textarea, select, [role="switch"], ' +
            '[role="button"], [data-nx-menu], .nx-plan-editing'
        );
    }

    function menuDe(el) {
        // El primer ancestro que contiene un menú: esa es la tarjeta.
        let n = el;
        while (n && n !== document.body) {
            const boton = n.querySelector && n.querySelector('[data-nx-menu]');
            if (boton) return boton;
            n = n.parentElement;
        }
        return null;
    }

    function cancelar() {
        if (temporizador) { clearTimeout(temporizador); temporizador = null; }
        objetivo = null;
    }

    document.addEventListener('pointerdown', function(e){
        if (e.button !== 0 && e.pointerType === 'mouse') return;
        if (noEsGesto(e.target)) return;
        const boton = menuDe(e.target);
        if (!boton) return;
        objetivo = boton; inicioX = e.clientX; inicioY = e.clientY;
        temporizador = setTimeout(function(){
            temporizador = null;
            if (!objetivo) return;
            // Un aviso al tacto de que el gesto ha entrado, para no dejar la
            // duda de si se ha mantenido bastante rato.
            if (navigator.vibrate) navigator.vibrate(12);
            objetivo.click();
            objetivo = null;
        }, RETARDO);
    }, {passive: true});

    document.addEventListener('pointermove', function(e){
        if (!temporizador) return;
        if (Math.abs(e.clientX - inicioX) > TOLERANCIA ||
            Math.abs(e.clientY - inicioY) > TOLERANCIA) cancelar();
    }, {passive: true});

    ['pointerup', 'pointercancel', 'scroll'].forEach(function(ev){
        document.addEventListener(ev, cancelar, {passive: true});
    });

    // Clic derecho en el ordenador: el mismo menú, y se le quita el del
    // navegador SOLO cuando hay uno nuestro que ofrecer.
    document.addEventListener('contextmenu', function(e){
        if (noEsGesto(e.target)) return;
        const boton = menuDe(e.target);
        if (!boton) return;
        e.preventDefault();
        boton.click();
    });
})();
"""


def pulsacion_larga() -> rx.Component:
    return rx.script(PULSACION_LARGA)
