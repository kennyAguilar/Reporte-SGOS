// SGOS — Tablas ordenables y con búsqueda rápida.
// Se aplica a cualquier <table class="record-table sortable-table">.
// Ordena solo el <tbody> (respeta el <tfoot> de totales) y filtra por texto
// sobre las filas visibles, sin recargar la página ni tocar el servidor.
(function () {
  "use strict";

  // Convierte el texto de una celda a número comparable.
  // "$13.262.650.138" -> 13262650138 ; "1.484" -> 1484 ; "12,5%" -> 12.5
  function aNumero(texto) {
    const limpio = texto.replace(/[^\d,-]/g, "").replace(",", ".");
    if (!limpio || limpio === "-") return null;
    const n = parseFloat(limpio);
    return isNaN(n) ? null : n;
  }

  // Una columna es numérica si TODAS sus celdas con contenido lo son.
  function columnaEsNumerica(filas, indice) {
    let conDatos = 0;
    for (const fila of filas) {
      const celda = fila.cells[indice];
      if (!celda) continue;
      const texto = celda.textContent.trim();
      if (!texto) continue;
      conDatos++;
      if (aNumero(texto) === null) return false;
    }
    return conDatos > 0;
  }

  function ordenar(tabla, indice, ascendente) {
    const cuerpo = tabla.tBodies[0];
    if (!cuerpo) return;
    const filas = Array.from(cuerpo.rows);
    const numerica = columnaEsNumerica(filas, indice);

    filas.sort(function (a, b) {
      const ta = (a.cells[indice] ? a.cells[indice].textContent : "").trim();
      const tb = (b.cells[indice] ? b.cells[indice].textContent : "").trim();

      let resultado;
      if (numerica) {
        const na = aNumero(ta);
        const nb = aNumero(tb);
        // Las celdas vacías quedan siempre al final.
        if (na === null && nb === null) resultado = 0;
        else if (na === null) return 1;
        else if (nb === null) return -1;
        else resultado = na - nb;
      } else {
        resultado = ta.localeCompare(tb, "es", { sensitivity: "base" });
      }
      return ascendente ? resultado : -resultado;
    });

    filas.forEach((f) => cuerpo.appendChild(f));
    renumerarRanking(cuerpo);
  }

  // Si la tabla tiene columna de ranking (#), se renumera tras ordenar para que
  // no quede mostrando la posición del orden anterior.
  function renumerarRanking(cuerpo) {
    let posicion = 0;
    Array.from(cuerpo.rows).forEach(function (fila) {
      const celda = fila.querySelector("td.rank");
      if (celda) {
        posicion++;
        celda.textContent = posicion;
      }
    });
  }

  function prepararOrden(tabla) {
    const encabezados = tabla.tHead ? tabla.tHead.rows[0] : null;
    if (!encabezados) return;

    Array.from(encabezados.cells).forEach(function (th, indice) {
      th.classList.add("th-sortable");
      th.setAttribute("role", "button");
      th.setAttribute("tabindex", "0");
      th.title = "Ordenar por " + th.textContent.trim();

      function alOrdenar() {
        const yaAscendente = th.classList.contains("sorted-asc");
        Array.from(encabezados.cells).forEach((otro) =>
          otro.classList.remove("sorted-asc", "sorted-desc")
        );
        const ascendente = !yaAscendente;
        th.classList.add(ascendente ? "sorted-asc" : "sorted-desc");
        ordenar(tabla, indice, ascendente);
      }

      th.addEventListener("click", alOrdenar);
      th.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          alOrdenar();
        }
      });
    });
  }

  function prepararBusqueda(tabla) {
    const cuerpo = tabla.tBodies[0];
    if (!cuerpo) return;

    const barra = document.createElement("div");
    barra.className = "table-search";

    const input = document.createElement("input");
    input.type = "search";
    input.placeholder = "Buscar en la tabla...";
    input.setAttribute("aria-label", "Buscar en la tabla");

    const contador = document.createElement("span");
    contador.className = "table-search-count";

    barra.appendChild(input);
    barra.appendChild(contador);

    // La barra va justo antes del contenedor con scroll de la tabla.
    const contenedor = tabla.closest(".heatmap-scroll") || tabla;
    contenedor.parentNode.insertBefore(barra, contenedor);

    const total = cuerpo.rows.length;

    function actualizarContador(visibles) {
      contador.textContent =
        visibles === total ? total + " filas" : visibles + " de " + total + " filas";
    }

    input.addEventListener("input", function () {
      const termino = input.value.trim().toLowerCase();
      let visibles = 0;
      Array.from(cuerpo.rows).forEach(function (fila) {
        const coincide = !termino || fila.textContent.toLowerCase().includes(termino);
        fila.hidden = !coincide;
        if (coincide) visibles++;
      });
      actualizarContador(visibles);
    });

    actualizarContador(total);
  }

  document.querySelectorAll("table.sortable-table").forEach(function (tabla) {
    prepararOrden(tabla);
    if (tabla.hasAttribute("data-buscador")) {
      prepararBusqueda(tabla);
    }
  });
})();
