from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from data.models import Profesor

USERNAME_DEFAULT = 'tecba'
PASSWORD_DEFAULT = 'st4rcr4fT2'
MOODLE_ID_PLACEHOLDER = 999999


class Command(BaseCommand):
    help = (
        'Crea (o actualiza la contraseña de) un usuario admin de prueba, junto con el '
        'Profesor al que debe coincidir segun login_view/register_view. Por defecto crea '
        '"tecba" / "st4rcr4fT2". Idempotente: correrlo de nuevo no duplica nada.'
    )

    def add_arguments(self, parser):
        parser.add_argument('username', nargs='?', default=USERNAME_DEFAULT)
        parser.add_argument('password', nargs='?', default=PASSWORD_DEFAULT)

    def handle(self, *args, **options):
        username = options['username']
        password = options['password']

        profesor, creado_profesor = Profesor.objects.get_or_create(
            nombre=username,
            defaults={
                'moodle_id': MOODLE_ID_PLACEHOLDER,
                'url': f'https://moodle-108854-0.cloudclusters.net/user/view.php?id={MOODLE_ID_PLACEHOLDER}',
            },
        )
        self.stdout.write(
            f"Profesor {'creado' if creado_profesor else 'ya existia'}: "
            f"id={profesor.id} nombre={profesor.nombre!r}"
        )

        user, creado_user = User.objects.get_or_create(
            username=username,
            defaults={'is_staff': True, 'is_superuser': True},
        )
        user.set_password(password)
        user.is_staff = True
        user.is_superuser = True
        user.save()
        self.stdout.write(
            f"User {'creado' if creado_user else 'actualizado (password reseteado)'}: "
            f"id={user.id} username={user.username!r}"
        )

        if profesor.user_id != user.id:
            profesor.user = user
            profesor.save(update_fields=['user'])
        self.stdout.write(f"Profesor.user enlazado a User id={profesor.user_id}")

        self.stdout.write(self.style.SUCCESS(
            f"\nListo. Inicia sesion en /web/login/ con usuario '{username}' y la contraseña dada."
        ))
