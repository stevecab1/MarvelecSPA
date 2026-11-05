/* MARVELEC SPA — Chat de consultas */
(function () {
    'use strict';

    const MV = window.MV;
    const chat = document.querySelector('[data-chat]');
    if (!chat) return;

    const lista = chat.querySelector('[data-chat-mensajes]');
    const form = chat.querySelector('[data-chat-form]');
    const texto = chat.querySelector('[data-chat-texto]');
    const inputFoto = chat.querySelector('[data-chat-foto]');
    const adjunto = chat.querySelector('[data-chat-adjunto]');
    const adjuntoNombre = chat.querySelector('[data-chat-adjunto-nombre]');
    const boton = form.querySelector('[type=submit]');
    const SONDEO_MS = 5000;

    let ultimo = parseInt(chat.dataset.ultimo, 10) || 0;
    let fotoLista = null;
    let enviando = false;

    function alFondo() {
        lista.scrollTop = lista.scrollHeight;
    }

    function pintar(m) {
        const vacio = lista.querySelector('[data-chat-vacio]');
        if (vacio) vacio.remove();
        const div = document.createElement('div');
        div.className = 'burbuja' + (m.propio ? ' es-propio' : '');
        let html = '';
        if (m.foto) {
            html += '<img src="' + MV.escape(m.foto) + '" alt="Foto adjunta" loading="lazy" data-lightbox="' +
                MV.escape(m.foto) + '" data-caption="' + MV.escape(m.autor) + ' — ' + MV.escape(m.fecha) + ' ' + MV.escape(m.hora) + '">';
        }
        if (m.texto) html += '<p>' + MV.escape(m.texto).replace(/\n/g, '<br>') + '</p>';
        div.innerHTML = html + '<time>' + MV.escape(m.hora) + '</time>';
        lista.appendChild(div);
        return div;
    }

    // ---------- Sondeo ----------
    // Render en plan gratuito no mantiene WebSockets: se consulta cada pocos segundos
    // mientras la conversación esté a la vista.
    async function buscarNuevos() {
        if (document.hidden || !navigator.onLine || enviando) return;
        try {
            const resp = await fetch(chat.dataset.urlMensajes + '?desde=' + ultimo, { credentials: 'same-origin' });
            if (!resp.ok) return;
            const data = await resp.json();
            if (!data.mensajes.length) return;
            const pegadoAbajo = lista.scrollHeight - lista.scrollTop - lista.clientHeight < 80;
            data.mensajes.forEach(pintar);
            ultimo = data.ultimo_id;
            if (pegadoAbajo) alFondo();
            MV.actualizarNotificaciones && MV.actualizarNotificaciones();
        } catch (e) { /* sin señal: se reintenta en el próximo ciclo */ }
    }

    setInterval(buscarNuevos, SONDEO_MS);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) buscarNuevos(); });
    window.addEventListener('online', buscarNuevos);

    // ---------- Adjuntar foto ----------
    if (inputFoto) {
        inputFoto.addEventListener('change', async () => {
            const archivo = inputFoto.files && inputFoto.files[0];
            if (!archivo) return;
            fotoLista = await MV.comprimirImagen(archivo);
            adjuntoNombre.textContent = 'Foto lista para enviar';
            adjunto.hidden = false;
            texto.focus();
        });
    }

    function quitarFoto() {
        fotoLista = null;
        if (inputFoto) inputFoto.value = '';
        adjunto.hidden = true;
    }
    chat.querySelector('[data-chat-quitar]').addEventListener('click', quitarFoto);

    // ---------- Enviar ----------
    // El mensaje no se guarda para después: una consulta que llega dos horas tarde confunde más
    // de lo que ayuda, así que sin señal se avisa y el texto queda escrito.
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const contenido = texto.value.trim();
        if (!contenido && !fotoLista) return;
        if (!navigator.onLine) {
            MV.toast('Sin señal: tu mensaje no se envió. Inténtalo cuando vuelva la conexión.', 'warning', 7000);
            return;
        }

        const datos = new FormData();
        datos.append('texto', contenido);
        if (fotoLista) datos.append('foto', fotoLista, 'foto.jpg');

        enviando = true;
        boton.classList.add('is-loading');
        try {
            const resp = await MV.post(chat.dataset.urlEnviar, datos);
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.mensaje || 'No se pudo enviar.');
            pintar(data.mensaje);
            ultimo = Math.max(ultimo, data.mensaje.id);
            texto.value = '';
            texto.style.height = '';
            quitarFoto();
            alFondo();
        } catch (err) {
            MV.toast(err.message || 'No se pudo enviar el mensaje.', 'error');
        } finally {
            enviando = false;
            boton.classList.remove('is-loading');
            texto.focus();
        }
    });

    // Enter envía; Shift+Enter hace salto de línea.
    texto.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey) {
            e.preventDefault();
            form.requestSubmit();
        }
    });

    // La caja crece con el texto, hasta un límite.
    texto.addEventListener('input', () => {
        texto.style.height = 'auto';
        texto.style.height = Math.min(texto.scrollHeight, 120) + 'px';
    });

    alFondo();
})();
