from django.core.management.base import BaseCommand

from services.utils.run_scraping import extraer_carreras_completo


class Command(BaseCommand):

    help = (
        'Corre la cadena completa (categorias -> carreras -> linkcarreras) en un solo '
        'paso - el mismo codigo que usa el boton "0. Extraer carreras" del dashboard. '
        'Para correr los 3 pasos por separado, usar extraer_categorias / extraer_carreras '
        '/ extraer_linkcarreras en ese orden.'
    )

    def handle(self, *args, **options):

        self.stdout.write("Extrayendo carreras (categorias -> carreras -> linkcarreras)...")

        categorias, carreras_html, linkcarreras = extraer_carreras_completo()

        total_materias = sum(len(item.get('materias') or []) for item in linkcarreras)
        self.stdout.write(
            self.style.SUCCESS(
                f"Importación completada: {len(categorias)} categoría(s), "
                f"{len(linkcarreras)} carrera(s)/nivel(es) con {total_materias} materia(s)."
            )
        )
