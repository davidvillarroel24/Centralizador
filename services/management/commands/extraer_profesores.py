from django.core.management.base import BaseCommand

from services.extraccion.profesores import extraer_profesores


class Command(BaseCommand):

    def handle(self, *args, **kwargs):

        self.stdout.write("Importando carreras...")

        extraer_profesores()

        self.stdout.write(
            self.style.SUCCESS("Importación completada.")
        )
