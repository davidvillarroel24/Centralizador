// Corre solo en las paginas de Centralizador (ver "matches" en manifest.json), nunca en
// Moodle. Agrega un boton junto a cada <textarea name="moodle_cookie"> que ya existe en
// dashboard.html/session_recovery.html - no reemplaza el pegado manual, solo lo completa:
// el usuario sigue pudiendo editar/borrar el valor y tiene que click "Guardar cookie" el
// mismo de siempre para que se mande al servidor.
(function () {
  "use strict";

  function crearBoton() {
    const boton = document.createElement("button");
    boton.type = "button";
    boton.textContent = "⚡ Capturar cookie de Moodle automáticamente";
    boton.className = "btn btn-secondary";
    boton.style.marginTop = "8px";
    boton.style.width = "auto";
    boton.style.padding = "8px 14px";
    return boton;
  }

  function crearEstado() {
    const estado = document.createElement("p");
    estado.className = "note";
    estado.style.marginTop = "6px";
    estado.style.minHeight = "1.2em";
    return estado;
  }

  function engancharTextarea(textarea) {
    if (textarea.dataset.centralizadorExtEnganchado) return;
    textarea.dataset.centralizadorExtEnganchado = "1";

    const boton = crearBoton();
    const estado = crearEstado();
    textarea.insertAdjacentElement("afterend", estado);
    estado.insertAdjacentElement("afterend", boton);

    boton.addEventListener("click", function () {
      boton.disabled = true;
      estado.textContent = "Buscando tu sesión de Moodle...";
      estado.style.color = "";

      chrome.runtime.sendMessage({ action: "getMoodleCookie" }, function (respuesta) {
        boton.disabled = false;

        if (chrome.runtime.lastError) {
          estado.textContent = "No se pudo conectar con la extensión. Pegá la cookie a mano.";
          estado.style.color = "#ff8080";
          return;
        }
        if (!respuesta || !respuesta.ok) {
          estado.textContent = (respuesta && respuesta.error) || "No se encontró la cookie.";
          estado.style.color = "#ff8080";
          return;
        }

        textarea.value = respuesta.value;
        // Dispara 'input' para que cualquier listener de la pagina (validacion, etc.)
        // se entere del cambio, igual que si el usuario hubiera tipeado/pegado a mano.
        textarea.dispatchEvent(new Event("input", { bubbles: true }));

        estado.textContent = "Cookie capturada. Revisá y hacé clic en \"Guardar cookie\" para confirmar.";
        estado.style.color = "#8ce38c";
      });
    });
  }

  function buscarYEnganchar() {
    document.querySelectorAll('textarea[name="moodle_cookie"]').forEach(engancharTextarea);
  }

  buscarYEnganchar();

  // dashboard.html abre/cierra el formulario de "Reemplazar cookie" dentro de un <details>,
  // asi que el textarea puede aparecer despues de la carga inicial de la pagina.
  const observer = new MutationObserver(buscarYEnganchar);
  observer.observe(document.body, { childList: true, subtree: true });
})();
