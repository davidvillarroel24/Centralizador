from django.core.management.base import BaseCommand

from services.extraccion.estudiantes import extraer_estudiantes


class Command(BaseCommand):

    def handle(self, *args, **kwargs):

        self.stdout.write("Importando carreras...")

        extraer_estudiantes()

        self.stdout.write(
            self.style.SUCCESS("Importación completada.")
        )
