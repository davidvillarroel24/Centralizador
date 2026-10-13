from django.core.management.base import BaseCommand

from services.extraccion.asignacion import extraer_asignacion


class Command(BaseCommand):

    help = (
        'Asigna automaticamente a periodos/parciales las tareas (tipo=assign) ya '
        'importadas a la base de datos (ver extraer_tareas + "Importar tareas a BD"), '
        'filtradas por los cursos indicados (Materia.id). '
        'Ejemplo: python manage.py extraer_asignacion 227 193'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'ids', nargs='+', type=int,
            help='IDs de Materia a asignar (obligatorio)',
        )

    def handle(self, *args, **options):

        ids = options['ids']
        self.stdout.write(f"Asignando tareas de {len(ids)} curso(s): {ids}...")

        asignacion, errores, warning = extraer_asignacion(ids)

        if warning:
            self.stdout.write(self.style.WARNING(warning))
        self.stdout.write(
            self.style.SUCCESS(f"Importación completada: {len(asignacion)} tarea(s) asignadas, {len(errores)} error(es).")
        )
