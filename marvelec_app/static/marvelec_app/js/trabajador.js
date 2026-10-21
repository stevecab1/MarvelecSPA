/* MARVELEC SPA — App del trabajador (celular) */
(function () {
    'use strict';

    const MV = window.MV;
    const Outbox = window.MarvelecOutbox;
    const hayIndexedDB = 'indexedDB' in window && Outbox;
    const usuarioId = document.body.dataset.userId;

    // =========================================================
    // Bandeja de salida: registros guardados sin señal
    // =========================================================
    function fechaCorta(iso) {
        const d = new Date(iso);
        return d.toLocaleDateString('es-CL', { day: '2-digit', month: '2-digit' }) + ' ' +
            d.toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' });
    }

    function tarjetaPendiente(item) {
        const r = item.resumen || {};
        // Los registros guardados con la versión anterior traían obra/subetapa.
        const titulo = r.titulo || [r.obra, r.subetapa].filter(Boolean).join(' / ') || 'Registro';
        const div = document.createElement('div');
        div.className = 'r-card is-pending';
        const thumb = item.foto
            ? '<img class="r-thumb" alt="" src="' + URL.createObjectURL(item.foto) + '">'
            : '<div class="r-thumb">' + MV.icono(r.icono || 'network') + '</div>';
        div.innerHTML = thumb +
            '<div class="r-body">' +
            '<div class="r-top"><span class="r-title">' + MV.escape(titulo) + '</span>' +
            (item.error
                ? '<span class="badge badge-observado">Rechazado</span>'
                : '<span class="badge badge-offline">' + MV.icono('cloud-off', 'icon-sm') + ' Por enviar</span>') +
            '</div>' +
            '<div class="r-meta"><span>' + MV.icono('clock', 'icon-sm') + ' ' + fechaCorta(item.creado) + '</span>' +
            (r.detalle ? '<span>' + MV.escape(r.detalle) + '</span>' : '') +
            (r.total ? '<span class="pts">' + r.total + ' pts</span>' : '') + '</div>' +
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
            if (n) n.textContent = porEnviar === 1 ? '1 registro' : porEnviar + ' registros';
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
            const msg = r.enviados.length === 1 ? 'Se envió 1 registro que estaba pendiente.'
                : 'Se enviaron ' + r.enviados.length + ' registros que estaban pendientes.';
            // En un formulario no recargamos para no borrar lo que el trabajador está escribiendo.
            if (document.querySelector('[data-registro-form]')) {
                MV.toast(msg, 'success');
            } else {
                MV.toastSiguientePagina(msg, 'success');
                window.location.reload();
                return;
            }
        }
        if (r.login) MV.toast('Tu sesión expiró. Vuelve a ingresar para enviar lo pendiente.', 'warning', 9000);
        else if (manual && r.sinRed) MV.toast('No se pudo conectar. Se reintentará automáticamente.', 'warning');
        pintarBandeja();
    }

    MV.onOutboxEnviado = function () { pintarBandeja(); };

    document.addEventListener('click', async (e) => {
        const enviar = e.target.closest('[data-outbox-enviar]');
        if (enviar) {
            enviar.classList.add('is-loading');
            await enviarPendientes(true);
            enviar.classList.remove('is-loading');
            return;
        }
        const descartar = e.target.closest('[data-outbox-descartar]');
        if (descartar && confirm('¿Descartar este registro? No se enviará.')) {
            await Outbox.borrar(descartar.dataset.outboxDescartar);
            pintarBandeja();
        }
    });

    window.addEventListener('online', () => enviarPendientes(false));
    pintarBandeja().then(() => enviarPendientes(false));

    // =========================================================
    // Formularios de registro (avance, incidencia, llegada)
    // =========================================================
    const form = document.querySelector('[data-registro-form]');
    if (!form) return;
    const tipoForm = form.dataset.registroForm;

    // --- Ubicación GPS (opcional: dentro de edificios puede fallar) ---
    const gpsEstado = form.querySelector('[data-gps-estado]');
    function pintarGps(texto, ok) {
        if (!gpsEstado) return;
        gpsEstado.innerHTML = MV.icono('pin', 'icon-sm') + ' ' + MV.escape(texto);
        gpsEstado.style.color = ok ? 'var(--ok)' : '';
    }
    if (form.querySelector('[name=latitud]')) {
        if (!('geolocation' in navigator)) {
            pintarGps('Este teléfono no entrega ubicación; se enviará sin GPS.');
        } else {
            navigator.geolocation.getCurrentPosition((pos) => {
                form.querySelector('[name=latitud]').value = pos.coords.latitude.toFixed(6);
                form.querySelector('[name=longitud]').value = pos.coords.longitude.toFixed(6);
                const prec = form.querySelector('[name=precision]');
                if (prec) prec.value = Math.round(pos.coords.accuracy);
                pintarGps('Ubicación registrada (±' + Math.round(pos.coords.accuracy) + ' m)', true);
            }, () => {
                pintarGps('Sin ubicación (permiso denegado o sin señal GPS). Se enviará igual.');
            }, { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 });
        }
    }

    // --- Foto: vista previa + compresión (sube rápido con poca señal) ---
    const fotoInput = form.querySelector('input[type=file][name=foto]');
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

    // --- Selector de puntos ---
    const selector = form.querySelector('[data-selector]');
    const datosSel = document.getElementById('selector-data');
    const sel = selector && datosSel ? crearSelector(selector, JSON.parse(datosSel.textContent)) : null;

    function crearSelector(raiz, datos) {
        const etapas = datos.etapas;
        const bit = {};
        etapas.forEach((e, i) => { bit[e.clave] = 1 << i; });
        const nombreEtapa = {};
        etapas.forEach((e) => { nombreEtapa[e.clave] = e.nombre.toLowerCase(); });
        const racks = {};
        datos.racks.forEach((r) => { racks[String(r.id)] = r; });

        const rackSel = form.querySelector('[name=rack]');
        const cajas = Array.from(form.querySelectorAll('input[name=etapas]'));
        const cont = raiz.querySelector('[data-paquetes]');
        const ocultos = raiz.querySelector('[data-puntos-hidden]');
        const texto = raiz.querySelector('[name=codigos]');
        const errorCodigos = raiz.querySelector('[data-codigos-error]');
        const seleccion = new Set((raiz.dataset.seleccion || '').split(',').filter(Boolean).map(Number));
        const esAvance = tipoForm === 'avance';

        // Recordar el último rack usado (ahorra un paso cada día).
        if (rackSel && !rackSel.value) {
            let ultimo = null;
            try { ultimo = localStorage.getItem('mv-ultimo-rack'); } catch (e) { /* sin storage */ }
            const opciones = Array.from(rackSel.options).filter((o) => o.value);
            if (ultimo && opciones.some((o) => o.value === ultimo)) rackSel.value = ultimo;
            else if (opciones.length === 1) rackSel.value = opciones[0].value;
        }

        function etapasElegidas() {
            return cajas.filter((c) => c.checked).map((c) => c.value);
        }

        function rackActual() { return rackSel ? racks[rackSel.value] : null; }

        // Mismo criterio que el servidor (servicios.validar_avances).
        function estado(p) {
            const [, , , , mascara, bloqueado] = p;
            if (bloqueado) return esAvance ? { clase: 'bloq', motivo: 'bloqueado por incidencia' } : { clase: 'bloq-sel' };
            if (!esAvance) return { clase: 'ok' };
            const elegidas = etapasElegidas();
            if (!elegidas.length) return { clase: 'ok' };
            const hechas = new Set(etapas.filter((e) => mascara & bit[e.clave]).map((e) => e.clave));
            const pendientes = etapas.filter((e) => elegidas.includes(e.clave) && !hechas.has(e.clave));
            if (!pendientes.length) return { clase: 'hecho', motivo: 'etapa ya registrada' };
            let valida = false;
            const faltan = [];
            pendientes.forEach((e) => {
                const falta = e.requiere.filter((r) => !hechas.has(r));
                if (falta.length) faltan.push(...falta.map((f) => nombreEtapa[f]));
                else { hechas.add(e.clave); valida = true; }
            });
            return valida ? { clase: 'ok' } : { clase: 'falta', motivo: 'falta ' + [...new Set(faltan)].join(' y ') };
        }

        function seleccionable(clase) { return clase === 'ok' || clase === 'bloq-sel'; }
        function codigo(p) { return p[1] + '-' + String(p[2]).padStart(3, '0'); }

        function sincronizar() {
            ocultos.innerHTML = '';
            seleccion.forEach((id) => {
                const input = document.createElement('input');
                input.type = 'hidden';
                input.name = 'puntos';
                input.value = id;
                ocultos.appendChild(input);
            });
            const n = seleccion.size;
            raiz.querySelector('[data-sel-n]').textContent = n;
            raiz.querySelector('[data-sel-plural]').hidden = n === 1;
            form.querySelectorAll('[data-submit-n]').forEach((el) => { el.textContent = n ? '(' + n + ')' : ''; });
        }

        function pintar() {
            const rack = rackActual();
            if (!rack) {
                cont.innerHTML = '<div class="empty small">' + MV.icono('network') + 'Elige el rack para ver sus puntos.</div>';
                seleccion.clear();
                sincronizar();
                return;
            }
            if (!rack.puntos.length) {
                cont.innerHTML = '<div class="empty small">' + MV.icono('info') +
                    'Este rack aún no tiene puntos cargados. Avísale a tu supervisor.</div>';
                return;
            }
            const grupos = new Map();
            rack.puntos.forEach((p) => {
                const clave = p[3] == null ? 'sin' : p[3];
                if (!grupos.has(clave)) grupos.set(clave, []);
                grupos.get(clave).push(p);
            });
            const ids = new Set(rack.puntos.map((p) => p[0]));
            Array.from(seleccion).forEach((id) => { if (!ids.has(id)) seleccion.delete(id); });

            const claves = Array.from(grupos.keys()).sort((a, b) => (a === 'sin') - (b === 'sin') || a - b);
            cont.innerHTML = claves.map((clave) => {
                const puntos = grupos.get(clave);
                let disponibles = 0;
                const chips = puntos.map((p) => {
                    const est = estado(p);
                    if (!seleccionable(est.clase)) seleccion.delete(p[0]);
                    else disponibles++;
                    const elegido = seleccion.has(p[0]);
                    return '<button type="button" class="pchip is-' + est.clase + (elegido ? ' is-sel' : '') + '"' +
                        ' data-punto="' + p[0] + '"' + (seleccionable(est.clase) ? '' : ' disabled') +
                        ' title="' + codigo(p) + (est.motivo ? ': ' + est.motivo : '') + '" aria-pressed="' + elegido + '">' +
                        codigo(p) + '</button>';
                }).join('');
                const info = rack.paquetes[clave] || [];
                const detalle = [info[1], info[0] ? info[0] + ' m' : ''].filter(Boolean).join(' · ');
                return '<div class="paquete">' +
                    '<div class="paquete-head"><b>' + (clave === 'sin' ? 'Sin paquete' : 'Paquete ' + String(clave).padStart(2, '0')) + '</b>' +
                    '<span class="small muted">' + MV.escape(detalle) + (detalle ? ' · ' : '') + disponibles + ' disponible' + (disponibles === 1 ? '' : 's') + '</span>' +
                    (disponibles ? '<button type="button" class="btn btn-ghost btn-sm" data-sel-paquete="' + clave + '">Todos</button>' : '') +
                    '</div><div class="pchips">' + chips + '</div></div>';
            }).join('');
            sincronizar();
        }

        // Mismo formato que el servidor (servicios.parsear_codigos): "DT 1-2-3, 7 a 12; VD-015".
        function parsear(valor) {
            const tokens = (valor || '').toUpperCase().match(/[A-ZÑ]+|\d+|\.\./g) || [];
            const rango = ['A', 'AL', 'HASTA', '..'];
            const pares = [];
            const errores = [];
            let sigla = null;
            for (let i = 0; i < tokens.length; i++) {
                const t = tokens[i];
                if (/^\d+$/.test(t)) {
                    if (!sigla) { errores.push('Falta el tipo antes de "' + t + '" (ej. DT ' + t + ').'); continue; }
                    const n = parseInt(t, 10);
                    if (i + 2 < tokens.length && rango.includes(tokens[i + 1]) && /^\d+$/.test(tokens[i + 2])) {
                        const m = parseInt(tokens[i + 2], 10);
                        const desde = Math.min(n, m);
                        const hasta = Math.max(n, m);
                        if (hasta - desde > 500) errores.push('El rango ' + sigla + ' ' + desde + ' a ' + hasta + ' es demasiado grande.');
                        else for (let k = desde; k <= hasta; k++) pares.push([sigla, k]);
                        i += 2;
                    } else {
                        pares.push([sigla, n]);
                    }
                } else if (!rango.includes(t) && t !== 'Y' && t !== 'E') {
                    sigla = t;
                }
            }
            return { pares, errores };
        }

        function aplicarCodigos() {
            if (!texto || !texto.value.trim()) return true;
            const rack = rackActual();
            if (!rack) {
                MV.toast('Primero elige el rack.', 'warning');
                return false;
            }
            const { pares, errores } = parsear(texto.value);
            const porCodigo = {};
            rack.puntos.forEach((p) => { porCodigo[p[1] + '-' + p[2]] = p; });
            const noExisten = [];
            const noDisponibles = [];
            let marcados = 0;
            pares.forEach(([s, n]) => {
                const p = porCodigo[s + '-' + n];
                if (!p) { noExisten.push(s + '-' + String(n).padStart(3, '0')); return; }
                const est = estado(p);
                if (!seleccionable(est.clase)) { noDisponibles.push(codigo(p) + ' (' + est.motivo + ')'); return; }
                if (!seleccion.has(p[0])) marcados++;
                seleccion.add(p[0]);
            });
            const avisos = [...errores];
            if (noExisten.length) avisos.push('No existen en el rack ' + rack.nombre + ': ' + noExisten.slice(0, 10).join(', ') + (noExisten.length > 10 ? '…' : '') + '.');
            if (noDisponibles.length) avisos.push('No se pueden marcar: ' + noDisponibles.slice(0, 6).join(', ') + (noDisponibles.length > 6 ? '…' : '') + '.');
            errorCodigos.textContent = avisos.join(' ');
            errorCodigos.hidden = !avisos.length;
            texto.value = '';
            pintar();
            if (marcados) MV.toast(marcados + ' punto' + (marcados === 1 ? '' : 's') + ' marcado' + (marcados === 1 ? '' : 's') + '.', 'success', 2000);
            return true;
        }

        raiz.addEventListener('click', (e) => {
            const chip = e.target.closest('[data-punto]');
            if (chip && !chip.disabled) {
                const id = Number(chip.dataset.punto);
                if (seleccion.has(id)) seleccion.delete(id); else seleccion.add(id);
                chip.classList.toggle('is-sel', seleccion.has(id));
                chip.setAttribute('aria-pressed', String(seleccion.has(id)));
                if (navigator.vibrate) navigator.vibrate(6);
                sincronizar();
                return;
            }
            const paquete = e.target.closest('[data-sel-paquete]');
            if (paquete) {
                const botones = Array.from(paquete.closest('.paquete').querySelectorAll('[data-punto]:not([disabled])'));
                const todos = botones.every((b) => seleccion.has(Number(b.dataset.punto)));
                botones.forEach((b) => { if (todos) seleccion.delete(Number(b.dataset.punto)); else seleccion.add(Number(b.dataset.punto)); });
                pintar();
                return;
            }
            if (e.target.closest('[data-sel-limpiar]')) {
                seleccion.clear();
                pintar();
                return;
            }
            if (e.target.closest('[data-aplicar-codigos]')) aplicarCodigos();
        });
        if (texto) {
            texto.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); aplicarCodigos(); }
            });
        }
        if (rackSel) {
            rackSel.addEventListener('change', () => {
                try { localStorage.setItem('mv-ultimo-rack', rackSel.value); } catch (e) { /* sin storage */ }
                seleccion.clear();
                pintar();
            });
        }
        cajas.forEach((c) => c.addEventListener('change', pintar));
        pintar();

        return {
            aplicarCodigos,
            ids: () => Array.from(seleccion),
            rack: rackActual,
            etapas: etapasElegidas,
        };
    }

    // --- Envío ---
    if (form.dataset.modo === 'editar' || !hayIndexedDB) {
        // Edición o navegador sin almacenamiento: POST tradicional (los puntos van en inputs ocultos).
        if (sel) form.addEventListener('submit', (e) => { if (!sel.aplicarCodigos()) e.preventDefault(); });
        return;
    }

    const boton = form.querySelector('[type=submit]');

    function valorCampo(nombre) {
        const el = form.querySelector('[name=' + nombre + ']');
        return el ? el.value : '';
    }

    function armarRegistro() {
        const campos = { usuario_id: usuarioId };
        let resumen = {};
        if (tipoForm === 'avance' || tipoForm === 'incidencia') {
            if (!sel.aplicarCodigos()) return null;
            const rack = sel.rack();
            if (!rack) { MV.toast('Elige el rack.', 'warning'); return null; }
            const ids = sel.ids();
            if (tipoForm === 'avance' && !sel.etapas().length) { MV.toast('Marca qué etapa terminaste.', 'warning'); return null; }
            if (!ids.length) { MV.toast('Selecciona al menos un punto.', 'warning'); return null; }
            campos.rack = rack.id;
            campos.puntos = ids;
            campos.comentario = valorCampo('comentario');
            if (tipoForm === 'avance') {
                const etapas = sel.etapas();
                campos.etapas = etapas;
                const nombres = Array.from(form.querySelectorAll('input[name=etapas]:checked'))
                    .map((c) => c.closest('label').textContent.trim());
                resumen = { titulo: 'Rack ' + rack.nombre + ' · ' + nombres.join(' + '), detalle: ids.length + ' puntos',
                    total: ids.length * etapas.length, icono: 'network' };
            } else {
                const tipo = form.querySelector('input[name=tipo]:checked');
                if (!tipo) { MV.toast('Elige qué pasó.', 'warning'); return null; }
                campos.tipo = tipo.value;
                campos.latitud = valorCampo('latitud');
                campos.longitud = valorCampo('longitud');
                resumen = { titulo: 'Incidencia: ' + tipo.closest('label').textContent.trim(),
                    detalle: 'Rack ' + rack.nombre + ' · ' + ids.length + ' punto' + (ids.length === 1 ? '' : 's'), icono: 'alert' };
            }
        } else if (tipoForm === 'asistencia') {
            const obra = form.querySelector('[name=obra]');
            if (!obra || !obra.value) { MV.toast('Selecciona la obra.', 'warning'); return null; }
            if (!fotoLista) { MV.toast('Toma la foto del lugar para marcar tu llegada.', 'warning'); return null; }
            campos.obra = obra.value;
            campos.latitud = valorCampo('latitud');
            campos.longitud = valorCampo('longitud');
            campos.precision = valorCampo('precision');
            const nombreObra = obra.dataset.nombre || (obra.options ? obra.options[obra.selectedIndex].text : '');
            resumen = { titulo: 'Llegada', detalle: nombreObra, icono: 'calendar' };
        }
        return {
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
            resumen,
        };
    }

    function mensajeExito(data) {
        if (tipoForm === 'asistencia') return 'Llegada registrada. Tu supervisor la confirmará.';
        if (tipoForm === 'incidencia') {
            return 'Incidencia registrada en ' + data.n + ' punto' + (data.n === 1 ? '' : 's') + '. Se avisó al supervisor.';
        }
        let msg = 'Reporte enviado: ' + data.total_puntos + ' etapa' + (data.total_puntos === 1 ? '' : 's') + ' registrada' + (data.total_puntos === 1 ? '' : 's') + '.';
        if (data.omitidos && data.omitidos.length) msg += ' ' + data.omitidos.length + ' no se registraron: revisa el detalle.';
        return msg;
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const item = armarRegistro();
        if (!item) return;
        boton.classList.add('is-loading');

        // 1) Primero se guarda en el teléfono: nunca se pierde un registro.
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
            const data = r.data || {};
            const conAviso = data.omitidos && data.omitidos.length;
            MV.toastSiguientePagina(mensajeExito(data), conAviso ? 'warning' : 'success');
            window.location.href = conAviso && data.url ? data.url : form.dataset.exitoUrl;
            return;
        }
        if (r.estado === 'rechazado') {
            await Outbox.borrar(item.uuid);
            boton.classList.remove('is-loading');
            MV.toast((r.data && r.data.mensaje) || 'Revisa los datos.', 'error', 9000);
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
            MV.toastSiguientePagina('Quedó guardado. Tu sesión expiró: vuelve a ingresar y se enviará.', 'warning');
        } else {
            MV.toastSiguientePagina('Sin señal: quedó guardado en el teléfono y se enviará automáticamente.', 'warning');
        }
        window.location.href = form.dataset.exitoUrl;
    });
})();
