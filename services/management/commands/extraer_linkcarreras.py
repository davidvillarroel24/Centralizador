from django.core.management.base import BaseCommand

from services.extraccion.linkcarreras import extraer_linkcarrera


class Command(BaseCommand):

    def handle(self, *args, **kwargs):

        self.stdout.write("Importando link carreras...")

        extraer_linkcarrera()

        self.stdout.write(
            self.style.SUCCESS("Importación completada.")
        )
