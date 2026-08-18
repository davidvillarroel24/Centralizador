from django.core.management.base import BaseCommand

from services.extraccion.session import extraer_session


class Command(BaseCommand):

    def handle(self, *args, **kwargs):

        self.stdout.write("Importando carreras...")

        extraer_session()

        self.stdout.write(
            self.style.SUCCESS("Importación completada.")
        )
