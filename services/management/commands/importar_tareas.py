from django.core.management.base import BaseCommand

from services.imports.tareas import importar_tareas


class Command(BaseCommand):

    help = "Importa tareas desde tareas.json"

    def handle(self, *args, **kwargs):

        self.stdout.write("Importando tareas...")

        importar_tareas()

        self.stdout.write(
            self.style.SUCCESS("Importación completada.")
        )
