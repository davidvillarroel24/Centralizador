# Centralizador TECBA - Captura cookie Moodle

Extensión de Chrome (Manifest V3) que lee la cookie `MoodleSession` del navegador y la
pega en el campo "Cookie de Moodle" de Centralizador, en vez de tener que copiarla a mano
desde las herramientas de desarrollador (F12 → Application → Cookies). El pegado manual
sigue funcionando exactamente igual; el botón que agrega la extensión es un atajo
opcional, no un reemplazo.

## Cómo funciona

- `background.js` (service worker) es el único archivo que toca `chrome.cookies` - lee el
  valor de `MoodleSession` para el dominio de Moodle configurado, cada vez que se lo piden
  (no guarda nada).
- `content_script.js` corre solo en las páginas de Centralizador (nunca en Moodle) y agrega
  un botón "⚡ Capturar cookie de Moodle automáticamente" junto a cada campo de cookie que
  ya existe en la página. Al hacer clic, le pide el valor al service worker y lo pega en el
  campo - el usuario sigue teniendo que revisar y apretar "Guardar cookie" como siempre.
- La cookie nunca sale del navegador del usuario hacia ningún servidor que no sea el propio
  Centralizador (y eso ya pasaba antes, al pegarla a mano).

## Probarla en modo desarrollador (mientras no está en la Web Store)

1. `chrome://extensions`
2. Activar "Modo de desarrollador" (switch arriba a la derecha).
3. "Cargar descomprimida" → seleccionar esta carpeta (`chrome_extension/`).
4. Iniciar sesión en Moodle en alguna pestaña (no hace falta dejarla abierta).
5. Ir a Centralizador (dashboard o la página de recuperación de sesión) y usar el botón
   nuevo junto al campo de cookie.

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

Desde la raíz del proyecto:

```
cd chrome_extension
# zippear todo menos este README si se quiere, o incluirlo tambien
```

El .zip generado se sirve desde `web/static/web/downloads/` y se enlaza en la página de
Configuración de Centralizador.
