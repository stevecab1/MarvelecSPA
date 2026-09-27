/* MARVELEC SPA — JS común (todas las páginas) */
(function () {
    'use strict';

    const body = document.body;
    const MV = (window.MV = window.MV || {});

    // ---------- Utilidades ----------
    MV.getCookie = function (name) {
        const v = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
        return v ? decodeURIComponent(v.pop()) : '';
    };

    MV.post = function (url, data) {
        const opciones = {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'X-CSRFToken': MV.getCookie('csrftoken'), 'X-Requested-With': 'fetch' },
        };
        if (data instanceof FormData) {
            opciones.body = data;
        } else if (data !== undefined) {
            opciones.headers['Content-Type'] = 'application/json';
            opciones.body = JSON.stringify(data);
        }
        return fetch(url, opciones);
    };

    MV.icono = function (nombre, clase) {
        return '<svg class="icon ' + (clase || '') + '" aria-hidden="true"><use href="#i-' + nombre + '"></use></svg>';
    };

    MV.escape = function (texto) {
        const div = document.createElement('div');
        div.textContent = texto == null ? '' : String(texto);
        return div.innerHTML;
    };

    // ---------- Toasts ----------
    const ICONOS_TOAST = { success: 'check-circle', error: 'alert', warning: 'alert', info: 'info' };
    const stack = document.getElementById('toasts');

    MV.toast = function (mensaje, tipo, duracion) {
        if (!stack) return;
        tipo = tipo || 'info';
        const el = document.createElement('div');
        el.className = 'toast toast-' + tipo;
        el.setAttribute('role', tipo === 'error' ? 'alert' : 'status');
        el.innerHTML = MV.icono(ICONOS_TOAST[tipo] || 'info') + '<span></span>';
        el.querySelector('span').textContent = mensaje;
        stack.appendChild(el);
        const cerrar = () => {
            el.classList.add('is-leaving');
            setTimeout(() => el.remove(), 220);
        };
        el.addEventListener('click', cerrar);
        setTimeout(cerrar, duracion || (tipo === 'error' ? 7000 : 4500));
    };

    // Toast pendiente de una página anterior (p. ej. tras enviar un reporte con JS).
    MV.toastSiguientePagina = function (mensaje, tipo) {
        try { sessionStorage.setItem('mv-toast', JSON.stringify({ mensaje, tipo })); } catch (e) { /* sin storage */ }
    };

    document.querySelectorAll('template[data-toast]').forEach((t) => {
        MV.toast(t.content.textContent.trim(), t.dataset.toast || 'info');
        t.remove();
    });
    try {
        const pendiente = sessionStorage.getItem('mv-toast');
        if (pendiente) {
            sessionStorage.removeItem('mv-toast');
            const t = JSON.parse(pendiente);
            MV.toast(t.mensaje, t.tipo);
        }
    } catch (e) { /* sin storage */ }

    // ---------- Estado de conexión ----------
    function actualizarRed() { body.classList.toggle('is-offline', !navigator.onLine); }
    window.addEventListener('online', actualizarRed);
    window.addEventListener('offline', actualizarRed);
    actualizarRed();

    // ---------- Service Worker ----------
    MV.swListo = null;
    if ('serviceWorker' in navigator && body.dataset.swUrl) {
        MV.swListo = navigator.serviceWorker.register(body.dataset.swUrl, { scope: '/' })
            .then(() => navigator.serviceWorker.ready)
            .then((reg) => {
                const urls = (body.dataset.urlPrecache || '').trim().split(/\s+/).filter(Boolean);
                if (urls.length && reg.active) reg.active.postMessage({ type: 'precache', urls });
                if (body.dataset.limpiarCache && reg.active) reg.active.postMessage({ type: 'limpiar' });
                return reg;
            })
            .catch((err) => { console.warn('SW no se pudo registrar:', err); return null; });

        navigator.serviceWorker.addEventListener('message', (event) => {
            const data = event.data || {};
            if (data.type === 'push-recibido') MV.actualizarNotificaciones();
            if (data.type === 'outbox-enviado' && MV.onOutboxEnviado) MV.onOutboxEnviado(data);
        });
    }

    // ---------- Visor de fotos ----------
    const lightbox = document.getElementById('lightbox');
    MV.abrirFoto = function (src, texto) {
        if (!lightbox) return;
        document.getElementById('lightbox-img').src = src;
        document.getElementById('lightbox-download').href = src;
        document.getElementById('lightbox-text').textContent = texto || '';
        lightbox.classList.add('is-open');
    };
    function cerrarFoto() { if (lightbox) lightbox.classList.remove('is-open'); }
    document.addEventListener('click', (e) => {
        const disparador = e.target.closest('[data-lightbox]');
        if (disparador) {
            e.preventDefault();
            e.stopPropagation();
            MV.abrirFoto(disparador.dataset.lightbox, disparador.dataset.caption);
            return;
        }
        if (lightbox && (e.target === lightbox || e.target.closest('[data-lightbox-close]'))) cerrarFoto();
    });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') cerrarFoto(); });

    // ---------- Filas clicables ----------
    document.addEventListener('click', (e) => {
        const fila = e.target.closest('[data-href]');
        if (!fila || e.target.closest('a, button, input, label, select, textarea, [data-lightbox]')) return;
        if (e.ctrlKey || e.metaKey) window.open(fila.dataset.href, '_blank');
        else window.location.href = fila.dataset.href;
    });

    // ---------- Menú lateral (escritorio en pantallas chicas) ----------
    const sidebar = document.getElementById('sidebar');
    const backdrop = document.querySelector('[data-sidebar-close]');
    function menu(abrir) {
        if (!sidebar) return;
        sidebar.classList.toggle('is-open', abrir);
        if (backdrop) backdrop.hidden = !abrir;
    }
    document.querySelectorAll('[data-sidebar-open]').forEach((b) => b.addEventListener('click', () => menu(true)));
    if (backdrop) backdrop.addEventListener('click', () => menu(false));

    if (!body.dataset.auth) return;

    // ---------- Centro de notificaciones ----------
    const ICONOS_NOTIF = {
        nuevo_reporte: 'file', reporte_corregido: 'edit', reporte_aprobado: 'check-circle',
        reporte_observado: 'alert', resumen_diario: 'chart',
    };

    function pintarContadores(n) {
        document.querySelectorAll('[data-notif-count]').forEach((el) => {
            el.textContent = n > 99 ? '99+' : n;
            el.hidden = !n;
        });
        if ('setAppBadge' in navigator) {
            (n ? navigator.setAppBadge(n) : navigator.clearAppBadge()).catch(() => {});
        }
    }

    MV.renderNotificacion = function (n) {
        return '<button type="button" class="notif ' + (n.leida ? '' : 'is-unread') + '" data-notif-leer="' +
            MV.escape(n.url_leer) + '">' +
            '<span class="notif-icon t-' + n.tipo + '">' + MV.icono(ICONOS_NOTIF[n.tipo] || 'bell') + '</span>' +
            '<span class="notif-body"><b>' + MV.escape(n.titulo) + '</b><p>' + MV.escape(n.cuerpo) + '</p>' +
            '<time>hace ' + MV.escape(n.hace) + '</time></span></button>';
    };

    const lista = document.querySelector('[data-notif-list]');
    MV.actualizarNotificaciones = function () {
        if (!body.dataset.urlEstadoNotif) return Promise.resolve();
        return fetch(body.dataset.urlEstadoNotif, { credentials: 'same-origin' })
            .then((r) => (r.ok ? r.json() : null))
            .then((data) => {
                if (!data) return;
                pintarContadores(data.no_leidas);
                if (lista) {
                    lista.innerHTML = data.ultimas.length
                        ? data.ultimas.map(MV.renderNotificacion).join('')
                        : '<div class="empty small">' + MV.icono('bell') + 'No tienes notificaciones.</div>';
                }
                document.querySelectorAll('[data-pendientes-count]').forEach((el) => {
                    if (data.pendientes_revision !== undefined) {
                        el.textContent = data.pendientes_revision;
                        el.hidden = !data.pendientes_revision;
                    }
                });
            })
            .catch(() => {});
    };

    document.addEventListener('click', (e) => {
        const item = e.target.closest('[data-notif-leer]');
        if (!item) return;
        e.preventDefault();
        item.classList.remove('is-unread');
        MV.post(item.dataset.notifLeer)
            .then((r) => r.json())
            .then((data) => { window.location.href = data.url || window.location.href; })
            .catch(() => {});
    });

    document.querySelectorAll('[data-leer-todas]').forEach((b) => b.addEventListener('click', () => {
        MV.post(body.dataset.urlLeerTodas).then(() => {
            document.querySelectorAll('.notif.is-unread').forEach((el) => el.classList.remove('is-unread'));
            pintarContadores(0);
        });
    }));

    const bell = document.querySelector('[data-bell]');
    const panel = document.querySelector('[data-bell-panel]');
    if (bell && panel) {
        bell.addEventListener('click', (e) => {
            e.stopPropagation();
            panel.hidden = !panel.hidden;
            bell.setAttribute('aria-expanded', String(!panel.hidden));
            if (!panel.hidden) MV.actualizarNotificaciones();
        });
        document.addEventListener('click', (e) => {
            if (!panel.hidden && !e.target.closest('.bell')) panel.hidden = true;
        });
    }

    setInterval(() => { if (!document.hidden && navigator.onLine) MV.actualizarNotificaciones(); }, 60000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) MV.actualizarNotificaciones(); });

    // ---------- Notificaciones push ----------
    const pushSoportado = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
    const esIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
    const instalada = window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;

    function urlBase64ToUint8Array(base64String) {
        const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
        const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
        const raw = atob(base64);
        return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
    }

    function enviarSuscripcion(sub) {
        return MV.post(body.dataset.urlSuscribir, sub.toJSON());
    }

    MV.estadoPush = async function () {
        if (!pushSoportado) return esIOS && !instalada ? 'ios-instalar' : 'no-soportado';
        if (Notification.permission === 'denied') return 'bloqueado';
        const reg = await MV.swListo;
        if (!reg) return 'no-soportado';
        const sub = await reg.pushManager.getSubscription();
        return sub && Notification.permission === 'granted' ? 'activo' : 'inactivo';
    };

    MV.activarPush = async function () {
        const permiso = await Notification.requestPermission();
        if (permiso !== 'granted') {
            MV.toast('No se dio permiso para notificaciones. Puedes activarlo en la configuración del navegador.', 'warning');
            return false;
        }
        const reg = await MV.swListo;
        let sub = await reg.pushManager.getSubscription();
        if (!sub) {
            const resp = await fetch(body.dataset.urlVapid, { credentials: 'same-origin' });
            const data = await resp.json();
            sub = await reg.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: urlBase64ToUint8Array(data.public_key),
            });
        }
        await enviarSuscripcion(sub);
        MV.toast('Notificaciones activadas en este dispositivo.', 'success');
        return true;
    };

    MV.desactivarPush = async function () {
        const reg = await MV.swListo;
        const sub = reg && (await reg.pushManager.getSubscription());
        if (sub) {
            await MV.post(body.dataset.urlDesuscribir, { endpoint: sub.endpoint });
            await sub.unsubscribe();
        }
        MV.toast('Notificaciones desactivadas en este dispositivo.', 'info');
    };

    const TEXTOS_PUSH = {
        activo: ['bell', 'Notificaciones activas'],
        inactivo: ['bell-off', 'Activar notificaciones'],
        bloqueado: ['bell-off', 'Notificaciones bloqueadas'],
    };

    async function pintarBotonesPush() {
        const estado = await MV.estadoPush();
        document.querySelectorAll('[data-push-toggle]').forEach((b) => {
            const texto = TEXTOS_PUSH[estado];
            b.hidden = !texto;
            if (!texto) return;
            b.dataset.estado = estado;
            b.querySelector('use').setAttribute('href', '#i-' + texto[0]);
            b.querySelector('span').textContent = texto[1];
        });
        document.querySelectorAll('[data-push-banner]').forEach((el) => {
            el.hidden = estado !== el.dataset.pushBanner;
        });
        return estado;
    }

    document.addEventListener('click', async (e) => {
        const b = e.target.closest('[data-push-toggle], [data-push-activar]');
        if (!b) return;
        b.classList.add('is-loading');
        try {
            const estado = await MV.estadoPush();
            if (estado === 'bloqueado') {
                MV.toast('Las notificaciones están bloqueadas. Actívalas desde el candado junto a la dirección del sitio.', 'warning', 9000);
            } else if (estado === 'activo' && b.matches('[data-push-toggle]')) {
                await MV.desactivarPush();
            } else {
                await MV.activarPush();
            }
        } catch (err) {
            console.warn(err);
            MV.toast('No se pudieron activar las notificaciones en este dispositivo.', 'error');
        }
        b.classList.remove('is-loading');
        pintarBotonesPush();
    });

    // Si ya estaba activo, re-sincroniza la suscripción con el servidor una vez por sesión.
    if (MV.swListo) {
        pintarBotonesPush().then(async (estado) => {
            if (estado !== 'activo') return;
            try {
                if (sessionStorage.getItem('mv-push-sync')) return;
                sessionStorage.setItem('mv-push-sync', '1');
            } catch (e) { /* sin storage */ }
            const reg = await MV.swListo;
            const sub = await reg.pushManager.getSubscription();
            if (sub) enviarSuscripcion(sub);
        });
    }
})();
