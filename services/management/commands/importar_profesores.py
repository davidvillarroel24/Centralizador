from django.core.management.base import BaseCommand

from services.imports.profesores import importar_profesores


class Command(BaseCommand):
    
    help = "Importa profesores desde linkcarreras.json"

    def handle(self, *args, **kwargs):

        self.stdout.write("Iniciando importación de profesores...")

        importar_profesores()

        self.stdout.write(
            self.style.SUCCESS("Importación completada correctamente.")
        )
