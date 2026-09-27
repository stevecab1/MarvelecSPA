/*
 * MARVELEC SPA — Bandeja de salida de reportes (IndexedDB).
 * Si el trabajador no tiene señal en la obra, el reporte (con su foto) queda guardado
 * en el teléfono y se envía solo cuando vuelve la conexión.
 * Se usa tanto desde la página como desde el Service Worker (importScripts).
 */
(function (global) {
    'use strict';

    const DB_NOMBRE = 'marvelec';
    const STORE = 'outbox';

    function abrir() {
        return new Promise((resolve, reject) => {
            const req = indexedDB.open(DB_NOMBRE, 1);
            req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: 'uuid' });
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
        });
    }

    function transaccion(modo, operacion) {
        return abrir().then((db) => new Promise((resolve, reject) => {
            const tx = db.transaction(STORE, modo);
            const peticion = operacion(tx.objectStore(STORE));
            tx.oncomplete = () => { db.close(); resolve(peticion ? peticion.result : undefined); };
            tx.onerror = () => { db.close(); reject(tx.error); };
        }));
    }

    let enviando = null;

    const Outbox = {
        guardar: (item) => transaccion('readwrite', (s) => s.put(item)),
        borrar: (uuid) => transaccion('readwrite', (s) => s.delete(uuid)),
        contar: () => transaccion('readonly', (s) => s.count()),
        todos: () => transaccion('readonly', (s) => s.getAll())
            .then((lista) => (lista || []).sort((a, b) => a.creado.localeCompare(b.creado))),

        /**
         * Envía un reporte al servidor.
         * Devuelve {estado: 'enviado'|'rechazado'|'login'|'error'|'sin-red', data}
         */
        enviarUno: async function (item, csrf) {
            const datos = new FormData();
            Object.keys(item.campos).forEach((k) => datos.append(k, item.campos[k]));
            if (item.foto) datos.append('foto_llegada', item.foto, item.foto_nombre || 'foto.jpg');
            datos.append('uuid_cliente', item.uuid);
            datos.append('fecha_hora_cliente', item.creado);
            if (item.offline) datos.append('offline', '1');

            let resp;
            try {
                resp = await fetch(item.url, {
                    method: 'POST',
                    body: datos,
                    credentials: 'same-origin',
                    redirect: 'manual',
                    headers: { 'X-CSRFToken': csrf || item.csrf, 'X-Requested-With': 'fetch' },
                });
            } catch (e) {
                return { estado: 'sin-red' };
            }

            if (resp.type === 'opaqueredirect' || [401, 403, 409].includes(resp.status)) {
                return { estado: 'login' };
            }
            let data = {};
            try { data = await resp.json(); } catch (e) { /* respuesta no JSON */ }

            if (resp.ok) {
                await Outbox.borrar(item.uuid);
                return { estado: 'enviado', data };
            }
            if (resp.status === 400) {
                item.error = data.mensaje || 'El servidor rechazó el reporte.';
                await Outbox.guardar(item);
                return { estado: 'rechazado', data };
            }
            item.intentos = (item.intentos || 0) + 1;
            await Outbox.guardar(item);
            return { estado: 'error', data };
        },

        /** Envía todos los reportes pendientes (sin los rechazados). No corre dos veces en paralelo. */
        enviarTodos: function (csrf, usuarioId) {
            if (enviando) return enviando;
            enviando = (async () => {
                const resultado = { enviados: [], login: false, sinRed: false };
                const items = await Outbox.todos();
                for (const item of items) {
                    if (item.error) continue;
                    if (usuarioId && item.campos.usuario_id !== usuarioId) continue;
                    const r = await Outbox.enviarUno(item, csrf);
                    if (r.estado === 'enviado') resultado.enviados.push(r.data);
                    if (r.estado === 'login') { resultado.login = true; break; }
                    if (r.estado === 'sin-red') { resultado.sinRed = true; break; }
                }
                resultado.pendientes = await Outbox.contar();
                return resultado;
            })().finally(() => { enviando = null; });
            return enviando;
        },
    };

    global.MarvelecOutbox = Outbox;
})(typeof self !== 'undefined' ? self : window);
