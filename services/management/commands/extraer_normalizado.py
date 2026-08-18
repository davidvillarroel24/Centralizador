from django.core.management.base import BaseCommand

from services.extraccion.normalizacion import extraer_normalizado


class Command(BaseCommand):

    def handle(self, *args, **kwargs):

        self.stdout.write("Importando carreras...")

        extraer_normalizado()

        self.stdout.write(
            self.style.SUCCESS("Importación completada.")
        )
