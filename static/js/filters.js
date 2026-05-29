// SGOS — Home / Resumen: panel de filtros retráctil
(function () {
  "use strict";

  const layout = document.getElementById("dashboard-layout");
  const toggleBtn = document.getElementById("btn-toggle-filtros");
  const todosBtn = document.getElementById("btn-todos");
  const ningunoBtn = document.getElementById("btn-ninguno");
  const form = document.getElementById("filters-form");

  if (toggleBtn && layout) {
    toggleBtn.addEventListener("click", function () {
      const collapsed = layout.classList.toggle("filters-collapsed");
      toggleBtn.setAttribute("aria-expanded", String(!collapsed));
    });
  }

  // "Todos": limpia filtros y recarga mostrando todos los datos.
  if (todosBtn && form) {
    todosBtn.addEventListener("click", function () {
      window.location.href = form.getAttribute("action");
    });
  }

  // "Ninguno": vacía los campos del formulario sin recargar.
  if (ningunoBtn && form) {
    ningunoBtn.addEventListener("click", function () {
      form.reset();
      form.querySelectorAll("select").forEach((s) => (s.value = ""));
      form.querySelectorAll('input[type="text"]').forEach((i) => (i.value = ""));
    });
  }
})();
