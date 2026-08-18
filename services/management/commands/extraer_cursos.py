from django.core.management.base import BaseCommand

from services.extraccion.cursos import extraer_cursos


class Command(BaseCommand):

    def handle(self, *args, **kwargs):

        self.stdout.write("Importando carreras...")

        extraer_cursos()

        self.stdout.write(
            self.style.SUCCESS("Importación completada.")
        )
