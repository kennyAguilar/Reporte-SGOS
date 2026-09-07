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
  if (typeof Chart === "undefined") {
    return;
  }

  let datos = null;
  if (dataEl) {
    try {
      datos = JSON.parse(dataEl.textContent);
    } catch (e) {
      datos = null;
    }
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
  if (datos && datos.ops_mes) {    crearBarras(
      "chart-ops-mes",
      datos.ops_mes.labels,
      datos.ops_mes.valores,
      ORO,
      "Operaciones"
    );
  }

  // --- Montos por Mes (área verde) ---
  if (datos && datos.montos_mes) {
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
  if (datos && datos.promedio_hora) {
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
  if (datos && datos.formas) {
    crearDonut("chart-formas", datos.formas);
  }

  // --- Distribución por tipo de pago (Premios · Record, barras oro) ---
  if (datos && datos.tipos) {
    crearBarras(
      "chart-tipos",
      datos.tipos.labels,
      datos.tipos.valores,
      ORO,
      "Transacciones"
    );
  }

  // ===================================================================
  // Dashboard de Comps. Datos embebidos en <script id="comps-data">.
  // Reutiliza las mismas funciones de gráficos; el donut usa `valor`.
  // ===================================================================
  function crearBarrasH(id, labels, valores, color, label) {
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
            maxBarThickness: 22,
          },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: TEXTO, boxWidth: 12 } } },
        scales: {
          x: { ticks: { color: TEXTO }, grid: { color: GRID }, beginAtZero: true },
          y: { ticks: { color: TEXTO }, grid: { color: GRID } },
        },
      },
    });
  }

  // Donut a partir de categorías {label, valor, pct, color}.
  function crearDonutCat(id, formas) {
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
            data: formas.map((f) => f.valor),
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
                return `${f.label}: ${f.valor.toLocaleString("es-CL")} (${f.pct}%)`;
              },
            },
          },
        },
      },
    });
  }

  const compsEl = document.getElementById("comps-data");
  if (compsEl) {
    let comps = null;
    try {
      comps = JSON.parse(compsEl.textContent);
    } catch (e) {
      comps = null;
    }

    if (comps) {
      // Cortesías por mes (barras oro).
      if (comps.cortesias_mes) {
        crearBarras(
          "chart-comps-mes",
          comps.cortesias_mes.labels,
          comps.cortesias_mes.valores,
          ORO,
          "Cortesías"
        );
      }

      // Micros por mes (área verde).
      if (comps.montos_mes) {
        crearArea(
          "chart-comps-montos-mes",
          comps.montos_mes.labels,
          comps.montos_mes.valores,
          VERDE,
          "Micros"
        );
      }

      // Promedio por día de la semana (cortesías azul, micros naranja).
      if (comps.dia_semana) {
        crearBarras(
          "chart-comps-dia",
          comps.dia_semana.labels,
          comps.dia_semana.cortesias,
          AZUL,
          "Promedio Cortesías"
        );
        crearArea(
          "chart-comps-montos-dia",
          comps.dia_semana.labels,
          comps.dia_semana.montos,
          NARANJA,
          "Promedio Micros"
        );
      }

      // Top productos (barras horizontales oro).
      if (comps.top_productos) {
        crearBarrasH(
          "chart-comps-productos",
          comps.top_productos.labels,
          comps.top_productos.valores,
          ORO,
          "Cortesías"
        );
      }

      // Distribución por categoría (donut).
      if (comps.categorias) {
        crearDonutCat("chart-comps-categorias", comps.categorias);
      }
    }
  }

  // ===================================================================
  // Dashboard de Coin In (MDA / MDJ). Datos en <script id="coinin-data">.
  // Los niveles traen {label, coin_in, jugadores, pct, color}.
  // ===================================================================
  const coininEl = document.getElementById("coinin-data");
  if (coininEl) {
    let coinin = null;
    try {
      coinin = JSON.parse(coininEl.textContent);
    } catch (e) {
      coinin = null;
    }

    if (coinin) {
      // Coin In por mes (área verde).
      if (coinin.coin_in_mes) {
        crearArea(
          "chart-coinin-mes",
          coinin.coin_in_mes.labels,
          coinin.coin_in_mes.valores,
          VERDE,
          "Coin In",
          pesos
        );
      }

      // Jugadores únicos por mes (barras oro).
      if (coinin.jugadores_mes) {
        crearBarras(
          "chart-coinin-jugadores",
          coinin.jugadores_mes.labels,
          coinin.jugadores_mes.valores,
          ORO,
          "Jugadores"
        );
      }

      // Coin In por Player Level (donut).
      if (coinin.niveles && coinin.niveles.length) {
        const niveles = coinin.niveles.map((n) => ({
          label: n.label,
          valor: n.coin_in,
          pct: n.pct,
          color: n.color,
        }));
        crearDonutCat("chart-coinin-niveles", niveles);
      }
    }
  }

  // ===================================================================
  // Dashboard de Coin In Cero. Datos en <script id="coinin-cero-data">.
  // casos_mes trae {labels, casos, montos}; areas trae {label, monto, pct, color}.
  // ===================================================================
  const ceroEl = document.getElementById("coinin-cero-data");
  if (ceroEl) {
    let cero = null;
    try {
      cero = JSON.parse(ceroEl.textContent);
    } catch (e) {
      cero = null;
    }

    if (cero) {
      if (cero.casos_mes) {
        crearBarras(
          "chart-cero-casos",
          cero.casos_mes.labels,
          cero.casos_mes.casos,
          NARANJA,
          "Casos sin juego"
        );
        crearArea(
          "chart-cero-montos",
          cero.casos_mes.labels,
          cero.casos_mes.montos,
          ORO,
          "Cortesías",
          pesos
        );
      }

      if (cero.areas && cero.areas.length) {
        const areas = cero.areas.map((a) => ({
          label: a.label,
          valor: a.monto,
          pct: a.pct,
          color: a.color,
        }));
        crearDonutCat("chart-cero-areas", areas);
      }
    }
  }

  // ===================================================================
  // Análisis general (Comps vs Coin In por área). Datos en
  // <script id="analisis-data">. comparativa trae {labels, coin_in, comps,
  // teorico, ratio, ratio_teorico}; categorias y top_productos usan el formato
  // ya conocido.
  // ===================================================================
  const analisisEl = document.getElementById("analisis-data");
  if (analisisEl) {
    let analisis = null;
    try {
      analisis = JSON.parse(analisisEl.textContent);
    } catch (e) {
      analisis = null;
    }

    if (analisis) {
      // Coin In (barras) vs Cortesías (línea) con dos ejes: los montos son de
      // órdenes de magnitud muy distintos y con un solo eje la línea quedaría
      // pegada al piso.
      if (analisis.comparativa) {
        const el = document.getElementById("chart-analisis-comparativa");
        if (el) {
          const previo = Chart.getChart(el);
          if (previo) previo.destroy();
          new Chart(el, {
            data: {
              labels: analisis.comparativa.labels,
              datasets: [
                {
                  type: "bar",
                  label: "Coin In",
                  data: analisis.comparativa.coin_in,
                  backgroundColor: VERDE,
                  borderRadius: 2,
                  maxBarThickness: 28,
                  yAxisID: "y",
                },
                {
                  type: "line",
                  label: "Cortesías",
                  data: analisis.comparativa.comps,
                  borderColor: ORO,
                  backgroundColor: ORO + "33",
                  tension: 0.3,
                  pointRadius: 2,
                  pointBackgroundColor: ORO,
                  yAxisID: "y1",
                },
              ],
            },
            options: {
              responsive: true,
              maintainAspectRatio: false,
              plugins: {
                legend: { labels: { color: TEXTO, boxWidth: 12 } },
                tooltip: {
                  callbacks: { label: (ctx) => ctx.dataset.label + ": " + pesos(ctx.parsed.y) },
                },
              },
              scales: {
                x: { ticks: { color: TEXTO }, grid: { color: GRID } },
                y: {
                  position: "left",
                  ticks: { color: TEXTO, callback: (v) => pesos(v) },
                  grid: { color: GRID },
                  beginAtZero: true,
                },
                y1: {
                  position: "right",
                  ticks: { color: TEXTO, callback: (v) => pesos(v) },
                  grid: { display: false },
                  beginAtZero: true,
                },
              },
            },
          });
        }

        // Ratio contra la ganancia teórica (Coin In x 0,065). Si el JSON viene
        // de una versión anterior sin ratio_teorico, se cae al ratio bruto.
        crearArea(
          "chart-analisis-ratio",
          analisis.comparativa.labels,
          analisis.comparativa.ratio_teorico || analisis.comparativa.ratio,
          NARANJA,
          "Cortesías sobre ganancia teórica",
          (v) => v + "%"
        );
      }

      // Productos más entregados (barras horizontales oro).
      if (analisis.top_productos) {
        crearBarrasH(
          "chart-analisis-productos",
          analisis.top_productos.labels,
          analisis.top_productos.valores,
          ORO,
          "Entregas"
        );
      }

      // Gasto por categoría (donut).
      if (analisis.categorias && analisis.categorias.length) {
        crearDonutCat("chart-analisis-categorias", analisis.categorias);
      }
    }
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
