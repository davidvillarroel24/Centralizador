from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from data.models import (
    Profesor, FechasParciales, PesosCategorias, asegurar_config_tareas_default,
    Facultad, Carrera, Materia, Unidad, Tarea, Estudiante, Entrega, PerfilUsuario, ArchivoTarea,
    PrediccionRiesgo, ConfiguracionInstitucional, AccesoCurso, RestablecimientoContrasena,
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
class ReasignarAutomaticoTests(TestCase):
    """'Asignar automáticamente' del modal "Revisar asignación" (ver
    run_reasignar_automatico_web en web/views.py): recalcula categoría/parcial por fecha de
    cierre con la config ACTUAL, sin pasar por Moodle - para cuando esa config tenía una
    fecha mal puesta (ej. un año equivocado) y se corrigió después (bug reportado
    2026-11-10)."""

    def setUp(self):
        self.user = User.objects.create_user(username='docente.reasignar', password='clave-123')
        self.profesor = Profesor.objects.create(
            moodle_id=434343, nombre='docente.reasignar', url='https://moodle.example/user/view.php?id=434343',
            user=self.user,
        )
        facultad = Facultad.objects.create(nombre='Ingeniería Reasignar')
        carrera = Carrera.objects.create(facultad=facultad, nombre='Sistemas Reasignar')
        self.materia = Materia.objects.create(
            moodle_nombre='Materia Reasignar 2026', nombre='Materia Reasignar', gestion=2026, carrera=carrera,
        )
        self.materia.profesores.add(self.profesor)
        unidad = Unidad.objects.create(materia=self.materia, nombre='U1')
        self.tarea = Tarea.objects.create(
            unidad=unidad, moodle_id=919191, titulo='Examen final', tipo='assign',
            cierre='miércoles, 11 de marzo de 2026, 23:59',
            url='https://moodle.example/mod/assign/view.php?id=919191',
        )
        self.client.force_login(self.user)

    def _post_xhr(self, action, **extra):
        datos = {'action': action, 'courses': [str(self.materia.id)], 'role': 'all', **extra}
        return self.client.post(reverse('dashboard'), datos, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

    def test_recalcula_sin_volver_a_extraer_tras_corregir_las_fechas(self):
        # Fechas mal configuradas (2025) mientras la tarea es de 2026: la tarea queda sin
        # categoria/parcial.
        FechasParciales.objects.create(profesor=self.profesor, p1_inicio='2025-01-01', p1_fin='2025-04-01')
        PesosCategorias.objects.create(profesor=self.profesor, examen=100)
        self._post_xhr('reasignar_automatico')
        self.tarea.refresh_from_db()
        self.assertIsNone(self.tarea.parcial)
        self.assertIsNone(self.tarea.categoria)

        # Se corrigen las fechas (2026, sin tocar nada más) y se reasigna de nuevo sin
        # pasar por "1." (sin cookie, sin Moodle): la tarea ahora sí debe quedar asignada.
        FechasParciales.objects.filter(profesor=self.profesor).update(p1_inicio='2026-01-01', p1_fin='2026-04-01')
        respuesta = self._post_xhr('reasignar_automatico')
        datos = respuesta.json()
        self.assertIsNone(datos['error'])
        self.assertTrue(datos['abrir_modal_asignacion'])
        self.tarea.refresh_from_db()
        self.assertEqual(self.tarea.parcial, 1)
        self.assertEqual(self.tarea.categoria, 'examen')

    def test_sin_cursos_seleccionados_da_error_claro(self):
        respuesta = self._post_xhr('reasignar_automatico', courses=[])
        self.assertEqual(respuesta.json()['error'], 'Debes seleccionar al menos un curso para reasignar.')


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
        respuesta = self.client.post(reverse('register'), {
            'username': 'docente.nuevo', 'password': 'clave-123-segura', 'password_confirmar': 'clave-123-segura',
        })
        self.assertRedirects(respuesta, f"{reverse('configuracion')}?tour=1", fetch_redirect_response=False)

    def test_registro_rechaza_contrasenas_que_no_coinciden(self):
        Profesor.objects.create(moodle_id=616162, nombre='docente.nuevo2', url='https://moodle.example/u/616162')
        respuesta = self.client.post(reverse('register'), {
            'username': 'docente.nuevo2', 'password': 'clave-123-segura', 'password_confirmar': 'otra-cosa',
        })
        self.assertEqual(respuesta.context['error'], 'Las contraseñas no coinciden.')
        self.assertFalse(User.objects.filter(username='docente.nuevo2').exists())

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
class LoginSinProfesorTests(TestCase):
    """El Administrador inicial se crea directo (no autoregistrado) y nunca tiene un
    Profesor vinculado con su mismo nombre de usuario - el chequeo "el usuario debe
    coincidir con un docente registrado" es para el flujo de autoregistro (ver
    register_view) y no debería bloquear su login (bug reportado 2026-11-20: la cuenta
    admin "tecba" no podía entrar ni guardar su cookie). Un Decano, en cambio, SIEMPRE tiene
    Profesor: nace de ascender a un docente ya autoregistrado (gestionar_rol_docente exige
    profesor.user, nunca crea una cuenta nueva) - no necesita (ni debe) esta excepción."""

    def test_administrador_sin_profesor_puede_iniciar_sesion(self):
        user = User.objects.create_user(username='admin.sinperfil', password='clave-123')
        PerfilUsuario.objects.create(user=user, rol=PerfilUsuario.ADMINISTRADOR)
        respuesta = self.client.post(reverse('login'), {'username': 'admin.sinperfil', 'password': 'clave-123'})
        # 302 a Resumen o a la guía de uso (primera vez): lo que importa es que NO vuelva a
        # mostrar el formulario de login con el error de "docente registrado".
        self.assertEqual(respuesta.status_code, 302)

    def test_decano_real_siempre_tiene_profesor_y_puede_iniciar_sesion(self):
        # Caso real: un Decano nace de un Profesor ya autoregistrado (mismo username que su
        # Profesor.nombre), nunca de una cuenta nueva - esto ya funcionaba sin ninguna
        # excepción especial y debe seguir así.
        user = User.objects.create_user(username='decano.prueba', password='clave-123')
        Profesor.objects.create(
            moodle_id=777777, nombre='decano.prueba',
            url='https://moodle.example/user/view.php?id=777777', user=user,
        )
        PerfilUsuario.objects.create(user=user, rol=PerfilUsuario.DECANO)
        respuesta = self.client.post(reverse('login'), {'username': 'decano.prueba', 'password': 'clave-123'})
        self.assertEqual(respuesta.status_code, 302)

    def test_decano_sin_profesor_sigue_bloqueado(self):
        # Esto no debería poder pasar por la UI real (gestionar_rol_docente exige
        # profesor.user), pero si alguna vez ocurre (dato corrupto, migración manual...) no
        # hay que tratarlo como caso válido igual que al Administrador - sigue exigiendo el
        # mismo chequeo que cualquier cuenta sin Profesor.
        user = User.objects.create_user(username='decano.sinperfil', password='clave-123')
        PerfilUsuario.objects.create(user=user, rol=PerfilUsuario.DECANO)
        respuesta = self.client.post(reverse('login'), {'username': 'decano.sinperfil', 'password': 'clave-123'})
        self.assertEqual(respuesta.context['error'], 'El usuario debe coincidir con un docente registrado.')

    def test_docente_que_no_coincide_con_ningun_profesor_sigue_bloqueado(self):
        # El chequeo sigue vigente para quien no es Administrador: evita loguearse con una
        # cuenta que no corresponde a ningun docente real.
        User.objects.create_user(username='nadie.conocido', password='clave-123')
        respuesta = self.client.post(reverse('login'), {'username': 'nadie.conocido', 'password': 'clave-123'})
        self.assertEqual(respuesta.context['error'], 'El usuario debe coincidir con un docente registrado.')

    def test_administrador_sin_profesor_puede_guardar_su_cookie(self):
        user = User.objects.create_user(username='admin.cookie', password='clave-123')
        PerfilUsuario.objects.create(user=user, rol=PerfilUsuario.ADMINISTRADOR)
        self.client.force_login(user)
        respuesta = self.client.post(
            reverse('guardar_cookie_extension'),
            data='{"cookie": "cookie-del-admin"}',
            content_type='application/json',
        )
        self.assertEqual(respuesta.json(), {'ok': True})
        profesor = Profesor.objects.get(user=user)
        self.assertIsNotNone(profesor.moodle_cookie_cifrada)


@override_settings(STORAGES=SIN_MANIFIESTO)
class RestablecerPasswordTests(TestCase):
    """Recuperación de contraseña sin correo (Fase A, decisión 2026-11-27): el
    Administrador le restablece la contraseña a un docente desde Docentes, lo que genera un
    código de 6 dígitos que el docente usa en /recuperar/ para elegir una nueva."""

    def setUp(self):
        self.admin = User.objects.create_user(username='admin.reset', password='clave-123')
        PerfilUsuario.objects.create(user=self.admin, rol=PerfilUsuario.ADMINISTRADOR)

        self.docente_user = User.objects.create_user(username='docente.reset', password='vieja-clave-123')
        self.profesor = Profesor.objects.create(
            moodle_id=9001, nombre='docente.reset',
            url='https://moodle.example/user/view.php?id=9001', user=self.docente_user,
        )

    def test_admin_restablece_password_genera_codigo_e_invalida_la_vieja(self):
        self.client.force_login(self.admin)
        resp = self.client.post(reverse('restablecer_password_docente'), {'profesor_id': self.profesor.id})
        data = resp.json()
        self.assertTrue(data['ok'])
        self.assertEqual(len(data['codigo']), 6)
        self.assertTrue(data['codigo'].isdigit())

        self.docente_user.refresh_from_db()
        self.assertFalse(self.docente_user.has_usable_password())
        self.assertTrue(RestablecimientoContrasena.objects.filter(profesor=self.profesor).exists())

    def test_no_admin_no_puede_restablecer_password(self):
        self.client.force_login(self.docente_user)
        resp = self.client.post(reverse('restablecer_password_docente'), {'profesor_id': self.profesor.id})
        self.assertNotEqual(resp.status_code, 200)

    def test_restablecer_password_sin_cuenta_da_error(self):
        sin_cuenta = Profesor.objects.create(
            moodle_id=9002, nombre='sin.cuenta', url='https://moodle.example/user/view.php?id=9002',
        )
        self.client.force_login(self.admin)
        resp = self.client.post(reverse('restablecer_password_docente'), {'profesor_id': sin_cuenta.id})
        data = resp.json()
        self.assertFalse(data['ok'])

    def _generar_codigo(self):
        self.client.force_login(self.admin)
        data = self.client.post(reverse('restablecer_password_docente'), {'profesor_id': self.profesor.id}).json()
        self.client.logout()
        return data['codigo']

    def test_recuperar_con_codigo_correcto_actualiza_la_password(self):
        codigo = self._generar_codigo()
        resp = self.client.post(reverse('recuperar_password'), {
            'username': 'docente.reset', 'codigo': codigo,
            'password': 'Nueva-Clave-456!', 'password_confirmar': 'Nueva-Clave-456!',
        })
        self.assertIn('Contraseña actualizada', resp.context['mensaje'])
        self.docente_user.refresh_from_db()
        self.assertTrue(self.docente_user.check_password('Nueva-Clave-456!'))
        self.assertFalse(RestablecimientoContrasena.objects.filter(profesor=self.profesor).exists())

    def test_recuperar_con_codigo_incorrecto_no_actualiza_nada(self):
        self._generar_codigo()
        resp = self.client.post(reverse('recuperar_password'), {
            'username': 'docente.reset', 'codigo': '000000',
            'password': 'Nueva-Clave-456!', 'password_confirmar': 'Nueva-Clave-456!',
        })
        self.assertEqual(resp.context['error'], 'Usuario o código incorrectos.')
        self.docente_user.refresh_from_db()
        self.assertFalse(self.docente_user.has_usable_password())

    def test_recuperar_bloquea_tras_demasiados_intentos_fallidos(self):
        self._generar_codigo()
        for _ in range(RestablecimientoContrasena.MAX_INTENTOS):
            self.client.post(reverse('recuperar_password'), {
                'username': 'docente.reset', 'codigo': '000000',
                'password': 'x', 'password_confirmar': 'x',
            })
        restablecimiento = RestablecimientoContrasena.objects.get(profesor=self.profesor)
        self.assertFalse(restablecimiento.vigente())

        resp = self.client.post(reverse('recuperar_password'), {
            'username': 'docente.reset', 'codigo': '111111',
            'password': 'Nueva-Clave-456!', 'password_confirmar': 'Nueva-Clave-456!',
        })
        self.assertIn('venció', resp.context['error'])

    def test_recuperar_codigo_vencido_falla(self):
        codigo = self._generar_codigo()
        restablecimiento = RestablecimientoContrasena.objects.get(profesor=self.profesor)
        restablecimiento.expira_en = timezone.now() - timedelta(minutes=1)
        restablecimiento.save(update_fields=['expira_en'])

        resp = self.client.post(reverse('recuperar_password'), {
            'username': 'docente.reset', 'codigo': codigo,
            'password': 'Nueva-Clave-456!', 'password_confirmar': 'Nueva-Clave-456!',
        })
        self.assertIn('venció', resp.context['error'])

    def test_recuperar_passwords_no_coinciden(self):
        codigo = self._generar_codigo()
        resp = self.client.post(reverse('recuperar_password'), {
            'username': 'docente.reset', 'codigo': codigo,
            'password': 'Nueva-Clave-456!', 'password_confirmar': 'Otra-Cosa-789!',
        })
        self.assertEqual(resp.context['error'], 'Las contraseñas no coinciden.')

    def test_recuperar_rechaza_password_debil(self):
        codigo = self._generar_codigo()
        resp = self.client.post(reverse('recuperar_password'), {
            'username': 'docente.reset', 'codigo': codigo,
            'password': '12345678', 'password_confirmar': '12345678',
        })
        self.assertIsNotNone(resp.context['error'])
        self.docente_user.refresh_from_db()
        self.assertFalse(self.docente_user.has_usable_password())


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

    def test_entrega_incluye_texto_en_linea_cuando_lo_tiene(self):
        tarea = Tarea.objects.create(
            unidad=Unidad.objects.create(materia=self.materia, nombre='Unidad 2'),
            moodle_id=1003, titulo='Práctica con texto', tipo='assign',
            url='https://moodle.example/mod/assign/view.php?id=2',
        )
        estudiante = Estudiante.objects.create(moodle_userid=5002, nombre='Luis Soria', email='luis@example.com')
        Entrega.objects.create(
            tarea=tarea, estudiante=estudiante, estado='Enviado para calificar',
            texto_en_linea='Este es el link\nhttps://drive.example/x',
        )
        self.client.force_login(self.docente_user)
        resp = self.client.get(self._url(self.materia))
        datos = resp.json()
        act = next(a for a in datos['actividades'] if a['titulo'] == 'Práctica con texto')
        entrega = act['entregas'][0]
        self.assertEqual(entrega['texto_en_linea'], 'Este es el link\nhttps://drive.example/x')

        # La otra entrega (sin texto en línea) no debe traer basura en ese campo.
        otra_act = next(a for a in datos['actividades'] if a['titulo'] == 'Práctica 1')
        self.assertIsNone(otra_act['entregas'][0]['texto_en_linea'])

    def test_materia_inexistente_da_404(self):
        self.client.force_login(self.admin_user)
        resp = self.client.get(self._url(self.materia).rsplit('/', 2)[0] + '/999999/avances/')
        self.assertEqual(resp.status_code, 404)


@override_settings(STORAGES=SIN_MANIFIESTO)
class PrevisualizarArchivoTests(TestCase):
    """previsualizar_archivo: de dónde saca la cookie de Moodle. Solo la de quien está
    mirando (sesión o la guardada en su Profesor) - nunca la de otro docente, aunque dicte
    esa materia y tenga una vigente."""

    def setUp(self):
        from data.cookie_crypto import cifrar_cookie
        self.cifrar_cookie = cifrar_cookie

        carrera = Carrera.objects.create(facultad=Facultad.objects.create(nombre='Ingeniería'), nombre='Sistemas')
        self.materia = Materia.objects.create(
            gestion=2026, nombre='Bases de Datos', moodle_nombre='2026/BDD',
            moodle_url='https://moodle.example/course/view.php?id=1', carrera=carrera,
        )
        tarea = Tarea.objects.create(
            unidad=Unidad.objects.create(materia=self.materia, nombre='Unidad 1'),
            moodle_id=2001, titulo='Práctica 1', tipo='assign',
            url='https://moodle.example/mod/assign/view.php?id=1',
        )
        self.archivo = ArchivoTarea.objects.create(
            tarea=tarea, nombre='enunciado.pdf', url='https://moodle.example/pluginfile.php/1/enunciado.pdf',
        )

        self.admin_user = User.objects.create_user(username='admin.preview', password='clave-123')
        PerfilUsuario.objects.create(user=self.admin_user, rol=PerfilUsuario.ADMINISTRADOR)
        self.admin_profesor = Profesor.objects.create(
            moodle_id=515151, nombre='admin.preview', url='https://moodle.example/user/view.php?id=515151',
            user=self.admin_user,
        )

    def _guardar_cookie_admin(self, cookie, hace=timedelta(0)):
        self.admin_profesor.moodle_cookie_cifrada = self.cifrar_cookie(self.admin_user, cookie)
        self.admin_profesor.moodle_cookie_guardada_en = timezone.now() - hace
        self.admin_profesor.save()

    def _cookie_en_sesion(self, cookie):
        sesion = self.client.session
        sesion['MoodleSession'] = cookie
        sesion.save()
        # Con SESSION_ENGINE signed_cookies la sesión ES la cookie: hay que reponerla a mano.
        self.client.cookies[settings.SESSION_COOKIE_NAME] = sesion.session_key

    def _moodle(self, cookies_validas):
        """requests.get falso: con una cookie de cookies_validas devuelve el PDF; con
        cualquier otra imita a Moodle, que redirige a su login (HTML con 200)."""
        def get(url, cookies=None, **kwargs):
            respuesta = mock.MagicMock(ok=True)
            if cookies['MoodleSession'] in cookies_validas:
                respuesta.headers = {'Content-Type': 'application/pdf'}
                respuesta.iter_content.return_value = [b'%PDF-1.4 contenido']
            else:
                respuesta.headers = {'Content-Type': 'text/html; charset=utf-8'}
                respuesta.iter_content.return_value = [b'<html>login</html>']
            return respuesta
        return mock.patch('web.views.requests.get', side_effect=get)

    def _get(self):
        return self.client.get(reverse('previsualizar_archivo', args=['tarea', self.archivo.id]))

    def test_administrador_usa_su_propia_cookie_aunque_no_dicte_la_materia(self):
        self._guardar_cookie_admin('cookie-admin')
        self.client.force_login(self.admin_user)
        with self._moodle({'cookie-admin'}):
            resp = self._get()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b'%PDF-1.4 contenido')

    def test_usa_la_cookie_de_la_sesion_actual(self):
        self.client.force_login(self.admin_user)
        self._cookie_en_sesion('cookie-sesion')
        with self._moodle({'cookie-sesion'}):
            resp = self._get()
        self.assertEqual(resp.status_code, 200)

    def test_nunca_usa_la_cookie_de_otro_docente_de_la_materia(self):
        user = User.objects.create_user(username='docente.ajeno', password='clave-123')
        docente = Profesor.objects.create(
            moodle_id=525252, nombre='docente.ajeno', url='https://moodle.example/user/view.php?id=525252',
            user=user, moodle_cookie_cifrada=self.cifrar_cookie(user, 'cookie-ajena'),
            moodle_cookie_guardada_en=timezone.now(),
        )
        self.materia.profesores.add(docente)
        self.client.force_login(self.admin_user)
        with self._moodle({'cookie-ajena'}) as get:
            resp = self._get()
        self.assertEqual(resp.status_code, 409)
        get.assert_not_called()

    def test_si_la_de_sesion_murio_en_moodle_prueba_la_guardada(self):
        self._guardar_cookie_admin('cookie-guardada')
        self.client.force_login(self.admin_user)
        self._cookie_en_sesion('cookie-muerta')
        with self._moodle({'cookie-guardada'}):
            resp = self._get()
        self.assertEqual(resp.status_code, 200)

    def test_login_de_moodle_no_se_devuelve_como_si_fuera_el_archivo(self):
        self._guardar_cookie_admin('cookie-muerta')
        self.client.force_login(self.admin_user)
        with self._moodle(set()):
            resp = self._get()
        self.assertEqual(resp.status_code, 409)
        self.assertIn('Moodle rechazó', resp.json()['error'])

    def test_sin_ninguna_cookie_avisa_que_hay_que_capturarla(self):
        self.client.force_login(self.admin_user)
        with self._moodle(set()) as get:
            resp = self._get()
        self.assertEqual(resp.status_code, 409)
        get.assert_not_called()

    def test_cookie_guardada_vencida_no_se_usa(self):
        self._guardar_cookie_admin('cookie-vieja', hace=timedelta(hours=3))
        self.client.force_login(self.admin_user)
        with self._moodle({'cookie-vieja'}) as get:
            resp = self._get()
        self.assertEqual(resp.status_code, 409)
        get.assert_not_called()


@override_settings(STORAGES=SIN_MANIFIESTO)
class RecalcularPrediccionesTests(TestCase):
    """Botón 'Recalcular predicciones' (/predicciones/): corre los 2 modelos ya
    entrenados (services/ml/predictor.py) sobre el estado actual y pisa por completo las
    PrediccionRiesgo de cada tipo. Usa los .joblib reales del repo, no un mock - esto
    también sirve de prueba de que el pipeline de inferencia corre de punta a punta."""

    def setUp(self):
        carrera = Carrera.objects.create(facultad=Facultad.objects.create(nombre='Ingeniería'), nombre='Sistemas')
        materia = Materia.objects.create(
            gestion=2026, nombre='Bases de Datos', moodle_nombre='2026/BDD',
            moodle_url='https://moodle.example/course/view.php?id=1', carrera=carrera, activo=True,
        )
        unidad = Unidad.objects.create(materia=materia, nombre='Unidad 1')
        self.estudiante = Estudiante.objects.create(moodle_userid=9001, nombre='Ana Pérez', email='ana9001@example.com')

        # Dos tareas ya cerradas (historial real) con fechas bien separadas, para que el
        # modelo de inactividad tenga una brecha real que evaluar.
        tarea_cerrada_1 = Tarea.objects.create(
            unidad=unidad, moodle_id=9101, titulo='Práctica 1', tipo='assign', categoria='etek',
            apertura='lunes, 25 de diciembre de 2023, 10:00',
            cierre='lunes, 1 de enero de 2024, 10:00',
            url='https://moodle.example/mod/assign/view.php?id=9101',
        )
        Entrega.objects.create(
            tarea=tarea_cerrada_1, estudiante=self.estudiante, estado='Enviado para calificar',
            ultima_mod_entrega='lunes, 1 de enero de 2024, 09:00',
        )
        tarea_cerrada_2 = Tarea.objects.create(
            unidad=unidad, moodle_id=9102, titulo='Práctica 2', tipo='assign', categoria='mitek',
            apertura='lunes, 15 de enero de 2024, 10:00',
            cierre='lunes, 22 de enero de 2024, 10:00',
            url='https://moodle.example/mod/assign/view.php?id=9102',
        )
        Entrega.objects.create(
            tarea=tarea_cerrada_2, estudiante=self.estudiante, estado='Enviado para calificar',
            ultima_mod_entrega='martes, 20 de febrero de 2024, 09:00',  # +29 dias: brecha real
        )

        # Tarea todavia abierta (cierre bien en el futuro) - lo que debe evaluar el
        # modelo de acumulacion.
        self.tarea_abierta = Tarea.objects.create(
            unidad=unidad, moodle_id=9103, titulo='Práctica 3', tipo='assign', categoria='training',
            apertura='lunes, 1 de enero de 2029, 10:00',
            cierre='martes, 1 de enero de 2030, 10:00',
            url='https://moodle.example/mod/assign/view.php?id=9103',
        )
        Entrega.objects.create(tarea=self.tarea_abierta, estudiante=self.estudiante, estado='Sin entrega')

        self.admin_user = User.objects.create_user(username='admin.predicciones', password='clave-123')
        PerfilUsuario.objects.create(user=self.admin_user, rol=PerfilUsuario.ADMINISTRADOR)
        self.docente_user = User.objects.create_user(username='docente.predicciones', password='clave-123')
        PerfilUsuario.objects.create(user=self.docente_user, rol=PerfilUsuario.DOCENTE)

    def _post(self):
        return self.client.post(reverse('recalcular_predicciones'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')

    def test_administrador_puede_recalcular_y_guarda_ambos_modelos(self):
        self.client.force_login(self.admin_user)
        resp = self._post()
        self.assertEqual(resp.status_code, 200)
        datos = resp.json()
        self.assertNotIn('error', datos)

        pred_acum = PrediccionRiesgo.objects.get(
            tipo_modelo=PrediccionRiesgo.ACUMULACION, estudiante=self.estudiante, tarea=self.tarea_abierta,
        )
        self.assertIn(pred_acum.banda, ('bajo', 'medio', 'alto'))
        self.assertTrue(0.0 <= pred_acum.probabilidad <= 1.0)

        pred_inact = PrediccionRiesgo.objects.get(
            tipo_modelo=PrediccionRiesgo.INACTIVIDAD, estudiante=self.estudiante,
        )
        self.assertIsNone(pred_inact.tarea)
        self.assertTrue(0.0 <= pred_inact.probabilidad <= 1.0)

    def test_recalcular_pisa_las_predicciones_anteriores_sin_duplicar(self):
        self.client.force_login(self.admin_user)
        self._post()
        total_primera_vez = PrediccionRiesgo.objects.count()
        self._post()
        self.assertEqual(PrediccionRiesgo.objects.count(), total_primera_vez)

    def test_docente_no_puede_recalcular(self):
        self.client.force_login(self.docente_user)
        resp = self._post()
        self.assertNotEqual(resp.status_code, 200)
        self.assertFalse(PrediccionRiesgo.objects.exists())

    def test_guardar_configuracion_cambia_las_bandas(self):
        self.client.force_login(self.admin_user)
        resp = self.client.post(
            reverse('guardar_configuracion_predicciones'),
            {'banda_riesgo_medio_desde': '0.10', 'banda_riesgo_alto_desde': '0.20', 'sobrecarga_tareas_minimas': '5'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(resp.json(), {'ok': True})
        config_inst = ConfiguracionInstitucional.actual()
        self.assertEqual(float(config_inst.banda_riesgo_medio_desde), 0.10)
        self.assertEqual(float(config_inst.banda_riesgo_alto_desde), 0.20)
        self.assertEqual(config_inst.sobrecarga_tareas_minimas, 5)

    def test_guardar_configuracion_rechaza_medio_mayor_o_igual_a_alto(self):
        self.client.force_login(self.admin_user)
        resp = self.client.post(
            reverse('guardar_configuracion_predicciones'),
            {'banda_riesgo_medio_desde': '0.80', 'banda_riesgo_alto_desde': '0.60', 'sobrecarga_tareas_minimas': '4'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertIn('error', resp.json())


@override_settings(STORAGES=SIN_MANIFIESTO)
class AlertasPrediccionesTests(TestCase):
    """alertas_view: 'Sobrecarga' es una sola fuente de verdad (el modelo de acumulación,
    ver README §11 C14) - vacía hasta la primera corrida, y requiere banda alta + un
    mínimo de tareas pendientes a la vez; no una cuenta manual aparte."""

    def setUp(self):
        carrera = Carrera.objects.create(facultad=Facultad.objects.create(nombre='Ingeniería'), nombre='Sistemas')
        self.materia = Materia.objects.create(
            gestion=2026, nombre='Bases de Datos', moodle_nombre='2026/BDD',
            moodle_url='https://moodle.example/course/view.php?id=1', carrera=carrera, activo=True,
        )
        unidad = Unidad.objects.create(materia=self.materia, nombre='Unidad 1')
        self.estudiante = Estudiante.objects.create(moodle_userid=9201, nombre='Ana Pérez', email='ana9201@example.com')

        self.tarea_abierta = Tarea.objects.create(
            unidad=unidad, moodle_id=9301, titulo='Práctica abierta', tipo='assign', categoria='etek',
            apertura='lunes, 1 de enero de 2029, 10:00', cierre='martes, 1 de enero de 2030, 10:00',
            url='https://moodle.example/mod/assign/view.php?id=9301',
        )
        # 5 tareas sin entregar (>= el minimo default de 4) para que el estudiante
        # cuente como "muchas tareas pendientes".
        for i in range(5):
            tarea = Tarea.objects.create(
                unidad=unidad, moodle_id=9400 + i, titulo=f'Tarea {i}', tipo='assign', categoria='etek',
                cierre='martes, 1 de enero de 2030, 10:00',
                url=f'https://moodle.example/mod/assign/view.php?id={9400 + i}',
            )
            Entrega.objects.create(tarea=tarea, estudiante=self.estudiante, estado='Sin entrega')

        self.admin_user = User.objects.create_user(username='admin.alertas', password='clave-123')
        PerfilUsuario.objects.create(user=self.admin_user, rol=PerfilUsuario.ADMINISTRADOR)
        self.client.force_login(self.admin_user)

    def test_sobrecarga_vacia_sin_predicciones(self):
        resp = self.client.get(reverse('alertas'))
        self.assertFalse(resp.context['alertas_detalle']['sobrecarga_calculada'])

    def test_sobrecarga_aparece_con_banda_alta_y_suficientes_pendientes(self):
        PrediccionRiesgo.objects.create(
            estudiante=self.estudiante, tarea=self.tarea_abierta,
            tipo_modelo=PrediccionRiesgo.ACUMULACION, probabilidad=0.9, banda=PrediccionRiesgo.ALTO,
        )
        resp = self.client.get(reverse('alertas'))
        detalle = resp.context['alertas_detalle']
        self.assertTrue(detalle['sobrecarga_calculada'])
        nombres = [f['estudiante__nombre'] for f in detalle['estudiantes_sobrecarga']]
        self.assertIn('Ana Pérez', nombres)

    def test_sobrecarga_muestra_la_probabilidad_promedio_y_su_banda(self):
        otra_tarea_abierta = Tarea.objects.create(
            unidad=self.tarea_abierta.unidad, moodle_id=9302, titulo='Otra práctica abierta',
            tipo='assign', categoria='mitek',
            apertura='lunes, 1 de enero de 2029, 10:00', cierre='martes, 1 de enero de 2030, 10:00',
            url='https://moodle.example/mod/assign/view.php?id=9302',
        )
        PrediccionRiesgo.objects.create(
            estudiante=self.estudiante, tarea=self.tarea_abierta,
            tipo_modelo=PrediccionRiesgo.ACUMULACION, probabilidad=0.9, banda=PrediccionRiesgo.ALTO,
        )
        PrediccionRiesgo.objects.create(
            estudiante=self.estudiante, tarea=otra_tarea_abierta,
            tipo_modelo=PrediccionRiesgo.ACUMULACION, probabilidad=0.1, banda=PrediccionRiesgo.BAJO,
        )
        resp = self.client.get(reverse('alertas'))
        fila = resp.context['alertas_detalle']['estudiantes_sobrecarga'][0]
        self.assertEqual(fila['probabilidad'], 0.5)  # promedio de 0.9 y 0.1
        self.assertEqual(fila['banda'], PrediccionRiesgo.MEDIO)  # banda del promedio, no siempre "alto"

    def test_sobrecarga_separa_abiertas_de_vencidas(self):
        # Las 5 tareas del setUp cierran en 2030 (abiertas); agrego 2 ya vencidas aparte.
        for i in range(2):
            tarea_vencida = Tarea.objects.create(
                unidad=self.tarea_abierta.unidad, moodle_id=9500 + i, titulo=f'Vencida {i}',
                tipo='assign', categoria='etek', cierre='martes, 1 de enero de 2020, 10:00',
                url=f'https://moodle.example/mod/assign/view.php?id={9500 + i}',
            )
            Entrega.objects.create(tarea=tarea_vencida, estudiante=self.estudiante, estado='Sin entrega')
        PrediccionRiesgo.objects.create(
            estudiante=self.estudiante, tarea=self.tarea_abierta,
            tipo_modelo=PrediccionRiesgo.ACUMULACION, probabilidad=0.9, banda=PrediccionRiesgo.ALTO,
        )
        resp = self.client.get(reverse('alertas'))
        fila = resp.context['alertas_detalle']['estudiantes_sobrecarga'][0]
        self.assertEqual(fila['abiertas'], 5)
        self.assertEqual(fila['vencidas'], 2)
        self.assertEqual(fila['pendientes'], 7)

    def test_filtro_de_anio_excluye_materias_de_otra_gestion(self):
        otra_materia = Materia.objects.create(
            gestion=2025, nombre='Materia Vieja', moodle_nombre='2025/MV',
            moodle_url='https://moodle.example/course/view.php?id=2', carrera=self.materia.carrera, activo=True,
        )
        otra_unidad = Unidad.objects.create(materia=otra_materia, nombre='Unidad 1')
        otro_estudiante = Estudiante.objects.create(moodle_userid=9202, nombre='Otro Estudiante', email='otro@example.com')
        otra_tarea = Tarea.objects.create(
            unidad=otra_unidad, moodle_id=9600, titulo='Tarea vieja', tipo='assign', categoria='etek',
            cierre='martes, 1 de enero de 2030, 10:00', url='https://moodle.example/mod/assign/view.php?id=9600',
        )
        for i in range(5):
            tarea = Tarea.objects.create(
                unidad=otra_unidad, moodle_id=9700 + i, titulo=f'Vieja {i}', tipo='assign', categoria='etek',
                cierre='martes, 1 de enero de 2030, 10:00', url=f'https://moodle.example/mod/assign/view.php?id={9700 + i}',
            )
            Entrega.objects.create(tarea=tarea, estudiante=otro_estudiante, estado='Sin entrega')
        PrediccionRiesgo.objects.create(
            estudiante=otro_estudiante, tarea=otra_tarea,
            tipo_modelo=PrediccionRiesgo.ACUMULACION, probabilidad=0.9, banda=PrediccionRiesgo.ALTO,
        )
        PrediccionRiesgo.objects.create(
            estudiante=self.estudiante, tarea=self.tarea_abierta,
            tipo_modelo=PrediccionRiesgo.ACUMULACION, probabilidad=0.9, banda=PrediccionRiesgo.ALTO,
        )

        resp_2026 = self.client.get(reverse('alertas'), {'anio': '2026'})
        nombres_2026 = [f['estudiante__nombre'] for f in resp_2026.context['alertas_detalle']['estudiantes_sobrecarga']]
        self.assertIn('Ana Pérez', nombres_2026)
        self.assertNotIn('Otro Estudiante', nombres_2026)

        resp_2025 = self.client.get(reverse('alertas'), {'anio': '2025'})
        nombres_2025 = [f['estudiante__nombre'] for f in resp_2025.context['alertas_detalle']['estudiantes_sobrecarga']]
        self.assertIn('Otro Estudiante', nombres_2025)
        self.assertNotIn('Ana Pérez', nombres_2025)

    def test_modal_detalle_agrupa_tareas_por_cercania_de_fecha(self):
        tarea_vencida_mucho = Tarea.objects.create(
            unidad=self.tarea_abierta.unidad, moodle_id=9800, titulo='Muy vencida',
            tipo='assign', categoria='etek', cierre='martes, 1 de enero de 2020, 10:00',
            url='https://moodle.example/mod/assign/view.php?id=9800',
        )
        Entrega.objects.create(tarea=tarea_vencida_mucho, estudiante=self.estudiante, estado='Sin entrega')
        # self.tarea_abierta NO tiene Entrega propia (solo sirve para calificar al
        # estudiante como "banda alta" en el setUp) - acá se la entrega también, para
        # poder verificar que SU probabilidad puntual viaja junto con ella en el modal.
        Entrega.objects.create(tarea=self.tarea_abierta, estudiante=self.estudiante, estado='Sin entrega')
        PrediccionRiesgo.objects.create(
            estudiante=self.estudiante, tarea=self.tarea_abierta,
            tipo_modelo=PrediccionRiesgo.ACUMULACION, probabilidad=0.77, banda=PrediccionRiesgo.ALTO,
        )

        resp = self.client.get(reverse('sobrecarga_detalle_estudiante', args=[self.estudiante.id]))
        self.assertEqual(resp.status_code, 200)
        datos = resp.json()
        self.assertEqual(datos['estudiante'], 'Ana Pérez')
        self.assertEqual(len(datos['grupos']['vencidas_hace_mucho']), 1)
        self.assertEqual(datos['grupos']['vencidas_hace_mucho'][0]['titulo'], 'Muy vencida')
        # Las 5 del setUp + tarea_abierta cierran en 2030: quedan como "por vencer lejos".
        self.assertEqual(len(datos['grupos']['por_vencer_lejos']), 6)
        # La probabilidad viaja con SU tarea puntual, no con las demás (que no tienen
        # PrediccionRiesgo propia y deben quedar en None).
        por_titulo = {t['titulo']: t['probabilidad'] for t in datos['grupos']['por_vencer_lejos']}
        self.assertEqual(por_titulo[self.tarea_abierta.titulo], 0.77)
        self.assertIsNone(por_titulo['Tarea 0'])

    def test_sobrecarga_no_aparece_con_banda_baja_aunque_tenga_muchas_pendientes(self):
        PrediccionRiesgo.objects.create(
            estudiante=self.estudiante, tarea=self.tarea_abierta,
            tipo_modelo=PrediccionRiesgo.ACUMULACION, probabilidad=0.1, banda=PrediccionRiesgo.BAJO,
        )
        resp = self.client.get(reverse('alertas'))
        detalle = resp.context['alertas_detalle']
        self.assertTrue(detalle['sobrecarga_calculada'])
        self.assertEqual(detalle['estudiantes_sobrecarga'], [])

    def test_inactividad_modelo_se_muestra_sin_ningun_aviso_pegado(self):
        PrediccionRiesgo.objects.create(
            estudiante=self.estudiante, tipo_modelo=PrediccionRiesgo.INACTIVIDAD,
            probabilidad=0.4, banda=PrediccionRiesgo.MEDIO,
        )
        resp = self.client.get(reverse('alertas'))
        self.assertContains(resp, 'Ana Pérez')
        self.assertContains(resp, '0.40')
        # Decisión 2026-11-23: nada de texto de advertencia sobre el recall del modelo.
        self.assertNotContains(resp, 'recall')
        self.assertNotContains(resp, 'referencial')

    def test_inactividad_estatica_por_materia_y_general(self):
        ahora = timezone.now()
        acceso = AccesoCurso.objects.create(materia=self.materia, moodle_userid=9201, ultimo_acceso='45 dias 0 horas')
        AccesoCurso.objects.filter(pk=acceso.pk).update(actualizado=ahora)
        resp = self.client.get(reverse('alertas'))
        detalle = resp.context['alertas_detalle']
        self.assertEqual(len(detalle['inactivos_general']), 1)
        self.assertEqual(detalle['inactivos_por_materia'][0]['materia'], 'Bases de Datos')

    def test_resumen_nunca_muestra_estudiantes_en_riesgo_alto(self):
        # Decisión 2026-11-24: ese KPI se oculta de Resumen (sigue viéndose en Alertas,
        # con más detalle) - ni con predicciones calculadas ni sin ellas.
        resp_sin = self.client.get(reverse('resumen'))
        self.assertNotIn('sobrecarga_calculada', resp_sin.context['kpis'])
        self.assertNotContains(resp_sin, 'Estudiantes en riesgo alto')

        PrediccionRiesgo.objects.create(
            estudiante=self.estudiante, tarea=self.tarea_abierta,
            tipo_modelo=PrediccionRiesgo.ACUMULACION, probabilidad=0.9, banda=PrediccionRiesgo.ALTO,
        )
        resp_con = self.client.get(reverse('resumen'))
        self.assertNotContains(resp_con, 'Estudiantes en riesgo alto')


@override_settings(STORAGES=SIN_MANIFIESTO)
class ResumenKpisTests(TestCase):
    """KPIs de Resumen rediseñados 2026-11-24: solo materias activas, docentes con cuenta
    sobre el total, estudiantes activos/posible abandono (acceso real, no proxy del
    modelo), actividades NO entregadas (excluye a los de posible abandono), y "materias
    con retraso" redefinido (Unidad con título placeholder "UT N: XXXX" que ya debería
    tener contenido real según la fecha y los parciales configurados)."""

    def setUp(self):
        self.carrera = Carrera.objects.create(facultad=Facultad.objects.create(nombre='Ingeniería'), nombre='Sistemas')
        self.materia_activa = Materia.objects.create(
            gestion=2026, nombre='Materia Activa', moodle_nombre='2026/MA',
            moodle_url='https://moodle.example/course/view.php?id=1', carrera=self.carrera, activo=True,
        )
        Materia.objects.create(
            gestion=2026, nombre='Materia Inhabilitada', moodle_nombre='2026/MI',
            moodle_url='https://moodle.example/course/view.php?id=2', carrera=self.carrera, activo=False,
        )

        self.docente_con_cuenta = User.objects.create_user(username='docente.cuenta', password='clave-123')
        self.profesor_con_cuenta = Profesor.objects.create(
            moodle_id=5001, nombre='Docente Con Cuenta',
            url='https://moodle.example/user/view.php?id=5001', user=self.docente_con_cuenta,
        )
        self.profesor_sin_cuenta = Profesor.objects.create(
            moodle_id=5002, nombre='Docente Sin Cuenta', url='https://moodle.example/user/view.php?id=5002',
        )
        self.materia_activa.profesores.add(self.profesor_con_cuenta, self.profesor_sin_cuenta)

        self.unidad = Unidad.objects.create(materia=self.materia_activa, nombre='Unidad 1')
        self.estudiante_activo = Estudiante.objects.create(moodle_userid=6001, nombre='Estudiante Activo', email='activo@example.com')
        self.estudiante_abandono = Estudiante.objects.create(moodle_userid=6002, nombre='Estudiante Abandono', email='abandono@example.com')

        tarea = Tarea.objects.create(
            unidad=self.unidad, moodle_id=6100, titulo='Práctica E-Tek 1', tipo='assign', categoria='etek',
            cierre='martes, 1 de enero de 2030, 10:00', url='https://moodle.example/mod/assign/view.php?id=6100',
        )
        Entrega.objects.create(tarea=tarea, estudiante=self.estudiante_activo, estado='Sin entrega')
        Entrega.objects.create(tarea=tarea, estudiante=self.estudiante_abandono, estado='Sin entrega')

        ahora = timezone.now()
        acceso_activo = AccesoCurso.objects.create(materia=self.materia_activa, moodle_userid=6001, ultimo_acceso='1 dia 0 horas')
        AccesoCurso.objects.filter(pk=acceso_activo.pk).update(actualizado=ahora)
        acceso_abandono = AccesoCurso.objects.create(materia=self.materia_activa, moodle_userid=6002, ultimo_acceso='45 dias 0 horas')
        AccesoCurso.objects.filter(pk=acceso_abandono.pk).update(actualizado=ahora)

        self.admin_user = User.objects.create_user(username='admin.resumen', password='clave-123')
        PerfilUsuario.objects.create(user=self.admin_user, rol=PerfilUsuario.ADMINISTRADOR)
        self.client.force_login(self.admin_user)

    def test_materias_monitoreadas_solo_cuenta_las_activas(self):
        resp = self.client.get(reverse('resumen'))
        self.assertEqual(resp.context['kpis']['materias'], 1)

    def test_docentes_muestra_con_cuenta_sobre_el_total(self):
        resp = self.client.get(reverse('resumen'))
        self.assertEqual(resp.context['kpis']['docentes'], 2)
        self.assertEqual(resp.context['kpis']['docentes_con_cuenta'], 1)
        self.assertContains(resp, '1/2')

    def test_estudiantes_separados_en_activos_y_posible_abandono(self):
        resp = self.client.get(reverse('resumen'))
        self.assertEqual(resp.context['kpis']['estudiantes_activos'], 1)
        self.assertEqual(resp.context['kpis']['estudiantes_posible_abandono'], 1)

    def test_actividades_no_entregadas_excluye_a_los_de_posible_abandono(self):
        # La tarea la deben los dos estudiantes, pero solo el activo cuenta - si ya la
        # deben solo los de posible abandono, no debería sumar acá.
        resp = self.client.get(reverse('resumen'))
        self.assertEqual(resp.context['kpis']['actividades_no_entregadas'], 1)

    def test_materias_con_retraso_detecta_placeholder_dentro_de_fecha(self):
        Unidad.objects.create(materia=self.materia_activa, nombre='UT 2: XXXX')
        FechasParciales.objects.create(
            profesor=self.profesor_con_cuenta,
            p1_inicio=timezone.now().date() - timedelta(days=10), p1_fin=timezone.now().date() + timedelta(days=10),
        )
        resp = self.client.get(reverse('resumen'))
        self.assertEqual(resp.context['kpis']['materias_con_retraso'], 1)

    def test_materias_con_retraso_no_alerta_antes_de_que_le_toque(self):
        # UT 8 todavía no debería tener contenido: con unidades_por_parcial=2 (default) y
        # solo el parcial 1 en curso (los parciales 2-4 configurados explícitamente en el
        # futuro, para que no entre el default institucional), lo esperado hasta ahora es
        # UT 1-2.
        Unidad.objects.create(materia=self.materia_activa, nombre='UT 8: XXXX')
        futuro = timezone.now().date() + timedelta(days=200)
        FechasParciales.objects.create(
            profesor=self.profesor_con_cuenta,
            p1_inicio=timezone.now().date() - timedelta(days=10), p1_fin=timezone.now().date() + timedelta(days=10),
            p2_inicio=futuro, p2_fin=futuro + timedelta(days=10),
            p3_inicio=futuro + timedelta(days=20), p3_fin=futuro + timedelta(days=30),
            p4_inicio=futuro + timedelta(days=40), p4_fin=futuro + timedelta(days=50),
        )
        resp = self.client.get(reverse('resumen'))
        self.assertEqual(resp.context['kpis']['materias_con_retraso'], 0)

    def test_materias_con_retraso_sin_fechas_configuradas_usa_el_default_institucional(self):
        # Decisión 2026-11-24: una materia cuyo profesor nunca configuró FechasParciales no
        # queda afuera para siempre - se usa el rango institucional por defecto para juzgarla.
        Unidad.objects.create(materia=self.materia_activa, nombre='UT 1: XXXX')
        resp = self.client.get(reverse('resumen'))
        self.assertEqual(resp.context['kpis']['materias_con_retraso'], 1)

    def test_guardar_unidades_por_parcial_desde_configuracion(self):
        self.client.post(reverse('configuracion'), {'accion': 'guardar_unidades_por_parcial', 'unidades_por_parcial': '5'})
        config_inst = ConfiguracionInstitucional.objects.get(pk=1)
        self.assertEqual(config_inst.unidades_por_parcial, 5)
