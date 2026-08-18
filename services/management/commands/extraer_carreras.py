from django.core.management.base import BaseCommand

from services.extraccion.carreras import extraer_carreras


class Command(BaseCommand):

    def handle(self, *args, **kwargs):

        self.stdout.write("Importando carreras...")

        extraer_carreras()

        self.stdout.write(
            self.style.SUCCESS("Importación completada.")
        )
