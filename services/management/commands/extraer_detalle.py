from django.core.management.base import BaseCommand

from services.extraccion.detalles import extraer_detalle


class Command(BaseCommand):

    help = (
        'Extrae descripcion + archivos adjuntos por el docente (ArchivoTarea) de las '
        'tareas tipo assign de los cursos indicados (Materia.id), nunca de todos. '
        'Necesita que esos cursos ya tengan tareas importadas a BD (extraer_tareas + '
        '"Importar tareas"). Ejemplo: python manage.py extraer_detalle 227 193'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'ids', nargs='+', type=int,
            help='IDs de Materia a extraer (ver /web/extraccion/ o Materia.objects.values_list("id", "nombre"))',
        )

    def handle(self, *args, **options):

        ids = options['ids']
        self.stdout.write(f"Extrayendo detalle de tareas de {len(ids)} curso(s): {ids}...")

        detalle, detenido = extraer_detalle(ids)

        if detenido:
            self.stdout.write(self.style.WARNING("Extracción detenida manualmente."))
        self.stdout.write(
            self.style.SUCCESS(f"Extracción completada: {len(detalle)} tarea(s) procesada(s).")
        )
