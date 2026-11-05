from unittest import mock

from django.test import TestCase

from data.models import Facultad, Carrera, Materia, Unidad, Tarea, Estudiante, Entrega
from services.data_utils import import_estudiantes_to_db


class ImportarEntregasSinEmailTests(TestCase):
    """Una cuenta sin permiso para ver el correo (ej. Decano) extrae filas sin email: antes
    se descartaban todas y la tarea quedaba sin entregas."""

    def setUp(self):
        carrera = Carrera.objects.create(facultad=Facultad.objects.create(nombre='Ingeniería'), nombre='Sistemas')
        materia = Materia.objects.create(
            gestion=2026, nombre='Bases de Datos', moodle_nombre='2026/BDD',
            moodle_url='https://moodle.example/course/view.php?id=1', carrera=carrera,
        )
        self.tarea = Tarea.objects.create(
            unidad=Unidad.objects.create(materia=materia, nombre='Unidad 1'),
            moodle_id=77, titulo='Práctica 1', tipo='assign',
            url='https://moodle.example/mod/assign/view.php?id=77',
        )
        Estudiante.objects.create(moodle_userid=101, nombre='Ana Pérez', email='ana@example.com')

    def _importar(self, estudiantes):
        datos = [{'id': 77, 'estudiantes': estudiantes}]
        with mock.patch.object(import_estudiantes_to_db.cargarjson, 'cargar_estudiantes', return_value=datos):
            return import_estudiantes_to_db.import_estudiantes_from_json()

    def test_estudiante_ya_conocido_sin_email_guarda_la_entrega(self):
        self._importar([{'userid': '101', 'nombre': 'Ana Pérez', 'email': None, 'estado': 'Enviado para calificar'}])
        entrega = Entrega.objects.get(tarea=self.tarea, estudiante__moodle_userid=101)
        self.assertEqual(entrega.estado, 'Enviado para calificar')
        self.assertEqual(entrega.estudiante.email, 'ana@example.com')

    def test_estudiante_desconocido_sin_email_se_omite(self):
        resultado = self._importar([{'userid': '999', 'nombre': 'Nuevo', 'email': None, 'estado': 'Sin entrega'}])
        self.assertEqual(resultado['skipped'], 1)
        self.assertFalse(Entrega.objects.filter(estudiante__moodle_userid=999).exists())
