from django.core.management.base import BaseCommand

from services.extraccion.tareas import extraer_tareas


class Command(BaseCommand):

    help = (
        'Extrae las tareas de los cursos indicados (Materia.id), nunca de todos. '
        'Ejemplo: python manage.py extraer_tareas 227 193 — usa data/models.Materia para '
        'resolver los ids, no un listado aparte.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'ids', nargs='+', type=int,
            help='IDs de Materia a extraer (ver /web/extraccion/ o Materia.objects.values_list("id", "nombre"))',
        )

    def handle(self, *args, **options):

        ids = options['ids']
        self.stdout.write(f"Extrayendo tareas de {len(ids)} curso(s): {ids}...")

        tareas_nuevas, detenido = extraer_tareas(ids)

        if detenido:
            self.stdout.write(self.style.WARNING("Extracción detenida manualmente."))
        self.stdout.write(
            self.style.SUCCESS(f"Importación completada: {len(tareas_nuevas)} curso(s) procesados.")
        )
