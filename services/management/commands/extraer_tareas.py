from django.core.management.base import BaseCommand

from services.extraccion.tareas import extraer_tareas


class Command(BaseCommand):

    def handle(self, *args, **kwargs):

        self.stdout.write("Importando carreras...")

        extraer_tareas()

        self.stdout.write(
            self.style.SUCCESS("Importación completada.")
        )
