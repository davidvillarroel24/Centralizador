from django.core.management.base import BaseCommand

from services.extraccion.categorias import extract_categorias


class Command(BaseCommand):

    def handle(self, *args, **kwargs):

        self.stdout.write("Importando categorias...")

        extract_categorias()

        self.stdout.write(
            self.style.SUCCESS("Importación completada.")
        )
