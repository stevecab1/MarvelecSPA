/* MARVELEC SPA — App del trabajador (celular) */
(function () {
    'use strict';

    const MV = window.MV;
    const Outbox = window.MarvelecOutbox;
    const hayIndexedDB = 'indexedDB' in window && Outbox;
    const usuarioId = document.body.dataset.userId;

    // =========================================================
    // Bandeja de salida: reportes guardados sin señal
    // =========================================================
    function fechaCorta(iso) {
        const d = new Date(iso);
        return d.toLocaleDateString('es-CL', { day: '2-digit', month: '2-digit' }) + ' ' +
            d.toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' });
    }

    function tarjetaPendiente(item) {
        const r = item.resumen || {};
        const div = document.createElement('div');
        div.className = 'r-card is-pending';
        const thumb = item.foto
            ? '<img class="r-thumb" alt="" src="' + URL.createObjectURL(item.foto) + '">'
            : '<div class="r-thumb">' + MV.icono('image') + '</div>';
        div.innerHTML = thumb +
            '<div class="r-body">' +
            '<div class="r-top"><span class="r-title">' + MV.escape(r.obra) + ' / ' + MV.escape(r.subetapa) + '</span>' +
            (item.error
                ? '<span class="badge badge-observado">Rechazado</span>'
                : '<span class="badge badge-offline">' + MV.icono('cloud-off', 'icon-sm') + ' Por enviar</span>') +
            '</div>' +
            '<div class="r-meta"><span>' + MV.icono('clock', 'icon-sm') + ' ' + fechaCorta(item.creado) + '</span>' +
            '<span class="pts">' + (r.total || 0) + ' pts</span></div>' +
            (item.error
                ? '<div class="r-note">' + MV.escape(item.error) + '</div>' +
                  '<div><button type="button" class="btn btn-secondary btn-sm mt-1" data-outbox-descartar="' + item.uuid + '">' +
                  MV.icono('trash', 'icon-sm') + ' Descartar</button></div>'
                : '') +
            '</div>';
        return div;
    }

    async function pintarBandeja() {
        if (!hayIndexedDB) return;
        let items = [];
        try { items = await Outbox.todos(); } catch (e) { return; }
        items = items.filter((i) => i.campos.usuario_id === usuarioId);
        const porEnviar = items.filter((i) => !i.error).length;

        document.querySelectorAll('[data-outbox-count]').forEach((el) => {
            el.textContent = items.length;
            el.hidden = !items.length;
        });
        document.querySelectorAll('[data-outbox-banner]').forEach((el) => {
            el.hidden = !porEnviar;
            const n = el.querySelector('[data-outbox-n]');
            if (n) n.textContent = porEnviar === 1 ? '1 reporte' : porEnviar + ' reportes';
        });
        document.querySelectorAll('[data-outbox-lista]').forEach((cont) => {
            cont.innerHTML = '';
            items.slice().reverse().forEach((item) => cont.appendChild(tarjetaPendiente(item)));
            cont.hidden = !items.length;
        });
    }

    async function enviarPendientes(manual) {
        if (!hayIndexedDB) return;
        if (!navigator.onLine) {
            if (manual) MV.toast('Sigues sin conexión. Se enviará apenas vuelva la señal.', 'warning');
            return;
        }
        let r;
        try { r = await Outbox.enviarTodos(MV.getCookie('csrftoken'), usuarioId); } catch (e) { return; }
        if (r.enviados.length) {
            const msg = r.enviados.length === 1 ? 'Se envió 1 reporte que estaba pendiente.'
                : 'Se enviaron ' + r.enviados.length + ' reportes que estaban pendientes.';
            // En el formulario no recargamos para no borrar lo que el trabajador está escribiendo.
            if (document.querySelector('[data-reporte-form]')) {
                MV.toast(msg, 'success');
            } else {
                MV.toastSiguientePagina(msg, 'success');
                window.location.reload();
                return;
            }
        }
        if (r.login) MV.toast('Tu sesión expiró. Vuelve a ingresar para enviar los reportes pendientes.', 'warning', 9000);
        else if (manual && r.sinRed) MV.toast('No se pudo conectar. Se reintentará automáticamente.', 'warning');
        pintarBandeja();
    }

    MV.onOutboxEnviado = function () {
        pintarBandeja();
    };

    document.addEventListener('click', async (e) => {
        const enviar = e.target.closest('[data-outbox-enviar]');
        if (enviar) {
            enviar.classList.add('is-loading');
            await enviarPendientes(true);
            enviar.classList.remove('is-loading');
            return;
        }
        const descartar = e.target.closest('[data-outbox-descartar]');
        if (descartar && confirm('¿Descartar este reporte? No se enviará.')) {
            await Outbox.borrar(descartar.dataset.outboxDescartar);
            pintarBandeja();
        }
    });

    window.addEventListener('online', () => enviarPendientes(false));
    pintarBandeja().then(() => enviarPendientes(false));

    // =========================================================
    // Formulario de reporte
    // =========================================================
    const form = document.querySelector('[data-reporte-form]');
    if (!form) return;

    // --- Subetapas según la obra (datos embebidos: funciona sin señal) ---
    const obraSel = form.querySelector('[name=obra]');
    const subSel = form.querySelector('[name=subetapa]');
    const datosSub = document.getElementById('subetapas-data');
    const subetapas = datosSub ? JSON.parse(datosSub.textContent) : {};

    function pintarSubetapas() {
        if (!obraSel || !subSel) return;
        const actual = subSel.value;
        const lista = subetapas[obraSel.value] || [];
        subSel.innerHTML = '<option value="">' + (obraSel.value ? 'Selecciona la subetapa' : 'Primero elige la obra') + '</option>';
        lista.forEach((s) => {
            const op = document.createElement('option');
            op.value = s.id;
            op.textContent = s.nombre;
            if (String(s.id) === actual) op.selected = true;
            subSel.appendChild(op);
        });
        subSel.disabled = !lista.length;
    }
    if (obraSel && subSel) {
        obraSel.addEventListener('change', pintarSubetapas);
        pintarSubetapas();
    }

    // --- Puntos: botones − / + y total en vivo ---
    const inputsPuntos = Array.from(form.querySelectorAll('.stepper-input'));
    const totalEl = form.querySelector('[data-total]');

    function valor(input) { return Math.max(0, parseInt(input.value, 10) || 0); }
    function pintarTotal() {
        if (totalEl) totalEl.textContent = inputsPuntos.reduce((s, i) => s + valor(i), 0);
    }
    form.addEventListener('click', (e) => {
        const b = e.target.closest('[data-step]');
        if (!b) return;
        const input = b.closest('.stepper').querySelector('input');
        input.value = Math.min(9999, Math.max(0, valor(input) + parseInt(b.dataset.step, 10)));
        if (navigator.vibrate) navigator.vibrate(8);
        pintarTotal();
    });
    inputsPuntos.forEach((i) => {
        i.addEventListener('input', pintarTotal);
        i.addEventListener('focus', () => i.select());
    });
    pintarTotal();

    // --- Foto: vista previa + compresión (sube rápido con poca señal) ---
    const fotoInput = form.querySelector('[name=foto]');
    const picker = form.querySelector('.foto-picker');
    let fotoLista = null; // Blob comprimido

    async function comprimir(archivo) {
        const MAX = 1600;
        try {
            let fuente;
            if ('createImageBitmap' in window) {
                fuente = await createImageBitmap(archivo);
            } else {
                fuente = await new Promise((resolve, reject) => {
                    const img = new Image();
                    img.onload = () => resolve(img);
                    img.onerror = reject;
                    img.src = URL.createObjectURL(archivo);
                });
            }
            const escala = Math.min(1, MAX / Math.max(fuente.width, fuente.height));
            const canvas = document.createElement('canvas');
            canvas.width = Math.round(fuente.width * escala);
            canvas.height = Math.round(fuente.height * escala);
            canvas.getContext('2d').drawImage(fuente, 0, 0, canvas.width, canvas.height);
            const blob = await new Promise((r) => canvas.toBlob(r, 'image/jpeg', 0.8));
            return blob && blob.size < archivo.size ? blob : archivo;
        } catch (e) {
            return archivo; // formato no soportado por el navegador: se sube el original
        }
    }

    if (fotoInput && picker) {
        fotoInput.addEventListener('change', async () => {
            const archivo = fotoInput.files && fotoInput.files[0];
            if (!archivo) return;
            picker.classList.add('has-foto');
            let img = picker.querySelector('img');
            if (!img) {
                img = document.createElement('img');
                img.alt = 'Vista previa';
                picker.appendChild(img);
                const tag = document.createElement('span');
                tag.className = 'foto-cambiar';
                tag.textContent = 'Cambiar foto';
                picker.appendChild(tag);
            }
            img.src = URL.createObjectURL(archivo);
            fotoLista = await comprimir(archivo);

            // En modo edición el formulario se envía normal: reemplazamos el archivo por el comprimido.
            if (form.dataset.modo === 'editar' && fotoLista !== archivo && window.DataTransfer) {
                try {
                    const dt = new DataTransfer();
                    dt.items.add(new File([fotoLista], 'foto.jpg', { type: 'image/jpeg' }));
                    fotoInput.files = dt.files;
                } catch (e) { /* navegador antiguo: se sube el original */ }
            }
        });
    }

    // --- Envío ---
    if (form.dataset.modo === 'editar' || !hayIndexedDB) return; // edición: POST tradicional

    const boton = form.querySelector('[type=submit]');

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!obraSel.value || !subSel.value) {
            MV.toast('Selecciona la obra y la subetapa.', 'warning');
            (obraSel.value ? subSel : obraSel).focus();
            return;
        }
        const total = inputsPuntos.reduce((s, i) => s + valor(i), 0);
        if (!total && !confirm('No ingresaste puntos. ¿Enviar el reporte igual?')) return;

        boton.classList.add('is-loading');
        const campos = {
            usuario_id: usuarioId,
            obra: obraSel.value,
            subetapa: subSel.value,
            comentario: form.querySelector('[name=comentario]').value,
        };
        inputsPuntos.forEach((i) => { campos[i.name] = valor(i); });

        const item = {
            uuid: (crypto.randomUUID && crypto.randomUUID()) ||
                'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
                    const r = (Math.random() * 16) | 0;
                    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
                }),
            creado: new Date().toISOString(),
            url: form.dataset.apiUrl,
            csrf: MV.getCookie('csrftoken'),
            campos,
            foto: fotoLista,
            foto_nombre: 'foto.jpg',
            resumen: {
                obra: obraSel.options ? obraSel.options[obraSel.selectedIndex].text : obraSel.dataset.nombre,
                subetapa: subSel.options[subSel.selectedIndex].text,
                total,
            },
        };

        // 1) Primero se guarda en el teléfono: nunca se pierde un reporte.
        try {
            await Outbox.guardar(item);
        } catch (err) {
            // Sin almacenamiento disponible (p. ej. modo incógnito): envío tradicional.
            boton.classList.remove('is-loading');
            form.submit();
            return;
        }

        // 2) Se intenta enviar de inmediato.
        const r = await Outbox.enviarUno(item, MV.getCookie('csrftoken'));
        if (r.estado === 'enviado') {
            MV.toastSiguientePagina('Reporte enviado correctamente. ¡Buen trabajo!', 'success');
            window.location.href = form.dataset.exitoUrl;
            return;
        }
        if (r.estado === 'rechazado') {
            await Outbox.borrar(item.uuid);
            boton.classList.remove('is-loading');
            MV.toast(r.data.mensaje || 'Revisa los datos del reporte.', 'error');
            return;
        }

        // 3) Sin señal / error del servidor: queda en la bandeja y se reintenta solo.
        item.offline = true;
        await Outbox.guardar(item);
        try {
            const reg = await MV.swListo;
            if (reg && 'sync' in reg) await reg.sync.register('enviar-reportes');
        } catch (err) { /* Background Sync no disponible: se reintenta al volver online */ }

        if (r.estado === 'login') {
            MV.toastSiguientePagina('Reporte guardado. Tu sesión expiró: vuelve a ingresar y se enviará.', 'warning');
        } else {
            MV.toastSiguientePagina('Sin señal: el reporte quedó guardado y se enviará automáticamente.', 'warning');
        }
        window.location.href = form.dataset.exitoUrl;
    });
})();
