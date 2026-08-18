from django.core.management.base import BaseCommand
from services.data_utils.import_to_db import import_tareas_from_json


class Command(BaseCommand):
    help = 'Import tasks from JSON files into the Django DB (minimal fields).'

    def handle(self, *args, **options):
        self.stdout.write('Importando tareas desde JSON...')
        try:
            result = import_tareas_from_json()
            self.stdout.write(self.style.SUCCESS(f"Importación completada: {result}"))
        except Exception as e:
            self.stderr.write(f"Error durante la importación: {e}")
            raise
