// Corre solo en las paginas de Centralizador (ver "matches" en manifest.json), nunca en
// Moodle. Ya no inserta ningun campo de texto ni boton propio: la pagina (dashboard.html)
// tiene su propio boton "Extraer cookie de Moodle" y dispara el evento
// 'centralizador-pedir-cookie' al hacer click. Este content script escucha ese evento,
// pide la cookie via el background (API chrome.cookies, requiere el permiso "cookies") y
// devuelve el resultado con 'centralizador-cookie-capturada' - la pagina es quien decide
// que hacer con eso (mostrar el SweetAlert2 de confirmar/cancelar, guardar, etc.), porque
// un content script corre en un mundo de JS aislado y no puede llamar funciones de la
// pagina (como window.Swal) directamente.
(function () {
  "use strict";

  document.addEventListener("centralizador-pedir-cookie", function () {
    chrome.runtime.sendMessage({ action: "getMoodleCookie" }, function (respuesta) {
      if (chrome.runtime.lastError) {
        document.dispatchEvent(new CustomEvent("centralizador-cookie-capturada", {
          detail: { ok: false, error: "No se pudo conectar con la extensión." },
        }));
        return;
      }
      if (!respuesta || !respuesta.ok) {
        document.dispatchEvent(new CustomEvent("centralizador-cookie-capturada", {
          detail: { ok: false, error: (respuesta && respuesta.error) || "No se encontró la cookie." },
        }));
        return;
      }
      document.dispatchEvent(new CustomEvent("centralizador-cookie-capturada", {
        detail: { ok: true, value: respuesta.value },
      }));
    });
  });
})();
