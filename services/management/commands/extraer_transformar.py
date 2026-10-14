from django.core.management.base import BaseCommand

from data.models import Profesor
from services.extraccion.trasformar import extraer_transformar


class Command(BaseCommand):

    help = (
        'Genera notas_profesor_<id>.xlsx desde la base de datos, filtrado por los cursos '
        'indicados (Materia.id) y los pesos por categoria del profesor indicado. '
        'Ejemplo: python manage.py extraer_transformar 227 193 --profesor 50'
    )

    def add_arguments(self, parser):
        parser.add_argument('ids', nargs='+', type=int, help='IDs de Materia a incluir en el Excel')
        parser.add_argument(
            '--profesor', type=int, required=True,
            help='Profesor.id duenio de los pesos de categoria a usar.',
        )

    def handle(self, *args, **options):

        ids = options['ids']
        profesor = Profesor.objects.filter(pk=options['profesor']).first()
        if profesor is None:
            self.stderr.write(self.style.ERROR(f"No existe Profesor con id={options['profesor']}"))
            return

        self.stdout.write(f"Generando Excel para {len(ids)} curso(s): {ids}...")

        total, archivo = extraer_transformar(ids, profesor)

        self.stdout.write(
            self.style.SUCCESS(f"Excel generado con {total} estudiante(s) en {archivo}.")
        )
