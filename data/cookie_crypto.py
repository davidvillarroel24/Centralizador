"""Cifrado reversible de la cookie MoodleSession guardada en Profesor.

La clave de cifrado se deriva de 2 ingredientes:
  1. 4 caracteres del hash de la contraseña del usuario (posicion 10 en adelante), que
     cambia si el usuario cambia de contraseña - asi la cookie guardada queda invalida
     automaticamente cuando eso pasa, sin tener que borrarla a mano.
  2. SECRET_KEY del servidor, que NO vive en la base de datos.

Un atacante que solo robe la base de datos (cookies cifradas + hashes de contraseña, todo
en la misma BD) no alcanza a descifrar nada: tambien necesitaria el SECRET_KEY del
servidor, que esta en el entorno/config, no en la base.

No se usan los 4 caracteres crudos como clave (serian un espacio de busqueda demasiado
chico, ~pocos miles de combinaciones) - se combinan con el SECRET_KEY y se pasan por
SHA-256 para obtener una clave de 32 bytes, como exige Fernet.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

POSICION_FRAGMENTO = 10
LARGO_FRAGMENTO = 4


def _derivar_clave(user):
    password_hash = user.password or ''
    fragmento = password_hash[POSICION_FRAGMENTO:POSICION_FRAGMENTO + LARGO_FRAGMENTO]
    material = (fragmento + settings.SECRET_KEY).encode('utf-8')
    digest = hashlib.sha256(material).digest()
    return base64.urlsafe_b64encode(digest)


def cifrar_cookie(user, valor):
    """Devuelve el token cifrado (str) listo para guardar en Profesor.moodle_cookie_cifrada."""
    f = Fernet(_derivar_clave(user))
    return f.encrypt(valor.encode('utf-8')).decode('utf-8')


def descifrar_cookie(user, token):
    """Devuelve el valor original, o None si no se pudo descifrar (contraseña cambiada,
    dato corrupto, etc.) - nunca levanta excepcion, para que el llamador solo tenga que
    chequear None y pedir recapturar la cookie."""
    if not token:
        return None
    f = Fernet(_derivar_clave(user))
    try:
        return f.decrypt(token.encode('utf-8')).decode('utf-8')
    except (InvalidToken, ValueError):
        return None
