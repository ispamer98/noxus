// Service worker de Noxus: solo notificaciones. No cachea nada a propósito —
// el panel refleja el estado de una casa de verdad y servir una versión
// guardada de hace un rato sería peor que no abrir.
//
// El payload lo construye domains/notifications/push.py. Los campos que se
// leen aquí son: title, body, icon, badge, tag, silencioso y acciones.
//
// LOS BOTONES NO EXISTEN EN iOS. WebKit no admite `actions` en
// showNotification, y no los ignora: RECHAZA la notificación entera. El
// resultado es el peor posible — iOS enseña entonces su propia notificación
// genérica, sin título ni cuerpo, y al pulsarla solo abre la aplicación. Se
// comprobó el 2026-08-17 en un iPhone con la alarma de esta casa: el mismo
// aviso llegaba en blanco con `acciones` y con su texto entero sin ellas.
// Los dos móviles de la casa son iPhone (endpoint web.push.apple.com), así que
// esto no es un caso raro: es el caso normal.
//
// De ahí las dos defensas de abajo. Los botones solo se piden donde de verdad
// se pueden pintar (SOPORTA_BOTONES), y mostrar() reintenta con lo mínimo si
// algo se rechaza. La regla es que un aviso puede salir sin adornos, pero NUNCA
// sin texto: un aviso mudo de una alarma es peor que no tener aviso, porque
// parece que el sistema ha avisado.

// Activarse cuanto antes. Sin esto, el service worker nuevo se queda "en
// espera" hasta que se cierran todas las pestañas de Noxus, y en un móvil que
// tiene la aplicación siempre abierta eso puede ser días: los avisos seguirían
// llegando con el comportamiento viejo sin que se entienda por qué.
self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(self.clients.claim());
});

// ¿Este navegador pinta botones en las notificaciones? Se le pregunta a él en
// vez de adivinarlo por el sistema operativo: maxActions es justo el número de
// botones que va a enseñar, y donde no existe el campo (WebKit) sale undefined,
// que no es > 0. Así un iOS que algún día los admita los tendrá sin tocar nada.
const SOPORTA_BOTONES = (
    typeof Notification !== 'undefined' && Notification.maxActions > 0
);

// Muestra el aviso, y si no se puede tal cual, lo muestra como se pueda.
//
// Un showNotification rechazado deja el push sin notificación, y entonces el
// sistema enseña la suya vacía (iOS) o nada (Android). Por eso hay segundo
// intento con lo imprescindible: nada de botones, ni renotify, ni vibración —
// solo título y texto, que es lo único que de verdad importa.
async function mostrar(titulo, opciones) {
    try {
        await self.registration.showNotification(titulo, opciones);
        return;
    } catch (e) {
        try {
            await self.registration.showNotification(titulo, {
                body: opciones.body,
                icon: opciones.icon,
                badge: opciones.badge,
                tag: opciones.tag,
                data: opciones.data,
            });
        } catch (e2) { /* no hay tercera opción: el sistema no quiere avisar */ }
    }
}

self.addEventListener('push', function(event) {
    let data = { title: 'Noxus', body: 'Nueva notificación recibida' };

    if (event.data) {
        try {
            data = event.data.json();
        } catch (e) {
            data.body = event.data.text();
        }
    }

    // Agrupar por tag: dos avisos del mismo elemento ocupan UNA sola
    // notificación, la segunda sustituye a la primera. Es lo que evita que una
    // puerta que se abre ocho veces en dos minutos deje ocho avisos apilados.
    // Quién comparte tag lo decide push.py, no esto: sin tag manda uno único
    // por envío, así que aquí siempre llega algo con lo que agrupar. El valor
    // de reserva es solo para un payload que no venga de push.py.
    const tag = data.tag || 'noxus';

    // Lo informativo (un equipo que vuelve a estar en línea) llega sin sonido
    // ni vibración. Lo de alarma nunca es silencioso — lo decide quien manda el
    // aviso.
    const silencioso = data.silencioso === true;

    const acciones = Array.isArray(data.acciones) ? data.acciones : [];
    // Donde no hay botones, el aviso tiene que DECIR qué hacer en su lugar. Sin
    // esto, un aviso de alarma en un iPhone se quedaría sin ninguna forma de
    // confirmarse y sin explicar por qué se repite tres veces.
    const cuerpo = (acciones.length && !SOPORTA_BOTONES)
        ? `${data.body} · Abre Noxus para confirmar o silenciar.`
        : data.body;

    const options = {
        body: cuerpo,
        icon: data.icon || '/icono-192.png',
        badge: data.badge || '/icono-192.png',
        tag: tag,
        // renotify hace que la SUSTITUCIÓN vuelva a sonar: sin esto, agrupar
        // tendría un efecto feo — la segunda apertura de la puerta actualizaría
        // el texto en silencio y nadie se enteraría. Va desactivado en los
        // silenciosos porque el navegador rechaza la notificación entera si se
        // piden las dos cosas a la vez.
        renotify: !silencioso,
        silent: silencioso,
        vibrate: silencioso ? [] : [200, 100, 200],
        timestamp: Date.now(),
        // Botones del propio aviso. Los manda push.py, y solo se piden si este
        // navegador los pinta — ver SOPORTA_BOTONES y la cabecera del fichero.
        actions: SOPORTA_BOTONES ? acciones : [],
        // El tag viaja también aquí dentro porque en notificationclick hay que
        // decirle al servidor DE QUÉ aviso se está hablando, y event.notification
        // solo conserva lo que se guardó al mostrarla.
        data: { tag: tag },
    };

    event.waitUntil(mostrar(data.title, options));
});

// Avisar de que algo NO ha salido. Es la pieza que evita el fallo mudo: si la
// sesión de Cloudflare Zero Trust ha caducado, la petición no llega al panel
// —devuelve una redirección al login, o un 403— y sin esto el botón «Visto»
// se quedaría en nada y la alarma seguiría repitiéndose sin que se entienda
// por qué. Preferimos molestar con un aviso feo a fallar en silencio.
async function avisarDelFallo(texto) {
    await mostrar('No se pudo hacer', {
        body: texto,
        icon: '/icono-192.png',
        badge: '/icono-192.png',
        tag: 'noxus:fallo',
        renotify: true,
        vibrate: [100, 50, 100],
    });
}

async function mandarAccion(accion, clave) {
    let respuesta;
    try {
        respuesta = await fetch('/api/aviso', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            // Sin las cookies el servidor no sabe qué dispositivo es, y sin
            // saberlo rechaza: es la misma sesión firmada del panel.
            credentials: 'include',
            body: JSON.stringify({ accion: accion, clave: clave || '' }),
        });
    } catch (e) {
        await avisarDelFallo(
            'No hay conexión con la casa. Abre Noxus para hacerlo desde la app.');
        return;
    }

    // Zero Trust no devuelve un error limpio: contesta con la página de su
    // login. Se detecta porque no es JSON o porque el código no es 2xx.
    let datos = null;
    try { datos = await respuesta.json(); } catch (e) { datos = null; }

    if (respuesta.status === 401 || respuesta.status === 403 || datos === null) {
        await avisarDelFallo(
            'Tu sesión ha caducado. Abre Noxus, entra, y vuelve a intentarlo.');
        return;
    }
    if (!respuesta.ok || datos.ok === false) {
        await avisarDelFallo(datos.mensaje || 'El panel no ha podido hacerlo.');
        return;
    }
    // Salió bien: se sustituye el aviso por la confirmación, en silencio para
    // no volver a sonar por algo que la persona acaba de pulsar.
    await mostrar('Noxus', {
        body: datos.mensaje || 'Hecho.',
        icon: '/icono-192.png',
        badge: '/icono-192.png',
        tag: clave || 'noxus:hecho',
        silent: true,
    });
}

self.addEventListener('notificationclick', function(event) {
    const accion = event.action;
    const clave = (event.notification.data && event.notification.data.tag) || '';
    event.notification.close();

    if (accion === 'confirmar' || accion === 'silenciar') {
        event.waitUntil(mandarAccion(accion, clave));
        return;
    }
    if (accion === 'camara') {
        event.waitUntil(clients.openWindow('/panel?vista=video_wall'));
        return;
    }

    // Enfocar la pestaña que ya está abierta en vez de abrir otra. Antes esto
    // hacía openWindow siempre, así que cada aviso pulsado dejaba una copia
    // más del panel: cuatro avisos, cuatro pestañas, cuatro conexiones al
    // backend y cuatro sesiones sincronizando lo mismo.
    //
    // includeUncontrolled es imprescindible: las pestañas que se cargaron
    // ANTES de que este service worker tomara el control no le pertenecen
    // todavía, y sin esto no las vería — justo las que hay abiertas ahora
    // mismo, que son las que hay que enfocar.
    event.waitUntil((async () => {
        const ventanas = await clients.matchAll({
            type: 'window',
            includeUncontrolled: true,
        });

        for (const ventana of ventanas) {
            // Mismo origen: no se enfoca una pestaña de otra web que el
            // navegador nos pueda listar.
            if (new URL(ventana.url).origin !== self.location.origin) continue;
            if ('focus' in ventana) return ventana.focus();
        }

        // No había ninguna abierta: entonces sí, se abre. Sin parámetros de
        // seguimiento — el aviso no lleva a ninguna vista concreta, solo al
        // panel.
        if (clients.openWindow) return clients.openWindow('/panel');
    })());
});
