from django.core.management.base import BaseCommand

from services.extraccion.trasformar import extraer_transformar


class Command(BaseCommand):

    def handle(self, *args, **kwargs):

        self.stdout.write("Importando Notas trasformadas...")

        extraer_transformar()

        self.stdout.write(
            self.style.SUCCESS("Importación completada.")
        )
