{% load static %}/* Service Worker de MARVELEC SPA — servido desde /sw.js para controlar todo el sitio. */
const VERSION = 'marvelec-{{ version }}';
const CACHE_ESTATICOS = VERSION + '-estaticos';
const CACHE_PAGINAS = 'marvelec-paginas';

const ESTATICOS = [
    '{% static "marvelec_app/css/style.css" %}',
    '{% static "marvelec_app/js/app.js" %}',
    '{% static "marvelec_app/js/outbox.js" %}',
    '{% static "marvelec_app/js/trabajador.js" %}',
    '{% static "marvelec_app/icons/icon-96x96.png" %}',
    '{% static "marvelec_app/icons/icon-192x192.png" %}',
];

// Rutas que nunca se sirven desde caché.
const SOLO_RED = ['/admin/', '/api/', '/notificaciones/', '/reportes/exportar', '/tareas/', '/salir/', '/ingresar/'];

importScripts('{% static "marvelec_app/js/outbox.js" %}');

const PAGINA_OFFLINE = '<!doctype html><html lang="es"><meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width,initial-scale=1"><title>Sin conexión - MARVELEC</title>' +
    '<body style="margin:0;font-family:system-ui,sans-serif;display:grid;place-items:center;min-height:100vh;' +
    'background:#3a288f;color:#fff;text-align:center;padding:24px"><div>' +
    '<h1 style="font-size:1.3rem">Sin conexión</h1>' +
    '<p style="opacity:.85">Esta página aún no está disponible sin señal.<br>Vuelve a intentarlo cuando tengas conexión.</p>' +
    '<p><a href="/panel/trabajador/" style="color:#f5b700;font-weight:700">Ir al inicio</a></p></div></body></html>';

self.addEventListener('install', (event) => {
    event.waitUntil(caches.open(CACHE_ESTATICOS).then((c) => c.addAll(ESTATICOS)).catch(() => {}));
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys()
            .then((keys) => Promise.all(
                keys.filter((k) => k !== CACHE_ESTATICOS && k !== CACHE_PAGINAS).map((k) => caches.delete(k))
            ))
            .then(() => self.clients.claim())
    );
});

function guardable(resp) {
    return resp && resp.ok && !resp.redirected && resp.type === 'basic';
}

async function guardarPagina(url) {
    try {
        const resp = await fetch(url, { credentials: 'same-origin' });
        if (guardable(resp)) await (await caches.open(CACHE_PAGINAS)).put(url, resp);
    } catch (e) { /* sin red */ }
}

self.addEventListener('fetch', (event) => {
    const req = event.request;
    if (req.method !== 'GET') return;
    const url = new URL(req.url);
    if (url.origin !== self.location.origin) return;
    if (SOLO_RED.some((p) => url.pathname.startsWith(p))) return;

    // Estáticos: con hash en el nombre (producción) caché primero; si no, red primero.
    if (url.pathname.startsWith('/static/')) {
        const conHash = /\.[0-9a-f]{12}\./.test(url.pathname);
        event.respondWith(
            caches.match(req).then((cacheado) => {
                if (cacheado && conHash) return cacheado;
                return fetch(req)
                    .then((resp) => {
                        if (guardable(resp)) {
                            const copia = resp.clone();
                            caches.open(CACHE_ESTATICOS).then((c) => c.put(req, copia));
                        }
                        return resp;
                    })
                    .catch(() => cacheado || Response.error());
            })
        );
        return;
    }

    // Páginas: red primero, caché si no hay señal.
    if (req.mode === 'navigate') {
        const clave = url.pathname + url.search;
        event.respondWith(
            fetch(req)
                .then((resp) => {
                    if (guardable(resp)) {
                        const copia = resp.clone();
                        caches.open(CACHE_PAGINAS).then((c) => c.put(clave, copia));
                    }
                    return resp;
                })
                .catch(async () => {
                    const cache = await caches.open(CACHE_PAGINAS);
                    return (await cache.match(clave)) ||
                        (await cache.match(url.pathname)) ||
                        new Response(PAGINA_OFFLINE, { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
                })
        );
    }
});

self.addEventListener('message', (event) => {
    const data = event.data || {};
    if (data.type === 'precache' && Array.isArray(data.urls)) {
        event.waitUntil(Promise.all(data.urls.map(guardarPagina)));
    }
    if (data.type === 'limpiar') {
        // Al cerrar sesión: no dejar páginas privadas guardadas en el dispositivo.
        event.waitUntil(caches.delete(CACHE_PAGINAS));
    }
});

// --- Reenvío de reportes guardados sin señal (Background Sync) ---
async function avisarClientes(mensaje) {
    const lista = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    lista.forEach((c) => c.postMessage(mensaje));
}

self.addEventListener('sync', (event) => {
    if (event.tag !== 'enviar-reportes') return;
    event.waitUntil((async () => {
        const r = await self.MarvelecOutbox.enviarTodos();
        if (r.enviados.length) {
            await avisarClientes({ type: 'outbox-enviado', enviados: r.enviados.length });
            await self.registration.showNotification('Reportes enviados', {
                body: r.enviados.length === 1
                    ? 'Tu reporte guardado sin señal ya fue enviado.'
                    : r.enviados.length + ' reportes guardados sin señal ya fueron enviados.',
                icon: '{% static "marvelec_app/icons/icon-192x192.png" %}',
                badge: '{% static "marvelec_app/icons/icon-96x96.png" %}',
                tag: 'outbox',
            });
        }
        // Si quedaron pendientes por falta de red, fallar hace que el navegador reintente más tarde.
        if (r.sinRed) throw new Error('Sin red: reintentar');
    })());
});

// --- Notificaciones push ---
self.addEventListener('push', (event) => {
    let data = { title: 'MARVELEC SPA', body: 'Tienes una notificación nueva.' };
    try {
        data = event.data.json();
    } catch (e) {
        if (event.data) data.body = event.data.text();
    }

    const tareas = [
        self.registration.showNotification(data.title || 'MARVELEC SPA', {
            body: data.body,
            icon: '{% static "marvelec_app/icons/icon-192x192.png" %}',
            badge: '{% static "marvelec_app/icons/icon-96x96.png" %}',
            tag: data.tag || 'marvelec',
            renotify: true,
            data: { url: data.url || '/panel/' },
            vibrate: [200, 100, 200],
        }),
        avisarClientes({ type: 'push-recibido' }),
    ];
    if (typeof data.no_leidas === 'number' && 'setAppBadge' in self.navigator) {
        tareas.push(self.navigator.setAppBadge(data.no_leidas).catch(() => {}));
    }
    event.waitUntil(Promise.all(tareas));
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const ruta = (event.notification.data && event.notification.data.url) || '/panel/';
    const destino = new URL(ruta, self.location.origin).href;
    event.waitUntil(
        self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((ventanas) => {
            for (const ventana of ventanas) {
                if (ventana.url.startsWith(self.location.origin) && 'focus' in ventana) {
                    return ventana.focus().then((v) => (v && 'navigate' in v ? v.navigate(destino) : v));
                }
            }
            return self.clients.openWindow(destino);
        })
    );
});
