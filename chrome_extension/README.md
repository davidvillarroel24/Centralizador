# Centralizador TECBA - Captura cookie Moodle

Extensión de Chrome (Manifest V3) que lee la cookie `MoodleSession` del navegador y, con
confirmación del usuario, la manda cifrada al servidor de Centralizador - en vez de tener
que copiarla a mano desde las herramientas de desarrollador (F12 → Application →
Cookies). Ya no existe un campo de texto donde pegarla: todo el flujo pasa por el botón
"Extraer cookie de Moodle" del panel de extracción.

## Cómo funciona

- `background.js` (service worker) es el único archivo que toca `chrome.cookies` - lee el
  valor de `MoodleSession` para el dominio de Moodle configurado, cada vez que se lo piden
  (no guarda nada).
- `content_script.js` corre solo en las páginas de Centralizador (nunca en Moodle) y
  escucha el evento `centralizador-pedir-cookie`, que dispara el botón "⚡ Extraer cookie
  de Moodle" de `dashboard.html` al hacer clic. Le pide el valor al service worker y lo
  devuelve a la página con el evento `centralizador-cookie-capturada` - nunca lo escribe
  en el DOM ni en ningún campo visible.
- La página (no la extensión) es quien muestra el cuadro de confirmación (Guardar /
  Cancelar) y, recién si el usuario confirma, lo envía por HTTPS al servidor, donde se
  guarda cifrado (ver `data/cookie_crypto.py`), vence a las 2 horas o al cerrar sesión.
- La cookie nunca sale del navegador del usuario hacia ningún servidor que no sea el propio
  Centralizador.

## Probarla en modo desarrollador (mientras no está en la Web Store)

1. `chrome://extensions`
2. Activar "Modo de desarrollador" (switch arriba a la derecha).
3. "Cargar descomprimida" → seleccionar esta carpeta (`chrome_extension/`).
4. Iniciar sesión en Moodle en alguna pestaña (no hace falta dejarla abierta).
5. Ir al dashboard de extracción de Centralizador y usar el botón "⚡ Extraer cookie de
   Moodle".

## Antes de subirla a la Chrome Web Store (privada/no listada)

- [ ] Reemplazar los íconos de `icons/` (son un placeholder generado por script, no arte
      final) por íconos reales de 16/48/128px.
- [x] Agregar el dominio real de producción (VPS, `https://centralizador-tecba.duckdns.org`)
      a `host_permissions` y a `content_scripts.matches` en `manifest.json`, además de
      `moodle-108854-0.cloudclusters.net` (Moodle) y `localhost:8000`/`127.0.0.1:8000`
      (desarrollo).
- [ ] Pagar el registro único de $5 USD como developer en el
      [Chrome Web Store Developer Dashboard](https://chrome.google.com/webstore/devconsole).
- [ ] Subir un .zip de esta carpeta, completar el listado (nombre, descripción, íconos,
      capturas) y la justificación de permisos (`cookies` + `host_permissions` concretos,
      nunca `<all_urls>`).
- [ ] Publicar como **Unlisted** (cualquiera con el link instala) o **Private** (solo
      cuentas/Google Group agregados como testers) - ver la página de política de
      privacidad en `/extension/privacidad/`, que el formulario de publicación va a pedir.
- [ ] Esperar la revisión de Google (puede tardar más por pedir `cookies`).

## Empaquetar el .zip para descarga

**Importante**: correr esto SIEMPRE que se modifique `background.js`, `content_script.js`
o `manifest.json` - el .zip es un archivo generado, no se actualiza solo. Si te olvidás de
este paso, la extensión que la gente instala desde "Descargar extensión" en Configuración
queda desactualizada y deja de coincidir con la página (así se rompió el 2026-10-22).

Desde la raíz del repo:

```
python chrome_extension/empaquetar.py
```

El .zip generado se sirve desde `web/static/web/downloads/` y se enlaza en la página de
Configuración de Centralizador.
