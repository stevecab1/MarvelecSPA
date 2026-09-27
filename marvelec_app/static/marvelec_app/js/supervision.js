/* MARVELEC SPA — Programa de supervisión / gerencia */
(function () {
    'use strict';

    const MV = window.MV;

    // =========================================================
    // Filtro de subetapas dependiente de la obra
    // =========================================================
    const datosSub = document.getElementById('filtro-subetapas');
    const subSel = document.getElementById('f-subetapa');
    const obraSel = document.getElementById('f-obra');
    if (datosSub && subSel) {
        const porObra = JSON.parse(datosSub.textContent);
        const seleccion = subSel.dataset.seleccion;
        const pintar = () => {
            const obra = obraSel ? obraSel.value : subSel.dataset.obraFija;
            const lista = obra ? (porObra[obra] || []) : [];
            subSel.innerHTML = '<option value="">' + (obra ? 'Todas' : 'Elige una obra') + '</option>';
            lista.forEach((s) => {
                const op = new Option(s.nombre, s.id);
                if (String(s.id) === seleccion) op.selected = true;
                subSel.add(op);
            });
            subSel.disabled = !obra;
        };
        if (obraSel) obraSel.addEventListener('change', () => { subSel.dataset.seleccion = ''; pintar(); });
        pintar();
    }

    // =========================================================
    // Gráficos (Chart.js)
    // =========================================================
    const datosGraficos = document.getElementById('datos-graficos');
    if (datosGraficos && window.Chart) {
        const g = JSON.parse(datosGraficos.textContent);
        const css = getComputedStyle(document.documentElement);
        const color = (v) => css.getPropertyValue(v).trim();
        const colores = { red: color('--tipo-red'), fuerza: color('--tipo-fuerza'), iluminacion: color('--tipo-iluminacion') };
        const nombres = { red: 'Red', fuerza: 'Fuerza', iluminacion: 'Iluminación' };
        const texto = color('--muted');
        const grilla = color('--border');

        Chart.defaults.font.family = css.getPropertyValue('--font');
        Chart.defaults.color = texto;
        Chart.defaults.plugins.legend.display = false;
        Chart.defaults.plugins.tooltip.padding = 10;
        Chart.defaults.plugins.tooltip.cornerRadius = 8;
        Chart.defaults.maintainAspectRatio = false;

        const ejes = {
            x: { stacked: true, grid: { display: false }, ticks: { maxRotation: 0, autoSkipPadding: 12 } },
            y: { stacked: true, beginAtZero: true, grid: { color: grilla }, border: { display: false }, ticks: { precision: 0 } },
        };

        const dias = document.getElementById('g-dias');
        if (dias) {
            new Chart(dias, {
                type: 'bar',
                data: {
                    labels: g.por_dia.labels,
                    datasets: Object.keys(g.por_dia.series).map((tipo) => ({
                        label: nombres[tipo],
                        data: g.por_dia.series[tipo],
                        backgroundColor: colores[tipo],
                        borderRadius: 4,
                        maxBarThickness: 28,
                    })),
                },
                options: {
                    scales: ejes,
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                        tooltip: {
                            callbacks: {
                                footer: (items) => 'Total: ' + items.reduce((s, i) => s + i.parsed.y, 0),
                            },
                        },
                    },
                },
            });
        }

        const tipos = document.getElementById('g-tipos');
        if (tipos) {
            const total = g.por_tipo.valores.reduce((a, b) => a + b, 0);
            new Chart(tipos, {
                type: 'doughnut',
                data: {
                    labels: g.por_tipo.labels,
                    datasets: [{
                        data: total ? g.por_tipo.valores : [1],
                        backgroundColor: total ? g.por_tipo.claves.map((k) => colores[k]) : [grilla],
                        borderWidth: 0,
                    }],
                },
                options: {
                    cutout: '68%',
                    plugins: {
                        legend: { display: true, position: 'bottom', labels: { usePointStyle: true, boxWidth: 8, padding: 16 } },
                        tooltip: { enabled: !!total },
                    },
                },
                plugins: [{
                    id: 'centro',
                    afterDraw(chart) {
                        const { ctx, chartArea } = chart;
                        const x = (chartArea.left + chartArea.right) / 2;
                        const y = (chartArea.top + chartArea.bottom) / 2;
                        ctx.save();
                        ctx.textAlign = 'center';
                        ctx.fillStyle = color('--text');
                        ctx.font = '800 26px ' + Chart.defaults.font.family;
                        ctx.fillText(total, x, y + 4);
                        ctx.fillStyle = texto;
                        ctx.font = '600 12px ' + Chart.defaults.font.family;
                        ctx.fillText('puntos', x, y + 24);
                        ctx.restore();
                    },
                }],
            });
        }

        const subs = document.getElementById('g-subetapas');
        if (subs) {
            new Chart(subs, {
                type: 'bar',
                data: {
                    labels: g.por_subetapa.map((s) => s.nombre),
                    datasets: [{
                        data: g.por_subetapa.map((s) => s.total),
                        backgroundColor: color('--brand-400') || '#5b47c7',
                        borderRadius: 6,
                        maxBarThickness: 22,
                    }],
                },
                options: {
                    indexAxis: 'y',
                    scales: {
                        x: { beginAtZero: true, grid: { color: grilla }, border: { display: false }, ticks: { precision: 0 } },
                        y: { grid: { display: false } },
                    },
                    plugins: {
                        tooltip: {
                            callbacks: {
                                title: (items) => {
                                    const s = g.por_subetapa[items[0].dataIndex];
                                    return s.obra + ' / ' + s.nombre;
                                },
                                label: (item) => item.parsed.x + ' puntos',
                            },
                        },
                    },
                },
            });
        }
    }

    // =========================================================
    // Cola de revisión
    // =========================================================
    const cola = document.querySelector('[data-cola]');
    if (!cola) return;

    const vacia = document.querySelector('[data-cola-vacia]');
    const totalEl = document.querySelector('[data-cola-total]');
    let foco = null;

    function tarjetas() { return Array.from(cola.querySelectorAll('[data-review]')); }

    function enfocar(card, desplazar) {
        if (!card) return;
        tarjetas().forEach((c) => c.classList.toggle('is-focused', c === card));
        foco = card;
        if (desplazar === false) return;
        card.focus({ preventScroll: true });
        card.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }

    function quitar(card) {
        const siguiente = card.nextElementSibling || card.previousElementSibling;
        card.classList.add('is-done');
        setTimeout(() => {
            card.remove();
            const n = tarjetas().length;
            if (totalEl) totalEl.textContent = Math.max(0, parseInt(totalEl.textContent, 10) - 1);
            if (!n) {
                const form = document.querySelector('[data-form-masivo]');
                if (form) form.hidden = true;
                if (vacia) vacia.hidden = false;
            } else if (siguiente) {
                enfocar(siguiente);
            }
            actualizarSeleccion();
            MV.actualizarNotificaciones && MV.actualizarNotificaciones();
        }, 260);
    }

    async function revisar(card, accion, comentario) {
        const datos = new FormData();
        datos.append('accion', accion);
        datos.append('comentario', comentario || '');
        card.querySelectorAll('button').forEach((b) => { b.disabled = true; });
        try {
            const resp = await MV.post(card.dataset.urlRevisar, datos);
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.mensaje || 'No se pudo guardar la revisión.');
            MV.toast(data.mensaje, 'success', 2500);
            quitar(card);
        } catch (err) {
            MV.toast(err.message || 'Error de conexión.', 'error');
            card.querySelectorAll('button').forEach((b) => { b.disabled = false; });
        }
    }

    function mostrarObservar(card) {
        const caja = card.querySelector('[data-observar]');
        caja.hidden = false;
        caja.querySelector('textarea').focus();
    }

    cola.addEventListener('click', (e) => {
        const card = e.target.closest('[data-review]');
        if (!card) return;
        if (!e.target.closest('textarea, input, a, [data-lightbox]')) enfocar(card);
        const boton = e.target.closest('[data-accion]');
        if (!boton) return;
        const accion = boton.dataset.accion;
        if (accion === 'aprobar') revisar(card, 'aprobar');
        if (accion === 'mostrar-observar') mostrarObservar(card);
        if (accion === 'observar') {
            const texto = card.querySelector('[data-observar] textarea').value.trim();
            if (!texto) {
                MV.toast('Escribe qué debe corregir el trabajador.', 'warning');
                return;
            }
            revisar(card, 'observar', texto);
        }
    });

    // Atajos de teclado: J/K para moverse, A aprobar, O observar.
    document.addEventListener('keydown', (e) => {
        if (e.target.closest('textarea, input, select') || e.ctrlKey || e.metaKey || e.altKey) return;
        const lista = tarjetas();
        if (!lista.length) return;
        const i = foco ? lista.indexOf(foco) : -1;
        const tecla = e.key.toLowerCase();
        if (tecla === 'j' || e.key === 'ArrowDown') { e.preventDefault(); enfocar(lista[Math.min(lista.length - 1, i + 1)]); }
        if (tecla === 'k' || e.key === 'ArrowUp') { e.preventDefault(); enfocar(lista[Math.max(0, i - 1)]); }
        if (tecla === 'a' && foco) { e.preventDefault(); revisar(foco, 'aprobar'); }
        if (tecla === 'o' && foco) { e.preventDefault(); mostrarObservar(foco); }
    });

    // Enviar observación con Ctrl+Enter
    cola.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && e.target.matches('[data-observar] textarea')) {
            e.preventDefault();
            e.target.closest('[data-observar]').querySelector('[data-accion=observar]').click();
        }
    });

    // --- Aprobación masiva ---
    const formMasivo = document.querySelector('[data-form-masivo]');
    const checkAll = document.querySelector('[data-check-all]');
    const btnMasivo = document.querySelector('[data-aprobar-seleccion]');
    const nSel = document.querySelector('[data-n-seleccion]');

    function seleccionados() { return Array.from(cola.querySelectorAll('[data-seleccion]:checked')); }
    function actualizarSeleccion() {
        const n = seleccionados().length;
        if (nSel) nSel.textContent = n;
        if (btnMasivo) btnMasivo.disabled = !n;
        if (checkAll) checkAll.checked = n > 0 && n === cola.querySelectorAll('[data-seleccion]').length;
    }
    cola.addEventListener('change', (e) => { if (e.target.matches('[data-seleccion]')) actualizarSeleccion(); });
    if (checkAll) {
        checkAll.addEventListener('change', () => {
            cola.querySelectorAll('[data-seleccion]').forEach((c) => { c.checked = checkAll.checked; });
            actualizarSeleccion();
        });
    }
    if (formMasivo) {
        formMasivo.addEventListener('submit', (e) => {
            const ids = seleccionados().map((c) => c.value);
            if (!ids.length || !confirm('¿Aprobar ' + ids.length + ' reporte(s)?')) {
                e.preventDefault();
                return;
            }
            formMasivo.querySelectorAll('input[name=ids]').forEach((i) => i.remove());
            ids.forEach((id) => {
                const input = document.createElement('input');
                input.type = 'hidden';
                input.name = 'ids';
                input.value = id;
                formMasivo.appendChild(input);
            });
            btnMasivo.classList.add('is-loading');
        });
    }

    enfocar(tarjetas()[0], false);
})();
