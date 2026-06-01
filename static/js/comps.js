// SGOS — Comps: expandir/colapsar filas de detalle en las tablas Histórico/Entrega.
// Al pulsar una fila "grupo" (categoría o jugador) se muestran u ocultan sus
// filas de detalle asociadas (data-de == data-grupo).
(function () {
  "use strict";

  function toggleGrupo(fila) {
    const grupo = fila.getAttribute("data-grupo");
    if (!grupo) return;
    const abierta = fila.classList.toggle("abierta");
    const detalles = document.querySelectorAll(
      '.fila-detalle[data-de="' + grupo + '"]'
    );
    detalles.forEach((d) => {
      d.hidden = !abierta;
    });
  }

  document.querySelectorAll(".tabla-detalle .fila-grupo").forEach((fila) => {
    fila.addEventListener("click", function () {
      toggleGrupo(fila);
    });
  });
})();
