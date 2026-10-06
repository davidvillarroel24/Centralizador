from django.core.management.base import BaseCommand

from services.extraccion.asignacion import extraer_asignacion


class Command(BaseCommand):

    help = (
        'Asigna automaticamente a periodos/parciales las tareas (tipo=assign) ya '
        'importadas a la base de datos (ver extraer_tareas + "Importar tareas a BD"). '
        'Sin ids, usa todas las tareas assign disponibles. Con ids (de Materia), filtra '
        'solo esos cursos. Ejemplo: python manage.py extraer_asignacion 227 193'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'ids', nargs='*', type=int, default=None,
            help='IDs de Materia a asignar (opcional; sin esto, usa todas las tareas assign)',
        )

    def handle(self, *args, **options):

        ids = options['ids'] or None
        self.stdout.write(f"Asignando tareas{f' de {len(ids)} curso(s): {ids}' if ids else ' (todas las disponibles)'}...")

        asignacion, errores, warning = extraer_asignacion(ids)

        if warning:
            self.stdout.write(self.style.WARNING(warning))
        self.stdout.write(
            self.style.SUCCESS(f"Importación completada: {len(asignacion)} tarea(s) asignadas, {len(errores)} error(es).")
        )
