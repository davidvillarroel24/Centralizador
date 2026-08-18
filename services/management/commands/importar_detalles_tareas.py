from django.core.management.base import BaseCommand

from services.imports.detalles_tareas import (
    importar_detalles_tareas
)


class Command(BaseCommand):

    help = "Importa detalles de tareas"

    def handle(self, *args, **kwargs):

        self.stdout.write(
            "Importando detalles de tareas..."
        )

        importar_detalles_tareas()

        self.stdout.write(
            self.style.SUCCESS(
                "Importación completada."
            )
        )
