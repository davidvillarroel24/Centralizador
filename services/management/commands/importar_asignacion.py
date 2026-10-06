from django.core.management.base import BaseCommand

from services.data_utils.import_to_db import import_asignacion_from_json


class Command(BaseCommand):

    help = "Importa asignacion.json (salida de extraer_asignacion) hacia Tarea.categoria/Tarea.parcial"

    def handle(self, *args, **kwargs):

        self.stdout.write("Importando asignación...")

        resultado = import_asignacion_from_json()

        self.stdout.write(
            self.style.SUCCESS(f"Importación completada: {resultado}.")
        )
