
let chartInstance = null;
let historyChartInstance = null;

async function searchCups() {
    const cupsInput = document.getElementById('cupsInput');
    const loading = document.getElementById('loading');
    const resultsArea = document.getElementById('results-area');
    const errorMsg = document.getElementById('error-msg');

    const cups = cupsInput.value.trim().toUpperCase();

    // Basic Validation
    if (!cups) {
        errorMsg.textContent = "Por favor, introduce un CUPS.";
        return;
    }
    if (!/^ES[A-Z0-9]{20}$/.test(cups)) {
        errorMsg.textContent = "Formato de CUPS incorrecto. Debe ser ES + 20 caracteres.";
        return;
    }

    // Reset UI
    errorMsg.textContent = "";
    resultsArea.style.display = 'none';
    loading.style.display = 'flex';

    try {
        const response = await fetch('/api/sips/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cups: cups })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || `Error ${response.status}`);
        }

        renderResults(data);
        resultsArea.style.display = 'block';

    } catch (error) {
        console.error(error);
        errorMsg.textContent = error.message;
    } finally {
        loading.style.display = 'none';
    }
}

function renderResults(data) {
    // 1. Basic Info
    setText('res-cups', data.cups);

    // Construct Address
    let address = data.direccion || "";
    // If no address, try to build it? No, backend sends what it has.
    setText('res-direccion', address);

    const muni = [data.municipio, data.provincia].filter(Boolean).join(' / ');
    setText('res-municipio', muni);

    setText('res-tarifa', data.tarifa);

    const contract = data.contrato || {};
    let status = "Desconocido";
    if (contract.es_baja === 'S') status = "BAJA";
    else if (contract.es_contratable === 'S') status = "CONTRATABLE";
    else if (contract.es_contratable === 'N') status = "NO CONTRATABLE";
    setText('res-estado', status);

    setText('res-distribuidora', data.distribuidor);

    // 2. Power Table
    const powerBody = document.getElementById('power-values');
    powerBody.innerHTML = '';
    const powers = data.potencias_contratadas || {};

    // Check if we have standard keys or need to map
    const periods = ['periodo_1', 'periodo_2', 'periodo_3', 'periodo_4', 'periodo_5', 'periodo_6'];

    periods.forEach(p => {
        const td = document.createElement('td');
        const val = powers[p];
        td.textContent = (val !== undefined && val !== null) ? `${val} kW` : '-';
        powerBody.appendChild(td);
    });

    // 3. Technical Data Grid
    const techGrid = document.getElementById('technical-grid');
    techGrid.innerHTML = '';
    const techData = data.datos_tecnicos || {};

    const techFields = {
        'tension_suministro': 'Tensión',
        'modo_control_potencia': 'Control Potencia',
        'telegestionado': 'Telegestión',
        'tipo_punto_medida': 'Punto Medida',
        'derechos_acceso_kW': 'Derechos Acceso',
        'derechos_extension_kW': 'Derechos Extensión'
    };

    for (const [key, label] of Object.entries(techFields)) {
        let val = techData[key];
        if (val) {
            const item = document.createElement('div');
            item.className = 'info-item';
            item.innerHTML = `<div class="info-label">${label}</div><div class="info-value">${val}</div>`;
            techGrid.appendChild(item);
        }
    }

    // 4. Annual Consumption
    const totalCons = data.consumo_anual_total || (data.total_consumos ? data.total_consumos.consumo_anual_kWh : 0);
    setText('res-total-consumption', formatNumber(totalCons));

    // Chart
    renderChart(data.consumos_anuales_periodo || {});

    // 5. Consumption Chart (replacing Table)
    renderHistoryChart(data.consumos || []);
}

function renderHistoryChart(consumos) {
    const ctx = document.getElementById('historyChart').getContext('2d');

    if (historyChartInstance) {
        historyChartInstance.destroy();
    }

    // Sort by Date ASC for chart
    consumos.sort((a, b) => parseDate(a.fecha) - parseDate(b.fecha));

    const labels = consumos.map(c => {
        const date = parseDate(c.fecha);
        if (!date || isNaN(date)) return c.fecha; // Fallback

        try {
            return new Intl.DateTimeFormat('es-ES', { month: 'short', year: '2-digit' }).format(date);
        } catch (e) {
            return c.fecha;
        }
    });

    const values = consumos.map(c => c.consumo);

    // Gradient
    const gradient = ctx.createLinearGradient(0, 0, 0, 400);
    gradient.addColorStop(0, 'rgba(0, 113, 227, 0.5)');
    gradient.addColorStop(1, 'rgba(0, 113, 227, 0.0)');

    historyChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Consumo (kWh)',
                data: values,
                backgroundColor: gradient,
                borderColor: '#0071e3',
                borderWidth: 2,
                pointBackgroundColor: '#fff',
                pointBorderColor: '#0071e3',
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function (context) {
                            return `Consumo: ${formatNumber(context.raw)} kWh`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { borderDash: [2, 2] }
                },
                x: {
                    grid: { display: false }
                }
            }
        }
    });
}

function renderChart(periodData) {
    const ctx = document.getElementById('consumptionChart').getContext('2d');

    if (chartInstance) {
        chartInstance.destroy();
    }

    const updateLabels = Object.keys(periodData).map(k => k.replace('periodo_', 'P').toUpperCase());
    const dataValues = Object.values(periodData);

    chartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: updateLabels,
            datasets: [{
                data: dataValues,
                backgroundColor: [
                    '#FF6384',
                    '#36A2EB',
                    '#FFCE56',
                    '#4BC0C0',
                    '#9966FF',
                    '#FF9F40'
                ]
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'right' }
            }
        }
    });
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value || "-";
}

function formatNumber(num) {
    if (num === undefined || num === null) return "-";
    return new Intl.NumberFormat('es-ES', { maximumFractionDigits: 2 }).format(num);
}

function parseDate(dateStr) {
    if (!dateStr) return null;

    // Check if YYYY-MM-DD (ISO)
    if (/^\d{4}-\d{2}-\d{2}/.test(dateStr)) {
        return new Date(dateStr);
    }

    // Check if DD/MM/YYYY
    if (/^\d{2}\/\d{2}\/\d{4}/.test(dateStr)) {
        const parts = dateStr.split('/');
        // Month is 0-indexed in Date(y, m, d) but 1-indexed in string for new Date("Y-M-D")
        // Safer to use new Date(y, m-1, d)
        return new Date(parts[2], parts[1] - 1, parts[0]);
    }

    // Fallback try common parsing
    const d = new Date(dateStr);
    return isNaN(d) ? null : d;
}
