from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from data.models import (
    Facultad, Carrera, Materia, Unidad, Tarea, Estudiante, Entrega, TrabajoExtraccion, AccesoCurso,
)
from services.data_utils import import_estudiantes_to_db
from services.utils import extraction_lock, reportes
from services.ml import features


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


def _entrega_falsa(cierre_dt, apertura_dt, entrega_dt, categoria=''):
    """Objeto liviano (sin tocar la base) con los mismos atributos que
    features.cargar_entregas_cerradas() deja en cada Entrega real, para probar las
    cuentas de services/ml/features.py sin armar Tarea/Entrega de verdad."""
    atraso_horas = (entrega_dt - cierre_dt).total_seconds() / 3600 if entrega_dt else None
    return SimpleNamespace(
        cierre_dt=cierre_dt, apertura_dt=apertura_dt, entrega_dt=entrega_dt, atraso_horas=atraso_horas,
        tarea=SimpleNamespace(categoria=categoria), tarea_id=1,
    )


class FeaturesAcumulacionTests(SimpleTestCase):
    """Las mismas cuentas que arma exportar_dataset_ml.py fila por fila (ver
    services/ml/features.py), verificadas a mano - es lo que el predictor en vivo
    (services/ml/predictor.py) va a reusar tal cual para no calcular "lo mismo" dos veces
    de formas distintas."""

    def setUp(self):
        # 3 tareas ya cerradas de un mismo estudiante, en orden cronologico: a tiempo,
        # sin entregar, y tarde.
        self.entregas = [
            _entrega_falsa(
                datetime(2025, 1, 1, 10, 0), datetime(2024, 12, 25, 10, 0),
                datetime(2024, 12, 31, 9, 0), categoria='etek',
            ),  # a tiempo
            _entrega_falsa(
                datetime(2025, 1, 8, 10, 0), datetime(2025, 1, 1, 10, 0),
                None, categoria='mitek',
            ),  # sin entregar
            _entrega_falsa(
                datetime(2025, 1, 15, 10, 0), datetime(2025, 1, 8, 10, 0),
                datetime(2025, 1, 15, 12, 0), categoria='training',
            ),  # tarde (2hs despues del cierre)
        ]

    def test_historial_acumulado_cuenta_atrasos_y_sin_entrega_por_separado(self):
        n_previas, n_atrasos, n_sin_entrega = features.historial_acumulacion_hasta_ahora(self.entregas)
        self.assertEqual((n_previas, n_atrasos, n_sin_entrega), (3, 1, 1))

    def test_fila_acumulacion_calcula_dia_hora_anticipacion_y_categoria_onehot(self):
        fila = features.fila_acumulacion(self.entregas[0], n_previas=0, n_atrasos_previos=0, n_sin_entrega_previos=0)
        self.assertEqual(fila['dia_semana_cierre'], datetime(2025, 1, 1, 10, 0).weekday())
        self.assertEqual(fila['hora_cierre'], 10)
        self.assertEqual(fila['anticipacion_horas'], 168.0)  # 7 dias de apertura a cierre
        self.assertIsNone(fila['pct_atrasos_previos'])  # primera tarea: sin historial previo
        self.assertEqual(fila['categoria_etek'], 1)
        self.assertEqual(fila['categoria_mitek'], 0)

    def test_fila_acumulacion_usa_el_historial_pasado_como_porcentaje(self):
        fila = features.fila_acumulacion(self.entregas[2], n_previas=2, n_atrasos_previos=0, n_sin_entrega_previos=1)
        self.assertEqual(fila['n_tareas_previas'], 2)
        self.assertEqual(fila['pct_atrasos_previos'], 0.0)
        self.assertEqual(fila['pct_sin_entrega_previos'], 0.5)

    def test_entrego_tarde_distingue_a_tiempo_sin_entregar_y_tarde(self):
        self.assertFalse(features.entrego_tarde(self.entregas[0]))  # a tiempo
        self.assertTrue(features.entrego_tarde(self.entregas[1]))  # sin entregar
        self.assertTrue(features.entrego_tarde(self.entregas[2]))  # tarde


class FeaturesInactividadTests(SimpleTestCase):
    """Mismas cuentas que exportar_dataset_ml.py arma para el modelo de inactividad,
    verificadas a mano."""

    def setUp(self):
        base = datetime(2025, 1, 1, 10, 0)
        # 3 eventos de entrega real, con 5 y 15 dias de brecha entre ellos.
        self.eventos = [
            _entrega_falsa(base, base - timedelta(days=7), base),
            _entrega_falsa(base + timedelta(days=5), base + timedelta(days=4), base + timedelta(days=5)),
            _entrega_falsa(base + timedelta(days=20), base + timedelta(days=19), base + timedelta(days=20)),
        ]

    def test_fila_posicional_del_ultimo_evento_usa_los_previos(self):
        actual = self.eventos[2]
        previos = self.eventos[:2]
        fila = features.fila_inactividad_posicional(actual, previos, self.eventos)
        # brecha entre el evento 0 y el 1 (los unicos dos previos) = 5 dias.
        self.assertEqual(fila['brecha_anterior_dias'], 5.0)
        self.assertEqual(fila['brecha_promedio_previa_dias'], 5.0)
        # ambos previos (20 y 15 dias antes del actual) caen dentro de la ventana de 30d.
        self.assertEqual(fila['entregas_ultimos_30d'], 2)
        self.assertEqual(fila['tareas_publicadas_por_profesor_30d'], 3)

    def test_fila_posicional_del_primer_evento_no_tiene_brecha_previa(self):
        fila = features.fila_inactividad_posicional(self.eventos[0], [], self.eventos)
        self.assertIsNone(fila['brecha_anterior_dias'])
        self.assertIsNone(fila['brecha_promedio_previa_dias'])
        self.assertEqual(fila['entregas_ultimos_30d'], 0)

    def test_anticipacion_horas_de_un_evento_puntual(self):
        self.assertEqual(features.anticipacion_horas_de(self.eventos[1]), 24.0)

    def test_eventos_de_acceso_simulado_descarta_los_sin_entrega_y_ordena(self):
        sin_entrega = _entrega_falsa(datetime(2025, 2, 1), datetime(2025, 1, 25), None)
        desordenado = [self.eventos[2], sin_entrega, self.eventos[0], self.eventos[1]]
        ordenado = features.eventos_de_acceso_simulado(desordenado)
        self.assertEqual(ordenado, self.eventos)


class EstudiantesInactivosEstaticoTests(TestCase):
    """estudiantes_inactivos_por_materia/estudiantes_inactivos_general
    (services/utils/reportes.py): indicador de inactividad real (AccesoCurso), no el
    proxy del modelo entrenado. "Por materia" mira cada (estudiante, materia) por
    separado; "general" usa el acceso más reciente del estudiante entre TODAS sus
    materias, para no marcarlo inactivo si entra seguido a una en particular."""

    def setUp(self):
        carrera = Carrera.objects.create(facultad=Facultad.objects.create(nombre='Ingeniería'), nombre='Sistemas')
        self.materia_a = Materia.objects.create(
            gestion=2026, nombre='Materia A', moodle_nombre='A',
            moodle_url='https://moodle.example/a', carrera=carrera,
        )
        self.materia_b = Materia.objects.create(
            gestion=2026, nombre='Materia B', moodle_nombre='B',
            moodle_url='https://moodle.example/b', carrera=carrera,
        )
        self.est_x = Estudiante.objects.create(moodle_userid=501, nombre='Estudiante X', email='x@example.com')
        self.est_y = Estudiante.objects.create(moodle_userid=502, nombre='Estudiante Y', email='y@example.com')

        ahora = timezone.now()

        def _acceso(materia, moodle_userid, texto_hace):
            acceso = AccesoCurso.objects.create(materia=materia, moodle_userid=moodle_userid, ultimo_acceso=texto_hace)
            # actualizado es auto_now: se fuerza a mano para simular "esto se extrajo justo ahora".
            AccesoCurso.objects.filter(pk=acceso.pk).update(actualizado=ahora)

        _acceso(self.materia_a, 501, '40 dias 0 horas')  # X: inactivo en A
        _acceso(self.materia_b, 501, '2 dias 0 horas')   # X: activo en B (hace poco)
        _acceso(self.materia_a, 502, '60 dias 0 horas')  # Y: inactivo en A (su única materia)

    def test_por_materia_detecta_inactividad_puntual(self):
        filas = reportes.estudiantes_inactivos_por_materia(Materia.objects.all())
        materias_x = {f['materia'] for f in filas if f['estudiante_id'] == self.est_x.id}
        self.assertEqual(materias_x, {'Materia A'})  # no "Materia B": ahí entró hace 2 días
        materias_y = {f['materia'] for f in filas if f['estudiante_id'] == self.est_y.id}
        self.assertEqual(materias_y, {'Materia A'})

    def test_general_usa_el_acceso_mas_reciente_entre_todas_las_materias(self):
        ids_inactivos = {f['estudiante_id'] for f in reportes.estudiantes_inactivos_general(Materia.objects.all())}
        self.assertNotIn(self.est_x.id, ids_inactivos)  # activo en general: entró a B hace 2 días
        self.assertIn(self.est_y.id, ids_inactivos)  # inactivo en general: su única materia, hace 60 días
