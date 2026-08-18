from django.core.management.base import BaseCommand

from services.imports.niveles import importar_niveles


class Command(BaseCommand):

    help = "Importa niveles desde linkcarreras.json"

    def handle(self, *args, **kwargs):

        self.stdout.write("Importando niveles...")

        importar_niveles()

        self.stdout.write(
            self.style.SUCCESS("Importación completada.")
        )
