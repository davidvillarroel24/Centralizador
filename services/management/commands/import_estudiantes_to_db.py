from django.core.management.base import BaseCommand
from services.data_utils.import_estudiantes_to_db import import_estudiantes_from_json


class Command(BaseCommand):
    help = 'Import students and deliveries from JSON files into the Django DB.'

    def handle(self, *args, **options):
        self.stdout.write('Importando estudiantes y entregas desde JSON...')
        try:
            result = import_estudiantes_from_json()
            if 'error' in result:
                self.stderr.write(f"Error: {result['error']}")
            else:
                self.stdout.write(self.style.SUCCESS(f"Importación completada: {result}"))
        except Exception as e:
            self.stderr.write(f"Error durante la importación: {e}")
            raise
