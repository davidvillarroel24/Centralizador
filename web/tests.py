from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from data.models import (
    Profesor, FechasParciales, PesosCategorias, asegurar_config_tareas_default,
    Facultad, Carrera, Materia, Unidad, Tarea, Estudiante, Entrega, PerfilUsuario,
)
from services.utils import run_scraping

# El storage de produccion (manifiesto de WhiteNoise) exige correr collectstatic antes de
# poder renderizar cualquier {% static %}; en tests alcanza con el storage simple.
SIN_MANIFIESTO = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


@override_settings(STORAGES=SIN_MANIFIESTO)
class PreparacionExtraccionTests(TestCase):
    """Fase 1 de la guía de uso: avisos claros antes de extraer y botones de Moodle
    deshabilitados mientras no haya cookie."""

    def setUp(self):
        self.user = User.objects.create_user(username='docente.prueba', password='clave-123')
        self.profesor = Profesor.objects.create(
            moodle_id=424242, nombre='docente.prueba', url='https://moodle.example/user/view.php?id=424242',
            user=self.user,
        )
        self.client.force_login(self.user)

    def _post_xhr(self, action, **extra):
        datos = {'action': action, 'courses': ['1'], 'role': 'all', **extra}
        return self.client.post(reverse('dashboard'), datos, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

    def test_boton_1_sin_fechas_usa_el_default_institucional_en_vez_de_bloquear(self):
        # Antes esto frenaba con "faltan fechas" (ver asegurar_config_tareas_default en
        # data/models.py): ahora un docente que nunca entro a Configuracion ya tiene
        # fechas/pesos default del año en curso, asi que no lo frena mas - el error
        # restante es el de cookie, igual que en test_boton_1_con_fechas_no_frena_por_configuracion.
        respuesta = self._post_xhr('cargar_tareas')
        datos = respuesta.json()
        self.assertIn('cookie', datos['error'].lower())
        self.assertIsNone(datos['error_link'])

    def test_boton_1_con_fechas_no_frena_por_configuracion(self):
        FechasParciales.objects.create(profesor=self.profesor, p1_inicio='2026-09-01', p1_fin='2026-10-15')
        respuesta = self._post_xhr('cargar_tareas')
        datos = respuesta.json()
        # Sin cookie sigue sin poder extraer, pero el motivo ya no es la configuración.
        self.assertIn('cookie', datos['error'].lower())
        self.assertIsNone(datos['error_link'])

    def test_default_solo_completa_campos_sin_configurar(self):
        # Parcial 1 ya tiene fecha (de un año cualquiera, no tiene que ser el actual) y
        # mitek/etek ya tienen peso propio: eso no se toca. Parcial 2-4 y las otras 3
        # categorias nunca se configuraron, asi que esos si se completan con el default.
        FechasParciales.objects.create(profesor=self.profesor, p1_inicio='2020-03-01', p1_fin='2020-04-20')
        PesosCategorias.objects.create(profesor=self.profesor, mitek=15, etek=25)

        fechas, pesos = asegurar_config_tareas_default(self.profesor)

        self.assertEqual(fechas.p1_inicio.isoformat(), '2020-03-01')
        self.assertEqual(fechas.p1_fin.isoformat(), '2020-04-20')
        self.assertIsNotNone(fechas.p2_inicio)
        self.assertIsNotNone(fechas.p4_fin)
        self.assertEqual(pesos.mitek, 15)
        self.assertEqual(pesos.etek, 25)
        self.assertEqual(pesos.training, 20)
        self.assertEqual(pesos.designlab, 20)
        self.assertEqual(pesos.examen, 30)

    def test_sin_cookie_los_botones_de_moodle_estan_deshabilitados(self):
        respuesta = self.client.get(reverse('dashboard'))
        self.assertFalse(respuesta.context['preparacion']['cookie_ok'])
        html = respuesta.content.decode()
        self.assertEqual(html.count('requiere-cookie" disabled'), 4)

    def test_con_cookie_los_botones_de_moodle_estan_habilitados(self):
        # La sesion usa signed_cookies (no se puede editar desde el test client): se usa el
        # otro camino real, la cookie cifrada guardada en el Profesor, todavia vigente.
        self.profesor.moodle_cookie_cifrada = 'cifrada-de-prueba'
        self.profesor.moodle_cookie_guardada_en = timezone.now()
        self.profesor.save()
        respuesta = self.client.get(reverse('dashboard'))
        self.assertTrue(respuesta.context['preparacion']['cookie_ok'])
        self.assertNotIn('requiere-cookie" disabled', respuesta.content.decode())

    def test_lista_antes_de_extraer_refleja_la_configuracion(self):
        FechasParciales.objects.create(profesor=self.profesor, p1_inicio='2026-09-01', p1_fin='2026-10-15')
        # Las 5 categorias con valor propio (ninguna en 0): asegurar_config_tareas_default
        # solo completa con el default institucional lo que esta sin configurar, asi que
        # esto tiene que quedar exactamente como se guardo, sin que nada se le pise.
        PesosCategorias.objects.create(
            profesor=self.profesor, mitek=30, etek=30, training=20, designlab=10, examen=10,
        )
        prep = self.client.get(reverse('dashboard')).context['preparacion']
        self.assertTrue(prep['fechas_ok'])
        self.assertTrue(prep['pesos_ok'])
        self.assertEqual(prep['pesos_total'], 100)
        self.assertFalse(prep['todo_ok'])  # falta la cookie


@override_settings(STORAGES=SIN_MANIFIESTO)
class GuiaDeUsoTests(TestCase):
    """La guía arranca sola la primera vez (Configuración, pasos 1-4), sigue en Extracción
    (pasos 5-10) y deja de salir sola una vez terminada o cerrada."""

    def setUp(self):
        self.user = User.objects.create_user(username='docente.guia', password='clave-123')
        self.profesor = Profesor.objects.create(
            moodle_id=515151, nombre='docente.guia', url='https://moodle.example/user/view.php?id=515151',
            user=self.user,
        )

    def _login(self):
        return self.client.post(reverse('login'), {'username': 'docente.guia', 'password': 'clave-123'})

    def test_login_con_guia_pendiente_lleva_a_la_guia(self):
        self.assertRedirects(self._login(), f"{reverse('configuracion')}?tour=1", fetch_redirect_response=False)

    def test_login_con_guia_vista_lleva_a_resumen(self):
        self.profesor.tour_visto_en = timezone.now()
        self.profesor.save()
        self.assertRedirects(self._login(), reverse('resumen'), fetch_redirect_response=False)

    def test_registro_lleva_a_la_guia(self):
        Profesor.objects.create(moodle_id=616161, nombre='docente.nuevo', url='https://moodle.example/u/616161')
        respuesta = self.client.post(reverse('register'), {'username': 'docente.nuevo', 'password': 'clave-123'})
        self.assertRedirects(respuesta, f"{reverse('configuracion')}?tour=1", fetch_redirect_response=False)

    def test_configuracion_arranca_la_guia_si_esta_pendiente(self):
        self.client.force_login(self.user)
        tour = self.client.get(reverse('configuracion')).context['tour']
        self.assertEqual(tour['iniciar'], 'configuracion')
        self.assertEqual(tour['url_extraccion'], f"{reverse('dashboard')}?tour=extraccion")

    def test_guia_vista_no_arranca_sola_pero_si_desde_el_menu(self):
        self.profesor.tour_visto_en = timezone.now()
        self.profesor.save()
        self.client.force_login(self.user)
        self.assertIsNone(self.client.get(reverse('configuracion')).context['tour']['iniciar'])
        self.assertEqual(
            self.client.get(reverse('configuracion'), {'tour': '1'}).context['tour']['iniciar'], 'configuracion'
        )

    def test_extraccion_sigue_la_guia_solo_con_el_parametro(self):
        self.client.force_login(self.user)
        self.assertIsNone(self.client.get(reverse('dashboard')).context['tour']['iniciar'])
        respuesta = self.client.get(reverse('dashboard'), {'tour': 'extraccion'})
        self.assertEqual(respuesta.context['tour']['iniciar'], 'extraccion')
        self.assertContains(respuesta, 'id="tourConfig"')

    def test_marcar_guia_vista(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(reverse('tour_visto')).json(), {'ok': True})
        self.profesor.refresh_from_db()
        self.assertIsNotNone(self.profesor.tour_visto_en)


@override_settings(STORAGES=SIN_MANIFIESTO)
class ExtraccionDecanoTests(TestCase):
    """Un Decano que además es Docente ve en Extracción su alcance asignado + lo que enseña.
    Antes daba error 500: el alcance del Decano usa .distinct() y Django no deja unir con
    `|` una consulta distinct con otra que no lo es."""

    def setUp(self):
        from data.models import Facultad, Carrera, Materia, PerfilUsuario
        facultad = Facultad.objects.create(nombre='Tecnología')
        sistemas = Carrera.objects.create(facultad=facultad, nombre='Sistemas')
        contaduria = Carrera.objects.create(facultad=facultad, nombre='Contaduría')

        def materia(nombre, carrera):
            return Materia.objects.create(
                gestion=2026, nombre=nombre, moodle_nombre=nombre, moodle_url='https://moodle.example/c', carrera=carrera,
            )
        self.de_su_carrera = materia('Base de Datos', sistemas)
        self.que_dicta = materia('Contabilidad I', contaduria)
        self.ajena = materia('Auditoría', contaduria)

        self.user = User.objects.create_user(username='decano.prueba', password='clave-123')
        profesor = Profesor.objects.create(
            moodle_id=919191, nombre='decano.prueba', url='https://moodle.example/u/919191', user=self.user,
        )
        self.que_dicta.profesores.add(profesor)
        perfil = PerfilUsuario.objects.create(user=self.user, rol=PerfilUsuario.DECANO)
        perfil.carreras.add(sistemas)
        self.client.force_login(self.user)

    def test_decano_docente_abre_extraccion_sin_error(self):
        respuesta = self.client.get(reverse('dashboard'))
        self.assertEqual(respuesta.status_code, 200)
        ids = {c['id'] for c in respuesta.context['courses']}
        self.assertEqual(ids, {self.de_su_carrera.id, self.que_dicta.id})


class ConfiguracionIncompletaTests(TestCase):
    def test_asignar_sin_fechas_lanza_configuracion_incompleta(self):
        with self.assertRaises(run_scraping.ConfiguracionIncompleta):
            run_scraping.asignacion_tareas([1], config_base={'rangos_parciales': [{'parcial': 1, 'inicio': None, 'fin': None}]})

    def test_estudiantes_sin_pesos_lanza_configuracion_incompleta(self):
        with self.assertRaises(run_scraping.ConfiguracionIncompleta):
            run_scraping.estudiantes([1], profesor_id=999999)


@override_settings(STORAGES=SIN_MANIFIESTO)
class MateriaAvancesTests(TestCase):
    """materia_avances (ver web/views.py) por cada rol - el mismo tipo de bug que rompio
    cuando se agregaron las vistas de Decano (505 en extraccion) era un rol que la vista
    nueva no contemplaba bien; esto cubre los 4 roles + materia fuera de alcance."""

    def setUp(self):
        self.facultad = Facultad.objects.create(nombre='Ingeniería')
        self.carrera = Carrera.objects.create(facultad=self.facultad, nombre='Sistemas')
        self.carrera_otra = Carrera.objects.create(facultad=self.facultad, nombre='Civil')

        self.materia = Materia.objects.create(
            gestion=2026, nombre='Bases de Datos', moodle_nombre='2026/BDD',
            moodle_url='https://moodle.example/course/view.php?id=1', carrera=self.carrera,
        )
        self.materia_otra_carrera = Materia.objects.create(
            gestion=2026, nombre='Estructuras', moodle_nombre='2026/EST',
            moodle_url='https://moodle.example/course/view.php?id=2', carrera=self.carrera_otra,
        )
        unidad = Unidad.objects.create(materia=self.materia, nombre='Unidad 1')
        tarea_assign = Tarea.objects.create(
            unidad=unidad, moodle_id=1001, titulo='Práctica 1', tipo='assign',
            url='https://moodle.example/mod/assign/view.php?id=1',
        )
        Tarea.objects.create(
            unidad=unidad, moodle_id=1002, titulo='Material de apoyo', tipo='url',
            url='https://moodle.example/mod/url/view.php?id=1',
        )
        estudiante = Estudiante.objects.create(moodle_userid=5001, nombre='Ana Pérez', email='ana@example.com')
        Entrega.objects.create(tarea=tarea_assign, estudiante=estudiante, estado='Sin entrega')

        self.docente_user = User.objects.create_user(username='docente.prueba2', password='clave-123')
        self.profesor = Profesor.objects.create(
            moodle_id=434343, nombre='docente.prueba2', url='https://moodle.example/user/view.php?id=434343',
            user=self.docente_user,
        )
        self.materia.profesores.add(self.profesor)

        self.decano_user = User.objects.create_user(username='decano.prueba', password='clave-123')
        perfil_decano = PerfilUsuario.objects.create(user=self.decano_user, rol=PerfilUsuario.DECANO)
        perfil_decano.carreras.add(self.carrera)  # NO incluye self.carrera_otra a proposito

        self.admin_user = User.objects.create_user(username='admin.prueba', password='clave-123')
        PerfilUsuario.objects.create(user=self.admin_user, rol=PerfilUsuario.ADMINISTRADOR)

    def _url(self, materia):
        return reverse('materia_avances', args=[materia.id])

    def test_docente_ve_su_propia_materia(self):
        self.client.force_login(self.docente_user)
        resp = self.client.get(self._url(self.materia))
        self.assertEqual(resp.status_code, 200)
        datos = resp.json()
        self.assertEqual(len(datos['actividades']), 2)
        assign = next(a for a in datos['actividades'] if a['tipo'] == 'assign')
        self.assertEqual(assign['total_estudiantes'], 1)
        self.assertEqual(assign['entregas'][0]['estudiante'], 'Ana Pérez')

    def test_docente_no_ve_materia_ajena(self):
        self.client.force_login(self.docente_user)
        resp = self.client.get(self._url(self.materia_otra_carrera))
        self.assertEqual(resp.status_code, 403)

    def test_decano_ve_materia_de_su_carrera(self):
        self.client.force_login(self.decano_user)
        resp = self.client.get(self._url(self.materia))
        self.assertEqual(resp.status_code, 200)

    def test_decano_no_ve_materia_fuera_de_su_alcance(self):
        self.client.force_login(self.decano_user)
        resp = self.client.get(self._url(self.materia_otra_carrera))
        self.assertEqual(resp.status_code, 403)

    def test_administrador_ve_cualquier_materia(self):
        self.client.force_login(self.admin_user)
        resp = self.client.get(self._url(self.materia_otra_carrera))
        self.assertEqual(resp.status_code, 200)

    def test_visitante_no_accede_a_materias(self):
        from data.roles import get_or_crear_visitante_compartido
        visitante = get_or_crear_visitante_compartido()
        self.client.force_login(visitante)
        resp = self.client.get(self._url(self.materia))
        # requiere_rol redirige a resumen (no 403) para roles sin acceso a la pantalla.
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('resumen'))

    def test_anonimo_redirige_a_login(self):
        resp = self.client.get(self._url(self.materia))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

    def test_materia_inexistente_da_404(self):
        self.client.force_login(self.admin_user)
        resp = self.client.get(self._url(self.materia).rsplit('/', 2)[0] + '/999999/avances/')
        self.assertEqual(resp.status_code, 404)
