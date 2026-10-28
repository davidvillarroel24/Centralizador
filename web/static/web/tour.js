// Guía de uso: globos que resaltan cada parte de Configuración (pasos 1-4) y de
// Extracción (pasos 5-10). Usa Driver.js (cargado en base.html). La página dice si arranca
// y en qué tramo a través de <script id="tourConfig"> (ver views.contexto_tour):
//   - Configuración la arranca sola mientras el usuario no la haya visto, o con ?tour=1
//     (ítem "Guía de uso" del menú).
//   - El paso 4 lleva a Extracción con ?tour=extraccion, donde sigue en el paso 5.
// Al terminarla o cerrarla en cualquier paso se marca como vista (no vuelve a salir sola).
(function () {
  var TOTAL = 10;
  // Si el usuario guarda la configuración en medio de la guía, la página se recarga: se
  // anota en qué paso iba para retomarla ahí.
  var CLAVE_RETOMAR = 'centralizador-guia-retomar';

  var PASOS_CONFIGURACION = [
    {
      titulo: 'Bienvenida',
      texto: 'Te mostramos en 10 pasos cómo dejar listo el Centralizador y cómo extraer tus ' +
        'datos de Moodle. Podés cerrar la guía cuando quieras y repetirla desde ' +
        '<strong>Guía de uso</strong> en el menú.',
    },
    {
      elemento: '#fechas',
      titulo: 'Fechas de tus parciales',
      texto: '<strong>No son fechas de Moodle.</strong> Indicá cuándo empieza y termina cada ' +
        'parcial; esto será para todas tus materias. Cada tarea que extraigas cae en el ' +
        'parcial que contiene su fecha de cierre. Completá al menos uno.',
    },
    {
      elemento: '#pesos',
      titulo: 'Pesos por categoría',
      texto: 'Cuánto vale cada tipo de tarea dentro del parcial. La categoría se detecta por ' +
        'el título (Mi-Tek, E-Tek, Design Lab, Examen; el resto cuenta como Training). Lo ' +
        'ideal es que sumen 100 %. Después pulsá <strong>Guardar configuración</strong>.',
    },
    {
      elemento: '#extension',
      titulo: 'Extensión de Chrome',
      texto: 'Descargala e instalala con estos pasos (una sola vez): con ella capturás tu ' +
        'cookie de Moodle con un clic, sin copiarla a mano. Ahora vamos a la pantalla de ' +
        'Extracción.',
      siguiente: 'Ir a Extracción →',
      irA: 'url_extraccion',
    },
  ];

  var PASOS_EXTRACCION = [
    {
      elemento: '#preparacion',
      titulo: 'Antes de extraer',
      texto: 'Esta lista te dice qué falta. Lo que tiene ✓ ya está listo; si algo quedó ' +
        'pendiente, el enlace te lleva a resolverlo.',
    },
    {
      elemento: '#cookie',
      titulo: 'Capturá tu cookie de Moodle',
      texto: 'Iniciá sesión en Moodle en otra pestaña y pulsá <strong>Extraer cookie de ' +
        'Moodle</strong>. Se guarda cifrada y dura 2 horas; mientras no la tengas, los ' +
        'botones 1 a 4 quedan bloqueados.',
    },
    {
      elemento: '.courses-panel',
      titulo: 'Elegí un curso',
      texto: 'Tildá el curso con el que vas a trabajar. Los botones que leen Moodle (1 a 4) ' +
        'trabajan con un curso por vez.',
    },
    {
      elemento: '.actions-grid',
      titulo: 'El orden de los botones',
      texto: '<ol class="guia-lista">' +
        '<li><strong>Tareas</strong>: extrae, asigna a su parcial e importa. Empezá siempre por acá.</li>' +
        '<li><strong>Detalle</strong> (opcional): descripción y archivos de cada tarea.</li>' +
        '<li><strong>Estudiantes</strong>: entregas y notas de cada estudiante.</li>' +
        '<li><strong>Último acceso</strong>: todos los inscritos y su última conexión.</li>' +
        '<li><strong>Excel</strong>: genera el reporte; acepta varios cursos a la vez.</li>' +
        '</ol>',
    },
    {
      elemento: 'button[value="ver_asignacion"]',
      titulo: 'Revisar asignación',
      texto: 'Si una tarea quedó en la categoría o el parcial equivocado, corregila acá. El ' +
        'cambio se guarda directo en la base.',
    },
    {
      titulo: '¡Listo!',
      texto: 'Ya sabés cómo extraer tus datos. Podés repetir esta guía cuando quieras desde ' +
        '<strong>Guía de uso</strong> en el menú.',
    },
  ];

  function leerConfig() {
    var nodo = document.getElementById('tourConfig');
    if (!nodo) return null;
    try { return JSON.parse(nodo.textContent); } catch (e) { return null; }
  }

  function csrfToken() {
    return (document.cookie.match(/csrftoken=([^;]+)/) || [])[1];
  }

  function marcarVista(config) {
    fetch(config.url_visto, {
      method: 'POST',
      headers: { 'X-CSRFToken': csrfToken(), 'X-Requested-With': 'XMLHttpRequest' },
    }).catch(function () {});
  }

  // Quita ?tour=... de la barra de direcciones: recargar la página no reinicia la guía.
  function limpiarUrl() {
    var url = new URL(window.location.href);
    if (!url.searchParams.has('tour')) return;
    url.searchParams.delete('tour');
    window.history.replaceState(null, '', url.pathname + url.search + url.hash);
  }

  // Formulario de fechas y pesos de Configuración (no existe en otras páginas).
  function formularioConfig() {
    var fechas = document.getElementById('fechas');
    return fechas ? fechas.closest('form') : null;
  }

  function formularioConCambios() {
    var form = formularioConfig();
    return form && form.dataset.guiaCambios === '1' ? form : null;
  }

  function iniciar(config, pasos, primerNumero, indiceInicial) {
    var navegando = false;
    var driverObj;

    var steps = pasos.map(function (paso, i) {
      var numero = primerNumero + i;
      var popover = {
        title: numero + '/' + TOTAL + ' · ' + paso.titulo,
        description: paso.texto,
      };
      if (paso.siguiente) popover.nextBtnText = paso.siguiente;
      // Primer paso de cada página (1 y 5): no hay "anterior" al que volver.
      if (i === 0) popover.showButtons = ['next', 'close'];
      if (paso.irA) {
        popover.onNextClick = function () {
          var form = formularioConCambios();
          if (form) {
            // Cambios sin guardar en fechas/pesos: se guardan y la guía sigue en este paso.
            try { sessionStorage.setItem(CLAVE_RETOMAR, String(i)); } catch (e) {}
            navegando = true;
            form.requestSubmit();
            // Si el navegador frena el envío (ej. una fecha inválida), la página no se va:
            // cerrar la guía después tiene que volver a marcarla como vista.
            setTimeout(function () {
              navegando = false;
              try { sessionStorage.removeItem(CLAVE_RETOMAR); } catch (e) {}
            }, 1500);
            return;
          }
          navegando = true;
          window.location.href = config[paso.irA];
        };
      }
      // Elemento que no está en la página (ej. cuenta sin docente vinculado): globo centrado.
      var el = paso.elemento && document.querySelector(paso.elemento);
      return el ? { element: el, popover: popover } : { popover: popover };
    });

    driverObj = window.driver.js.driver({
      steps: steps,
      popoverClass: 'centralizador-guia',
      nextBtnText: 'Siguiente →',
      prevBtnText: '← Anterior',
      doneBtnText: 'Terminar',
      stagePadding: 8,
      onDestroyed: function () {
        if (!navegando) marcarVista(config);
      },
    });
    limpiarUrl();
    driverObj.drive(indiceInicial || 0);
  }

  document.addEventListener('DOMContentLoaded', function () {
    var config = leerConfig();
    if (!config || !window.driver || !window.driver.js) return;

    var form = formularioConfig();
    if (form) {
      form.addEventListener('input', function () { form.dataset.guiaCambios = '1'; });
    }

    var retomar = null;
    try {
      retomar = sessionStorage.getItem(CLAVE_RETOMAR);
      sessionStorage.removeItem(CLAVE_RETOMAR);
    } catch (e) {}
    // Si el guardado falló, no se retoma: el mensaje de error queda a la vista.
    if (retomar !== null && (!form || document.querySelector('.message.card.error'))) retomar = null;

    if (retomar !== null) {
      // Se acaba de guardar en medio de la guía: el aviso de "guardado" va dentro del globo.
      if (window.Swal && Swal.isVisible()) Swal.close();
      var indice = parseInt(retomar, 10);
      var pasos = PASOS_CONFIGURACION.slice();
      pasos[indice] = Object.assign({}, pasos[indice], {
        texto: '<p class="guia-ok">✓ Configuración guardada.</p>' + pasos[indice].texto,
      });
      iniciar(config, pasos, 1, indice);
    } else if (config.iniciar === 'configuracion') {
      iniciar(config, PASOS_CONFIGURACION, 1, 0);
    } else if (config.iniciar === 'extraccion') {
      iniciar(config, PASOS_EXTRACCION, PASOS_CONFIGURACION.length + 1, 0);
    }
  });
})();
