from django.core.management.base import BaseCommand

from services.extraccion.scrap import extraer_scrap


class Command(BaseCommand):

    def handle(self, *args, **kwargs):

        self.stdout.write("Importando carreras...")

        extraer_scrap()

        self.stdout.write(
            self.style.SUCCESS("Importación completada.")
        )
