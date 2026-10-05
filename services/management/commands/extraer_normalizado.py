from django.core.management.base import BaseCommand

from services.extraccion.normalizacion import extraer_normalizado


class Command(BaseCommand):

    help = (
        'Normaliza (aplana) las tareas ya extraidas de los cursos indicados (Materia.id), '
        'nunca de todos. Necesita que esos cursos ya tengan tareas extraidas '
        '(extraer_tareas). Ejemplo: python manage.py extraer_normalizado 227 193'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'ids', nargs='+', type=int,
            help='IDs de Materia a normalizar (ver /web/extraccion/ o Materia.objects.values_list("id", "nombre"))',
        )

    def handle(self, *args, **options):

        ids = options['ids']
        self.stdout.write(f"Normalizando tareas de {len(ids)} curso(s): {ids}...")

        normalizado = extraer_normalizado(ids)

        self.stdout.write(
            self.style.SUCCESS(f"Importación completada: {len(normalizado)} tarea(s) planas.")
        )
