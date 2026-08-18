from django.core.management.base import BaseCommand

from services.imports.estudiantes import (
    importar_estudiantes
)


class Command(BaseCommand):

    help = "Importa estudiantes y entregas"

    def handle(self, *args, **kwargs):

        self.stdout.write(
            "Importando estudiantes..."
        )

        importar_estudiantes()

        self.stdout.write(
            self.style.SUCCESS(
                "Importación completada."
            )
        )
