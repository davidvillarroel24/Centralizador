from django.core.management.base import BaseCommand

from services.extraccion.estudiantes import extraer_estudiantes


class Command(BaseCommand):

    help = (
        'Extrae estudiantes/entregas de los cursos indicados (Materia.id), nunca de '
        'todos. Necesita que esos cursos ya tengan tareas extraidas (extraer_tareas). '
        'Ejemplo: python manage.py extraer_estudiantes 227 193'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'ids', nargs='+', type=int,
            help='IDs de Materia a extraer (ver /web/extraccion/ o Materia.objects.values_list("id", "nombre"))',
        )

    def handle(self, *args, **options):

        ids = options['ids']
        self.stdout.write(f"Extrayendo estudiantes de {len(ids)} curso(s): {ids}...")

        estudiantes, detenido = extraer_estudiantes(ids)

        if detenido:
            self.stdout.write(self.style.WARNING("Extracción detenida manualmente."))
        self.stdout.write(
            self.style.SUCCESS(f"Importación completada: {len(estudiantes)} registro(s) de entrega.")
        )
