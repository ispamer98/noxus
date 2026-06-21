self.addEventListener('push', function(event) {
    let data = { title: 'Noxus Alerta', body: 'Nueva notificación recibida' };
    
    if (event.data) {
        try {
            data = event.data.json();
        } catch (e) {
            data.body = event.data.text();
        }
    }

    const options = {
        body: data.body,
        icon: '/icon.png',
        badge: '/icon.png',
        vibrate: [200, 100, 200],
        // Se elimina la propiedad 'data' que contenía la URL para evitar que aparezca en el sistema
    };

    event.waitUntil(
        self.registration.showNotification(data.title, options)
    );
});

self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    // Solo abre la app, sin URLs específicas si no quieres rastreo
    event.waitUntil(
        clients.openWindow('/')
    );
});