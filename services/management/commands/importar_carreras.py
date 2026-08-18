from django.core.management.base import BaseCommand

from services.imports.carreras import importar_carreras


class Command(BaseCommand):

    help = "Importa carreras desde linkcarreras.json"

    def handle(self, *args, **kwargs):

        self.stdout.write("Importando carreras...")

        importar_carreras()

        self.stdout.write(
            self.style.SUCCESS("Importación completada.")
        )
