import os

from django.conf import settings

# Query param para romper el cache del navegador en los <link> de web/static/web/ (css/js
# propios) - se recalcula una sola vez al arrancar el proceso, a partir del mtime mas
# reciente entre esos archivos, asi cualquier cambio (incluso sin reiniciar el server en
# `runserver`, que no vigila estaticos) ya alcanza para invalidar el cache sin tener que
# acordarse de bumpear nada a mano (ver el caso del .zip de la extensión, que se quedó
# cacheado varias vueltas por no tener un query param que lo invalide).
def _calcular_static_version():
    carpeta = settings.BASE_DIR / 'web' / 'static' / 'web'
    try:
        mtimes = [
            os.path.getmtime(os.path.join(root, f))
            for root, _dirs, files in os.walk(carpeta)
            for f in files
        ]
        return str(int(max(mtimes))) if mtimes else '0'
    except OSError:
        return '0'


_STATIC_VERSION = _calcular_static_version()


def static_version(request):
    return {'static_v': _STATIC_VERSION}
