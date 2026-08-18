from django.core.management.base import BaseCommand

from services.extraccion.asignacion import extraer_asignacion


class Command(BaseCommand):

    def handle(self, *args, **kwargs):

        self.stdout.write("Importando carreras...")

        extraer_asignacion()

        self.stdout.write(
            self.style.SUCCESS("Importación completada.")
        )
