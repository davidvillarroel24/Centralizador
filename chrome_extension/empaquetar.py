"""Reempaqueta esta carpeta en el .zip que se sirve desde /configuracion/ (botón
"Descargar extensión"). Correr esto SIEMPRE que se toque background.js, content_script.js
o manifest.json - si no, el .zip descargable queda desactualizado y la extensión instalada
desde ahí deja de coincidir con lo que espera la página (justo lo que pasó el 2026-10-22:
el .zip tenía el content_script.js viejo, basado en un textarea que ya no existe).

Uso (desde la raíz del repo o desde esta carpeta, da igual):
    python chrome_extension/empaquetar.py
"""

import os
import zipfile

CARPETA_ORIGEN = os.path.dirname(os.path.abspath(__file__))
DESTINO = os.path.join(CARPETA_ORIGEN, '..', 'web', 'static', 'web', 'downloads', 'centralizador-moodle-cookie.zip')
NOMBRE_BASE = 'centralizador-moodle-cookie'
EXCLUIR = {'README.md', 'empaquetar.py'}


def main():
    destino = os.path.normpath(DESTINO)
    if os.path.exists(destino):
        os.remove(destino)

    with zipfile.ZipFile(destino, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(CARPETA_ORIGEN):
            for nombre in files:
                if nombre in EXCLUIR:
                    continue
                ruta_completa = os.path.join(root, nombre)
                ruta_relativa = os.path.relpath(ruta_completa, CARPETA_ORIGEN)
                arcname = os.path.join(NOMBRE_BASE, ruta_relativa)
                z.write(ruta_completa, arcname)

    print(f'Empaquetado OK: {destino}')
    with zipfile.ZipFile(destino) as z:
        for nombre in z.namelist():
            print(' -', nombre)


if __name__ == '__main__':
    main()
