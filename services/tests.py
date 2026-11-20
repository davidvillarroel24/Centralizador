from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from data.models import Facultad, Carrera, Materia, Unidad, Tarea, Estudiante, Entrega, TrabajoExtraccion
from services.data_utils import import_estudiantes_to_db
from services.utils import extraction_lock


def _quien_tiene_el_candado():
    candado = extraction_lock.current_lock()
    return candado.usuario if candado else 'nadie (libre)'


class CandadoExtraccionTests(TestCase):
    """Una sola extracción a la vez contra Moodle (services/utils/extraction_lock.py): la
    fila TrabajoExtraccion pk=1 hace de mutex. Los print() muestran cada paso en la consola
    (para la demostración de la prueba)."""

    def test_segundo_usuario_no_toma_el_candado(self):
        print('\n[test_segundo_usuario_no_toma_el_candado] Dos usuarios intentan extraer al mismo tiempo')
        job_a, _ = extraction_lock.try_acquire_lock('usuario.a')
        print(f'  usuario.a pide el candado -> {"lo toma" if job_a else "bloqueado"} (job={job_a})')
        job_b, aviso = extraction_lock.try_acquire_lock('usuario.b')
        print(f'  usuario.b pide el candado -> {"lo toma" if job_b else "bloqueado"} (job={job_b})')
        print(f'  candado en manos de: {_quien_tiene_el_candado()}')
        self.assertIsNotNone(job_a)
        self.assertIsNone(job_b)
        self.assertIsNone(aviso)
        self.assertEqual(extraction_lock.current_lock().usuario, 'usuario.a')

    def test_al_liberar_el_candado_el_siguiente_usuario_si_puede_tomarlo(self):
        print('\n[test_al_liberar_el_candado_el_siguiente_usuario_si_puede_tomarlo] El primero termina y libera; el segundo reintenta')
        job_a, _ = extraction_lock.try_acquire_lock('usuario.a')
        print(f'  usuario.a toma el candado (job={job_a})')
        extraction_lock.release_lock(job_a)
        print(f'  usuario.a termina y lo libera -> candado en manos de: {_quien_tiene_el_candado()}')
        self.assertIsNone(extraction_lock.current_lock())
        job_b, _ = extraction_lock.try_acquire_lock('usuario.b')
        print(f'  usuario.b reintenta -> {"lo toma" if job_b else "bloqueado"} (job={job_b})')
        print(f'  candado en manos de: {_quien_tiene_el_candado()}')
        self.assertIsNotNone(job_b)
        self.assertEqual(extraction_lock.current_lock().usuario, 'usuario.b')

    def test_candado_vencido_se_libera_solo(self):
        print('\n[test_candado_vencido_se_libera_solo] Un candado queda colgado (worker caído) y vence')
        extraction_lock.try_acquire_lock('usuario.a')
        # Simula un worker que murió hace más de LOCK_TIMEOUT_SECONDS sin liberar el candado.
        TrabajoExtraccion.objects.filter(pk=1).update(
            iniciado=timezone.now() - timedelta(seconds=extraction_lock.LOCK_TIMEOUT_SECONDS + 10)
        )
        print(f'  usuario.a lo tomó hace {extraction_lock.LOCK_TIMEOUT_SECONDS + 10}s y nunca lo liberó '
              f'(límite: {extraction_lock.LOCK_TIMEOUT_SECONDS}s)')
        job_b, aviso = extraction_lock.try_acquire_lock('usuario.b')
        print(f'  usuario.b pide el candado -> {"lo toma" if job_b else "bloqueado"} (job={job_b})')
        print(f'  candado en manos de: {_quien_tiene_el_candado()}')
        self.assertIsNotNone(job_b)
        self.assertIn('usuario.a', aviso)
        self.assertEqual(extraction_lock.current_lock().usuario, 'usuario.b')


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


class CandadoExtraccionTests(TestCase):
    """Candado global de extraccion (services/utils/extraction_lock.py): garantiza que
    solo haya UNA extraccion en curso a la vez en todo el sistema, sin importar que
    usuario la dispare (ver docstring de TrabajoExtraccion)."""

    def test_segundo_usuario_no_toma_el_candado_mientras_el_primero_esta_en_curso(self):
        job1, aviso1 = try_acquire_lock('docente_1')
        self.assertIsNotNone(job1)
        self.assertIsNone(aviso1)

        job2, aviso2 = try_acquire_lock('docente_2')
        self.assertIsNone(job2)
        self.assertIsNone(aviso2)

    def test_al_liberar_el_candado_el_siguiente_usuario_si_puede_tomarlo(self):
        job1, _ = try_acquire_lock('docente_1')
        release_lock(job1)

        job2, aviso2 = try_acquire_lock('docente_2')
        self.assertIsNotNone(job2)
        self.assertIsNone(aviso2)

    def test_candado_vencido_se_libera_solo_y_avisa_quien_lo_tenia(self):
        job1, _ = try_acquire_lock('docente_1')
        vencido = timezone.now() - timedelta(seconds=LOCK_TIMEOUT_SECONDS + 10)
        TrabajoExtraccion.objects.filter(pk=1, job_id=job1).update(iniciado=vencido)

        job2, aviso2 = try_acquire_lock('docente_2')
        self.assertIsNotNone(job2)
        self.assertNotEqual(job2, job1)
        self.assertIn('docente_1', aviso2)
