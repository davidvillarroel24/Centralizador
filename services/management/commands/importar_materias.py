from django.core.management.base import BaseCommand

from services.imports.materias import importar_materias


class Command(BaseCommand):

    help = "Importa materias desde linkcarreras.json"

    def handle(self, *args, **kwargs):

        self.stdout.write("Importando materias...")

        importar_materias()

        self.stdout.write(
            self.style.SUCCESS("Importación completada.")
        )
