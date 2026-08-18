from django.core.management.base import BaseCommand

from services.imports.facultades import importar_facultades


class Command(BaseCommand):
    help = "Importa facultades desde linkcarreras.json"

    def handle(self, *args, **kwargs):

        self.stdout.write("Importando facultades...")

        importar_facultades()

        self.stdout.write(
            self.style.SUCCESS("Importación completada.")
        )
