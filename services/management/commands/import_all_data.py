from django.core.management.base import BaseCommand
from services.data_utils.import_to_db import import_tareas_from_json
from services.data_utils.import_estudiantes_to_db import import_estudiantes_from_json


class Command(BaseCommand):
    help = 'Import all data (tasks, students, deliveries) from JSON files into Django DB.'

    def handle(self, *args, **options):
        self.stdout.write('Iniciando importación completa de datos...')

        try:
            # Importar tareas primero
            self.stdout.write('1. Importando tareas...')
            result_tareas = import_tareas_from_json()
            self.stdout.write(self.style.SUCCESS(f"   ✓ Tareas: {result_tareas}"))

            # Importar estudiantes/entregas
            self.stdout.write('2. Importando estudiantes y entregas...')
            result_estudiantes = import_estudiantes_from_json()
            if 'error' in result_estudiantes:
                self.stderr.write(f"   ✗ Error en estudiantes: {result_estudiantes['error']}")
            else:
                self.stdout.write(self.style.SUCCESS(f"   ✓ Estudiantes/Entregas: {result_estudiantes}"))

            self.stdout.write(self.style.SUCCESS('\n✅ Importación completada exitosamente'))

        except Exception as e:
            self.stderr.write(f"Error durante la importación: {e}")
            raise
