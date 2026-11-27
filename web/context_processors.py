import os

from django.conf import settings

from data.models import ConfiguracionInstitucional

# Query param para romper el cache del navegador en los <link> de web/static/web/ (css/js
# propios), a partir del mtime mas reciente entre esos archivos.
#
# BUG (encontrado 2026-11-28): esto se calculaba UNA sola vez "al arrancar el proceso"
# (modulo importado una vez) y se reusaba para todos los requests - en `runserver`, que se
# queda corriendo horas/dias sin reiniciarse mientras se edita CSS/JS, el valor quedaba
# pegado al momento en que el proceso arrancó, así que ?v= nunca cambiaba aunque el archivo
# sí - el navegador seguía sirviendo su copia vieja en caché sin enterarse nunca del cambio
# (visto en vivo: un overlay con una clase CSS nueva aparecía como texto plano sin estilo,
# porque el navegador nunca había vuelto a pedir el dashboard.css actualizado). Ahora se
# recalcula en cada request - es un os.walk() chico (unos pocos archivos propios), de costo
# insignificante al lado de todo lo demás que ya hace una vista. En producción esto ni pesa:
# WhiteNoise (ver STORAGES en settings.py) ya sirve estáticos con su propio nombre con hash
# de contenido, haciendo este query param redundante ahí - esto es pura ayuda para dev local.
def static_version(request):
    carpeta = settings.BASE_DIR / 'web' / 'static' / 'web'
    try:
        mtimes = [
            os.path.getmtime(os.path.join(root, f))
            for root, _dirs, files in os.walk(carpeta)
            for f in files
        ]
        valor = str(int(max(mtimes))) if mtimes else '0'
    except OSError:
        valor = '0'
    return {'static_v': valor}


def mensajes_resultado(request):
    """Si los popups de resultado (SweetAlert, ver mostrarResultado en base.html) muestran
    el mensaje completo de cada acción o solo un resumen corto - ver
    ConfiguracionInstitucional.mensajes_resultado_detallados, configurable en
    /configuracion/ (solo Administrador)."""
    return {'mensajes_resultado_detallados': ConfiguracionInstitucional.actual().mensajes_resultado_detallados}
