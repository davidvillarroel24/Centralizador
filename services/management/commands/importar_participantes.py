from django.core.management.base import BaseCommand
from services.data_utils.import_to_db import import_participantes_a_accesos


class Command(BaseCommand):
    help = 'Importa participantes.json (ultimo acceso) hacia AccesoCurso (materia + moodle_userid).'

    def handle(self, *args, **options):
        self.stdout.write('Importando último acceso desde JSON...')
        try:
            result = import_participantes_a_accesos()
            self.stdout.write(self.style.SUCCESS(f"Importación completada: {result}"))
        except Exception as e:
            self.stderr.write(f"Error durante la importación: {e}")
            raise
