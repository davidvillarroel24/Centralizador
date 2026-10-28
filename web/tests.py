from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from data.models import Profesor, FechasParciales, PesosCategorias
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

    def test_boton_1_sin_fechas_avisa_antes_de_ir_a_moodle(self):
        with mock.patch('web.views.run_cargar_tareas_web') as extraer:
            respuesta = self._post_xhr('cargar_tareas')
        datos = respuesta.json()
        extraer.assert_not_called()
        self.assertIn('no de Moodle', datos['error'])
        self.assertEqual(datos['error_link']['url'], reverse('configuracion'))

    def test_boton_1_con_fechas_no_frena_por_configuracion(self):
        FechasParciales.objects.create(profesor=self.profesor, p1_inicio='2026-09-01', p1_fin='2026-10-15')
        respuesta = self._post_xhr('cargar_tareas')
        datos = respuesta.json()
        # Sin cookie sigue sin poder extraer, pero el motivo ya no es la configuración.
        self.assertIn('cookie', datos['error'].lower())
        self.assertIsNone(datos['error_link'])

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
        PesosCategorias.objects.create(profesor=self.profesor, mitek=40, etek=60)
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


class ConfiguracionIncompletaTests(TestCase):
    def test_asignar_sin_fechas_lanza_configuracion_incompleta(self):
        with self.assertRaises(run_scraping.ConfiguracionIncompleta):
            run_scraping.asignacion_tareas([1], config_base={'rangos_parciales': [{'parcial': 1, 'inicio': None, 'fin': None}]})

    def test_estudiantes_sin_pesos_lanza_configuracion_incompleta(self):
        with self.assertRaises(run_scraping.ConfiguracionIncompleta):
            run_scraping.estudiantes([1], profesor_id=999999)
