// Service Worker de MARVELEC SPA
const CACHE_NAME = 'marvelec-v1';
const ASSETS_TO_CACHE = [
    '/static/marvelec_app/css/style.css',
    '/static/marvelec_app/icons/icon-192x192.png',
];

// Instalar: cachear archivos estáticos esenciales
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => cache.addAll(ASSETS_TO_CACHE))
    );
    self.skipWaiting();
});

// Activar: limpiar caches viejos
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
        )
    );
    self.clients.claim();
});

// Fetch: network-first (siempre intenta la red, usa cache solo si falla)
self.addEventListener('fetch', event => {
    // No cachear peticiones POST ni del admin
    if (event.request.method !== 'GET' || event.request.url.includes('/admin/')) return;

    event.respondWith(
        fetch(event.request)
            .then(response => {
                // Guardar copia en cache para offline
                if (response.ok) {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
                }
                return response;
            })
            .catch(() => caches.match(event.request))
    );
});

// Notificaciones Push: mostrar notificación cuando llega un mensaje del servidor
self.addEventListener('push', event => {
    let data = { title: 'MARVELEC SPA', body: 'Nuevo reporte recibido.' };
    try {
        data = event.data.json();
    } catch (e) {
        data.body = event.data ? event.data.text() : data.body;
    }

    event.waitUntil(
        self.registration.showNotification(data.title || 'MARVELEC SPA', {
            body: data.body,
            icon: '/static/marvelec_app/icons/icon-192x192.png',
            badge: '/static/marvelec_app/icons/icon-96x96.png',
            tag: data.tag || 'reporte',
            data: { url: data.url || '/panel/' },
            vibrate: [200, 100, 200],
        })
    );
});

// Al tocar la notificación: abrir la URL correspondiente
self.addEventListener('notificationclick', event => {
    event.notification.close();
    const url = event.notification.data.url || '/panel/';
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(windowClients => {
            // Si ya hay una ventana abierta, enfocarla
            for (const client of windowClients) {
                if (client.url.includes(self.location.origin) && 'focus' in client) {
                    client.navigate(url);
                    return client.focus();
                }
            }
            // Si no, abrir una nueva
            return clients.openWindow(url);
        })
    );
});
