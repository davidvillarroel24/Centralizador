from django.core.management.base import BaseCommand

from services.extraccion.participantes import extraer_participantes
from scraping.scrapers.participantes import PERPAGE_MINIMO


class Command(BaseCommand):

    help = (
        'Extrae el padron de inscritos (estudiantes y profesores) de los cursos indicados '
        '(Materia.id), con su ultimo acceso al curso - via /user/index.php?id=<curso>. '
        'Ejemplo: python manage.py extraer_participantes 227 193'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'ids', nargs='+', type=int,
            help='IDs de Materia a extraer (ver /web/extraccion/ o Materia.objects.values_list("id", "nombre"))',
        )
        parser.add_argument(
            '--cookie', type=str, default=None,
            help='Cookie MoodleSession a usar; si se omite, usa MOODLE_SESSION_COOKIE del .env.',
        )
        parser.add_argument(
            '--perpage', type=int, default=PERPAGE_MINIMO,
            help=f'Nunca baja de {PERPAGE_MINIMO} aunque se pida menos.',
        )

    def handle(self, *args, **options):
        ids = options['ids']
        self.stdout.write(f"Extrayendo participantes de {len(ids)} curso(s): {ids}...")

        resultado, detenido = extraer_participantes(
            ids, cookie=options['cookie'], perpage=options['perpage']
        )

        if detenido:
            self.stdout.write(self.style.WARNING("Extracción detenida manualmente."))
        self.stdout.write(
            self.style.SUCCESS(f"Extracción completada: {len(resultado)} participante(s).")
        )
