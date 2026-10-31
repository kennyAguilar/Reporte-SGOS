// SGOS — Configuración: buscador en tablas, confirmaciones y switches.
// Sin dependencias. Se apoya en atributos data-* del template:
//   - input[data-buscar="#tabla"]        filtra filas por texto
//   - [data-contador="#tabla"]           muestra "N de M" al filtrar
//   - form[data-confirmar="..."]         pide confirmación antes de enviar
//   - form[data-confirmar-off="..."]     solo confirma cuando el switch se APAGA
//   - form .switch input[type=checkbox]  envía el formulario al cambiar
(function () {
  "use strict";

  // --- Buscador por tabla -------------------------------------------------
  document.querySelectorAll("input[data-buscar]").forEach(function (input) {
    const tabla = document.querySelector(input.dataset.buscar);
    if (!tabla || !tabla.tBodies[0]) return;
    const filas = Array.from(tabla.tBodies[0].rows);
    const contador = document.querySelector('[data-contador="' + input.dataset.buscar + '"]');
    const textoBase = contador ? contador.textContent : "";

    input.addEventListener("input", function () {
      const termino = input.value.trim().toLowerCase();
      let visibles = 0;
      filas.forEach(function (fila) {
        const coincide = !termino || fila.textContent.toLowerCase().includes(termino);
        fila.hidden = !coincide;
        if (coincide) visibles++;
      });
      if (contador) {
        contador.textContent = termino ? visibles + " de " + filas.length : textoBase;
      }
    });
  });

  // --- Confirmaciones -----------------------------------------------------
  document.querySelectorAll("form[data-confirmar]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!window.confirm(form.dataset.confirmar)) e.preventDefault();
    });
  });

  // --- Switches: enviar al cambiar; confirmar solo al apagar ---------------
  document.querySelectorAll("form .switch input[type=checkbox]").forEach(function (chk) {
    chk.addEventListener("change", function () {
      const form = chk.form;
      if (!form) return;
      const apagando = !chk.checked;
      const mensaje = form.dataset.confirmarOff;
      if (apagando && mensaje && !window.confirm(mensaje)) {
        chk.checked = true; // revierte el switch visualmente
        return;
      }
      form.submit();
    });
  });
})();
