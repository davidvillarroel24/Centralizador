from django.core.management.base import BaseCommand

from services.extraccion.estudiantes import extraer_estudiantes


class Command(BaseCommand):

    help = (
        'Extrae estudiantes/entregas de los cursos indicados (Materia.id), nunca de '
        'todos. Necesita que esos cursos ya tengan tareas extraidas e importadas a BD '
        '(extraer_tareas + "Importar tareas"), y que --profesor tenga pesos de categoria '
        'guardados (PesosCategorias, ver /configuracion/) - sin eso no arranca. '
        'Ejemplo: python manage.py extraer_estudiantes 227 193 --profesor 50'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'ids', nargs='+', type=int,
            help='IDs de Materia a extraer (ver /web/extraccion/ o Materia.objects.values_list("id", "nombre"))',
        )
        parser.add_argument(
            '--profesor', type=int, required=True,
            help='Profesor.id duenio de esta extraccion; debe tener PesosCategorias guardado.',
        )

    def handle(self, *args, **options):

        ids = options['ids']
        profesor_id = options['profesor']
        self.stdout.write(f"Extrayendo estudiantes de {len(ids)} curso(s): {ids}...")

        estudiantes, detenido = extraer_estudiantes(ids, profesor_id=profesor_id)

        if detenido:
            self.stdout.write(self.style.WARNING("Extracción detenida manualmente."))
        self.stdout.write(
            self.style.SUCCESS(f"Importación completada: {len(estudiantes)} registro(s) de entrega.")
        )
