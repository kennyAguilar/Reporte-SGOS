// SGOS — Dashboard de Getnet: gráficos con Chart.js + escala del mapa de calor.
// Los datos llegan embebidos en un <script id="getnet-data" type="application/json">
// que genera el template. Aquí solo los leemos y dibujamos.
(function () {
  "use strict";

  // Paleta consistente con DESIGN.md (Carbon dark + oro).
  const ORO = "#d4af37";
  const VERDE = "#24a148";
  const AZUL = "#78a9ff";
  const NARANJA = "#ff832b";
  const GRID = "rgba(255, 255, 255, 0.06)";
  const TEXTO = "#8d8d8d";

  const dataEl = document.getElementById("getnet-data");
  if (!dataEl || typeof Chart === "undefined") {
    return;
  }

  let datos;
  try {
    datos = JSON.parse(dataEl.textContent);
  } catch (e) {
    return;
  }

  // Opciones base compartidas por todos los gráficos.
  function opcionesBase(formatoY) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: TEXTO, boxWidth: 12 } },
        tooltip: {
          callbacks: formatoY
            ? { label: (ctx) => formatoY(ctx.parsed.y) }
            : {},
        },
      },
      scales: {
        x: { ticks: { color: TEXTO }, grid: { color: GRID } },
        y: {
          ticks: { color: TEXTO, callback: (v) => (formatoY ? formatoY(v) : v) },
          grid: { color: GRID },
          beginAtZero: true,
        },
      },
    };
  }

  // Formatea montos al estilo chileno: 1234567 -> "$1.234.567".
  function pesos(n) {
    return "$" + Math.round(n).toLocaleString("es-CL");
  }

  function crearBarras(id, labels, valores, color, label, formatoY) {
    const el = document.getElementById(id);
    if (!el) return;
    const previo = Chart.getChart(el);
    if (previo) previo.destroy();
    new Chart(el, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          {
            label: label,
            data: valores,
            backgroundColor: color,
            borderRadius: 2,
            maxBarThickness: 28,
          },
        ],
      },
      options: opcionesBase(formatoY),
    });
  }

  function crearArea(id, labels, valores, color, label, formatoY) {
    const el = document.getElementById(id);
    if (!el) return;
    const previo = Chart.getChart(el);
    if (previo) previo.destroy();
    new Chart(el, {
      type: "line",
      data: {
        labels: labels,
        datasets: [
          {
            label: label,
            data: valores,
            borderColor: color,
            backgroundColor: color + "33", // relleno translúcido
            fill: true,
            tension: 0.3,
            pointRadius: 2,
            pointBackgroundColor: color,
          },
        ],
      },
      options: opcionesBase(formatoY),
    });
  }

  // Donut (arandela) de distribución por forma de pago.
  function crearDonut(id, formas) {
    const el = document.getElementById(id);
    if (!el || !formas || !formas.length) return;
    const previo = Chart.getChart(el);
    if (previo) previo.destroy();
    new Chart(el, {
      type: "doughnut",
      data: {
        labels: formas.map((f) => f.label),
        datasets: [
          {
            data: formas.map((f) => f.ops),
            backgroundColor: formas.map((f) => f.color),
            borderColor: "#161616",
            borderWidth: 2,
            hoverOffset: 6,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "62%",
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const f = formas[ctx.dataIndex];
                return `${f.label}: ${f.ops.toLocaleString("es-CL")} ops (${f.pct}%) · ${pesos(f.monto)}`;
              },
            },
          },
        },
      },
    });
  }

  // --- Operaciones por Mes (barras oro) ---
  if (datos.ops_mes) {    crearBarras(
      "chart-ops-mes",
      datos.ops_mes.labels,
      datos.ops_mes.valores,
      ORO,
      "Operaciones"
    );
  }

  // --- Montos por Mes (área verde) ---
  if (datos.montos_mes) {
    crearArea(
      "chart-montos-mes",
      datos.montos_mes.labels,
      datos.montos_mes.valores,
      VERDE,
      "Monto Total",
      pesos
    );
  }

  // --- Operaciones por Hora promedio (barras azul) ---
  if (datos.promedio_hora) {
    crearBarras(
      "chart-ops-hora",
      datos.promedio_hora.labels,
      datos.promedio_hora.operaciones,
      AZUL,
      "Promedio Operaciones"
    );

    // --- Montos por Hora promedio (área naranja) ---
    crearArea(
      "chart-montos-hora",
      datos.promedio_hora.labels,
      datos.promedio_hora.montos,
      NARANJA,
      "Promedio Monto ($)",
      pesos
    );
  }

  // --- Donut por forma de pago (débito / crédito) ---
  if (datos.formas) {
    crearDonut("chart-formas", datos.formas);
  }

  // --- Escala de color del mapa de calor ---
  // Cada celda recibe un fondo oro con opacidad proporcional a su valor
  // respecto al máximo de la tabla. Así las franjas activas resaltan.
  const celdas = document.querySelectorAll(".heatmap td.hcell");
  let maximo = 0;
  celdas.forEach((c) => {
    const v = parseFloat(c.getAttribute("data-valor")) || 0;
    if (v > maximo) maximo = v;
  });
  if (maximo > 0) {
    celdas.forEach((c) => {
      const v = parseFloat(c.getAttribute("data-valor")) || 0;
      const intensidad = v / maximo; // 0..1
      // Fondo oro translúcido; las celdas en 0 quedan casi sin color.
      c.style.backgroundColor = "rgba(212, 175, 55, " + (intensidad * 0.85).toFixed(3) + ")";
      if (intensidad > 0.55) {
        c.style.color = "#161616"; // texto oscuro sobre oro intenso
      }
      if (v === 0) {
        c.style.color = "#525252";
      }
    });
  }
})();
