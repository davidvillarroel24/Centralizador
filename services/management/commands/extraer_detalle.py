from django.core.management.base import BaseCommand

from services.extraccion.detalles import extraer_detalle


class Command(BaseCommand):

    def handle(self, *args, **kwargs):

        self.stdout.write("Importando carreras...")

        extraer_detalle()

        self.stdout.write(
            self.style.SUCCESS("Importación completada.")
        )
