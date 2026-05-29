// SGOS — Login: mostrar/ocultar contraseña
(function () {
  const input = document.getElementById("password");
  const toggle = document.getElementById("togglePassword");
  if (!input || !toggle) return;

  toggle.addEventListener("click", function () {
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    toggle.classList.toggle("show-password", show);
    toggle.setAttribute("aria-pressed", show ? "true" : "false");
    const label = show ? "Ocultar contraseña" : "Mostrar contraseña";
    toggle.setAttribute("aria-label", label);
    toggle.setAttribute("title", label);
    input.focus();
  });
})();
