from datetime import date, timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

COOKIE_VENCE_DESPUES = timedelta(hours=2)


class Profesor(models.Model):
    moodle_id = models.IntegerField(unique=True)
    nombre = models.CharField(max_length=255)
    url = models.URLField()
    # Cookie MoodleSession cifrada (ver data/cookie_crypto.py) - reemplaza al viejo
    # moodle_session_hash, que guardaba un hash de un solo sentido (make_password) y nunca
    # se podia volver a leer para usarla de verdad en una extraccion.
    moodle_cookie_cifrada = models.TextField(blank=True, null=True)
    moodle_cookie_guardada_en = models.DateTimeField(blank=True, null=True)
    # Cuándo terminó (o cerró) la guía de uso. Vacío = se le muestra al entrar; se puede
    # repetir cuando quiera desde "Guía de uso" en el menú (ver web/static/web/tour.js).
    tour_visto_en = models.DateTimeField(blank=True, null=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='profesor_perfil'
    )

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    def cookie_vigente(self):
        """'Expiracion perezosa': no hay ningun proceso en segundo plano borrando cookies
        vencidas - simplemente, cada vez que se la necesita, se compara cuanto hace que se
        guardo. Si pasaron mas de 2 horas (o nunca se guardo), se la trata como vencida."""
        if not self.moodle_cookie_cifrada or not self.moodle_cookie_guardada_en:
            return False
        return timezone.now() - self.moodle_cookie_guardada_en < COOKIE_VENCE_DESPUES

    def borrar_cookie(self):
        self.moodle_cookie_cifrada = None
        self.moodle_cookie_guardada_en = None
        self.save(update_fields=['moodle_cookie_cifrada', 'moodle_cookie_guardada_en'])


class FechasParciales(models.Model):
    """Una fila por profesor (id_user = profesor_id), con las fechas de inicio/fin de los
    4 parciales como columnas fijas - reemplaza al JSON {'rangos_parciales': [...]} para
    no mezclar datos estructurados dentro de una sola celda."""

    profesor = models.OneToOneField(
        Profesor,
        on_delete=models.CASCADE,
        related_name='fechas_parciales'
    )

    p1_inicio = models.DateField(null=True, blank=True)
    p1_fin = models.DateField(null=True, blank=True)
    p2_inicio = models.DateField(null=True, blank=True)
    p2_fin = models.DateField(null=True, blank=True)
    p3_inicio = models.DateField(null=True, blank=True)
    p3_fin = models.DateField(null=True, blank=True)
    p4_inicio = models.DateField(null=True, blank=True)
    p4_fin = models.DateField(null=True, blank=True)

    actualizado = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Fechas de parciales - {self.profesor}"


class PesosCategorias(models.Model):
    """Una fila por profesor (id_user = profesor_id), con el peso (%) de cada categoria de
    tarea como columna fija - reemplaza al JSON {'pesos_default': {...}}."""

    profesor = models.OneToOneField(
        Profesor,
        on_delete=models.CASCADE,
        related_name='pesos_categorias'
    )

    mitek = models.PositiveSmallIntegerField(default=0)
    etek = models.PositiveSmallIntegerField(default=0)
    training = models.PositiveSmallIntegerField(default=0)
    designlab = models.PositiveSmallIntegerField(default=0)
    examen = models.PositiveSmallIntegerField(default=0)

    actualizado = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Pesos de categorias - {self.profesor}"


# Default institucional (ver web/views.py::configuracion_view): la mayoria de los docentes
# no quiere/no necesita personalizar esto parcial por parcial, asi que estos valores se
# aplican solos en vez de bloquear la extraccion hasta que alguien complete el formulario
# a mano. Los 4 meses de "fin" (abril/junio/septiembre/noviembre) tienen todos 30 dias, asi
# que no hace falta calendar.monthrange para el ultimo dia.
PESOS_DEFAULT = {'mitek': 10, 'etek': 20, 'training': 20, 'designlab': 20, 'examen': 30}
RANGOS_PARCIALES_DEFAULT_MESES = {
    1: (2, 1, 4, 30),    # Febrero a Abril
    2: (5, 1, 6, 30),    # Mayo a Junio
    3: (7, 1, 9, 30),    # Julio a Septiembre
    4: (10, 1, 11, 30),  # Octubre a Noviembre
}


def _rango_parcial_default(numero, anio):
    mes_ini, dia_ini, mes_fin, dia_fin = RANGOS_PARCIALES_DEFAULT_MESES[numero]
    return date(anio, mes_ini, dia_ini), date(anio, mes_fin, dia_fin)


def asegurar_config_tareas_default(profesor, forzar=False):
    """Crea FechasParciales/PesosCategorias de `profesor` si no existen y completa SOLO los
    campos que todavia estan sin configurar, con el default institucional de arriba (año en
    curso) - para que un docente que nunca entro a Configuracion igual pueda extraer/asignar
    tareas, sin quedar bloqueado hasta completar el formulario a mano. Los docentes pueden
    configurar fechas de cualquier año (no se asume que tiene que ser el actual) - un campo
    ya configurado nunca se toca, sin importar a que año corresponda. Con forzar=True
    ("Restablecer y guardar" en Configuración) pisa todo con el default del año en curso,
    incluso lo ya configurado. Devuelve (fechas, pesos) ya guardados."""
    anio = date.today().year

    fechas, _ = FechasParciales.objects.get_or_create(profesor=profesor)
    cambios = False
    for i in range(1, 5):
        inicio_default, fin_default = _rango_parcial_default(i, anio)
        campo_inicio, campo_fin = f'p{i}_inicio', f'p{i}_fin'
        if forzar or not getattr(fechas, campo_inicio):
            setattr(fechas, campo_inicio, inicio_default)
            cambios = True
        if forzar or not getattr(fechas, campo_fin):
            setattr(fechas, campo_fin, fin_default)
            cambios = True
    if cambios:
        fechas.save()

    pesos, _ = PesosCategorias.objects.get_or_create(profesor=profesor)
    cambios = False
    for cat, valor in PESOS_DEFAULT.items():
        if forzar or not getattr(pesos, cat):
            setattr(pesos, cat, valor)
            cambios = True
    if cambios:
        pesos.save()

    return fechas, pesos


from django.db import models


class Facultad(models.Model):
    nombre = models.CharField(max_length=255, unique=True)

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

class Carrera(models.Model):

    facultad = models.ForeignKey(
        Facultad,
        on_delete=models.CASCADE,
        related_name='carreras'
    )

    nombre = models.CharField(max_length=255)

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['nombre']
        unique_together = ['facultad', 'nombre']

    def __str__(self):
        return self.nombre
    
class Nivel(models.Model):

    nombre = models.CharField(
        max_length=100,
        unique=True
    )

    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre
    
class Materia(models.Model):

    gestion = models.IntegerField()

    grupo = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )

    turno = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )

    sigla = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    nombre = models.CharField(
        max_length=255
    )

    moodle_nombre = models.CharField(
        max_length=500,
        unique=True
    )

    moodle_url = models.URLField()

    carrera = models.ForeignKey(
        Carrera,
        on_delete=models.CASCADE,
        related_name='materias'
    )

    nivel = models.ForeignKey(
        Nivel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='materias'
    )

    profesores = models.ManyToManyField(
        Profesor,
        related_name='materias',
        blank=True
    )

    # "Eliminacion logica": una materia inhabilitada no aparece para nadie (ver
    # data.roles.materias_visibles, que filtra activo=True al final) ni es seleccionable
    # para extraccion - pero sus filas (Unidad/Tarea/Entrega) siguen intactas en la base,
    # a diferencia de borrarla. Pensado para casos como una materia duplicada (bug #1: ver
    # Materia.moodle_nombre mas abajo) que conviene esconder ya mismo sin animarse a un
    # DELETE. Solo Administrador puede tocar este campo (web/materias.html).
    activo = models.BooleanField(default=True)

    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['gestion', 'nombre']

    def __str__(self):
        return f"{self.gestion} - {self.nombre}"
    
from django.db import models


class Unidad(models.Model):

    materia = models.ForeignKey(
        "Materia",
        on_delete=models.CASCADE,
        related_name="unidades"
    )

    nombre = models.CharField(max_length=255)

    def __str__(self):

        return self.nombre


class Tarea(models.Model):

    unidad = models.ForeignKey(
        Unidad,
        on_delete=models.CASCADE,
        related_name="tareas"
    )

    moodle_id = models.IntegerField(
        unique=True
    )

    titulo = models.CharField(
        max_length=500
    )

    tipo = models.CharField(
        max_length=100
    )

    apertura = models.CharField(
        max_length=255,
        null=True,
        blank=True
    )

    cierre = models.CharField(
        max_length=255,
        null=True,
        blank=True
    )

    url = models.URLField(
        max_length=1000
    )

    descripcion = models.TextField(
        null=True,
        blank=True
    )

    url_entrega = models.URLField(
        max_length=1000,
        null=True,
        blank=True
    )

    CATEGORIAS = [
        ('mitek', 'Mi-Tek'),
        ('etek', 'E-Tek'),
        ('training', 'Training'),
        ('designlab', 'Design Lab'),
        ('examen', 'Examen'),
    ]

    categoria = models.CharField(
        max_length=20,
        choices=CATEGORIAS,
        null=True,
        blank=True
    )

    parcial = models.PositiveSmallIntegerField(
        null=True,
        blank=True
    )

    def __str__(self):

        return self.titulo


class Estudiante(models.Model):

    moodle_userid = models.IntegerField(
        unique=True
    )

    nombre = models.CharField(
        max_length=255
    )

    # BUG (encontrado 2026-11-05): un Decano ve la planilla de calificacion sin columna de
    # correo (ver scraping/scrapers/detallesprofesores.py::ORDEN_DECANO), asi que
    # importar_estudiantes() puede no tener ese dato todavia. Antes este campo no admitia
    # NULL y la extraccion de un Decano reventaba (IntegrityError) con el primer estudiante
    # nuevo que viera. null=True permite dejarlo vacio hasta que una extraccion de un
    # Docente (que si trae el correo) lo complete - unique=True sigue sin problema porque
    # Postgres no compara dos NULL como iguales.
    email = models.EmailField(
        unique=True,
        null=True,
        blank=True,
    )

    def __str__(self):

        return self.nombre


class Entrega(models.Model):

    tarea = models.ForeignKey(
        Tarea,
        on_delete=models.CASCADE,
        related_name="entregas"
    )

    estudiante = models.ForeignKey(
        Estudiante,
        on_delete=models.CASCADE,
        related_name="entregas"
    )

    estado = models.CharField(
        max_length=255,
        null=True,
        blank=True
    )

    calificacion = models.CharField(
        max_length=100,
        null=True,
        blank=True
    )

    # nota/nota_maxima se parsean de calificacion_final ("16,70 / 100,00"), no de
    # calificacion (trae el texto del boton de Moodle pegado, ej. "Calificar16,70 / 100,00")
    # - calificacion/calificacion_final se conservan como texto crudo para auditoria.
    # Ambos quedan en None si la tarea todavia no fue calificada (calificacion_final="-").
    nota = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )

    nota_maxima = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )

    ultima_mod_entrega = models.CharField(
        max_length=255,
        null=True,
        blank=True
    )

    ultima_mod_calificacion = models.CharField(
        max_length=255,
        null=True,
        blank=True
    )

    comentarios_entrega = models.TextField(
        null=True,
        blank=True
    )

    comentarios_feedback = models.TextField(
        null=True,
        blank=True
    )

    calificacion_final = models.CharField(
        max_length=100,
        null=True,
        blank=True
    )

    link_calificar = models.URLField(
        max_length=1000,
        null=True,
        blank=True
    )

    class Meta:

        unique_together = ("tarea", "estudiante")

    def __str__(self):

        return f"{self.estudiante} - {self.tarea}"


class AccesoCurso(models.Model):
    """Una fila por (materia, persona), viniendo de /user/index.php?id=<curso> (padron de
    inscritos de Moodle - a diferencia de Entrega, que solo ve a quien entrego algo en una
    tarea, esto trae a TODOS los inscritos). No usa FK a Estudiante/Profesor porque un mismo
    moodle_userid puede ser cualquiera de los dos segun el curso (ademas asi una sola tabla
    sirve para ambos, en vez de duplicar columnas en los dos modelos) - el `rol` que trae
    Moodle dice cual es en cada materia puntual, y los reportes resuelven la identidad
    buscando ese id en Estudiante.moodle_userid o Profesor.moodle_id segun haga falta.

    ultimo_acceso/fecha_inicio_matricula/fecha_matriculacion quedan como texto crudo tal
    cual lo manda Moodle (ej. "343 dias 13 horas" o "Nunca"), igual que Tarea.apertura/
    cierre - no se parsean a fecha real porque el formato varia (relativo vs absoluto segun
    configuracion del sitio)."""

    materia = models.ForeignKey(
        Materia,
        on_delete=models.CASCADE,
        related_name='accesos'
    )

    moodle_userid = models.IntegerField()

    rol = models.CharField(max_length=255, null=True, blank=True)

    ultimo_acceso = models.CharField(max_length=255, null=True, blank=True)
    fecha_inicio_matricula = models.CharField(max_length=255, null=True, blank=True)
    fecha_matriculacion = models.CharField(max_length=255, null=True, blank=True)

    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('materia', 'moodle_userid')

    def __str__(self):
        return f"acceso {self.moodle_userid} - {self.materia}"


class ConfiguracionInstitucional(models.Model):
    """Fila unica (pk=1), igual que TrabajoExtraccion: parametros que no son por-profesor
    sino de la institucion entera. Nota minima de aprobacion (TECBA: 61/100), que usa tanto
    el panel de Predicciones (banda de riesgo) como el comando `exportar_dataset_ml` (para
    etiquetar las filas de entrenamiento); y si el boton "Visitante" del login esta
    habilitado (ver PerfilUsuario.VISITANTE y login_view)."""

    nota_aprobacion = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=61,
        help_text='Nota minima sobre 100 para considerar un parcial aprobado.',
    )

    visitante_habilitado = models.BooleanField(
        default=False,
        help_text='Si esta activo, el login muestra un boton "Visitante" que loguea sin '
                   'cuenta a una sesion de solo lectura (Resumen, Estudiantes, Reportes).',
    )

    actualizado = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Nota de aprobación: {self.nota_aprobacion}/100"

    @classmethod
    def actual(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class TrabajoExtraccion(models.Model):
    """Fila unica (pk=1) que actua como candado global de extraccion: garantiza que solo
    haya UNA extraccion en curso a la vez en todo el sistema, sin importar que usuario la
    dispare. El paralelismo interno de una misma extraccion (asyncio.Semaphore en los
    scrapers) no se ve afectado por este candado - solo serializa entre usuarios distintos.
    """

    job_id = models.CharField(max_length=64, blank=True, default='')
    usuario = models.CharField(max_length=255, blank=True, default='')
    en_curso = models.BooleanField(default=False)
    iniciado = models.DateTimeField(null=True, blank=True)
    # Antes vivia solo en memoria (threading.Event) del proceso que arranco la extraccion
    # - con mas de un worker de gunicorn, el click de "Detener" podia caer en un worker
    # distinto al que la corria y no hacer nada. En la base, cualquier worker lo ve.
    detener = models.BooleanField(default=False)
    # Texto corto tipo "Extrayendo tareas de la materia: X", actualizado por el scraper a
    # medida que avanza (ver services/utils/extraction_lock.py::DbStopEvent.set_paso). Lo
    # lee el endpoint de progreso (/extraccion/progreso/) via polling, para el spinner del
    # dashboard - gunicorn corre con 2 workers (ver deploy/web/entrypoint.sh), asi que ese
    # polling lo atiende el worker libre mientras el otro sigue bloqueado extrayendo.
    paso_actual = models.CharField(max_length=255, blank=True, default='')

    def __str__(self):
        if self.en_curso:
            return f"candado ocupado por {self.usuario} (job {self.job_id})"
        return "candado libre"


class ArchivoTarea(models.Model):

    tarea = models.ForeignKey(
        Tarea,
        on_delete=models.CASCADE,
        related_name="archivos_tarea"
    )

    nombre = models.CharField(
        max_length=500
    )

    url = models.URLField(
        max_length=1500
    )

    fecha = models.CharField(
        max_length=255,
        null=True,
        blank=True
    )

    def __str__(self):

        return self.nombre


class ArchivoEntrega(models.Model):
    """Archivos que el ESTUDIANTE adjuntó a una entrega puntual (no confundir con
    ArchivoTarea, que son los archivos que el DOCENTE subió en la descripción de la tarea).
    1 Entrega -> N archivos - existió como JSONField en Entrega (migración 0008), se quitó
    en la 0009 sin reemplazo (se perdía el dato igual, el scraper nunca dejó de traerlo) y
    se repone acá como tabla aparte, igual que ArchivoTarea, para no romper 3FN con un
    array dentro de una columna."""

    entrega = models.ForeignKey(
        Entrega,
        on_delete=models.CASCADE,
        related_name="archivos_entrega"
    )

    nombre = models.CharField(
        max_length=500
    )

    url = models.URLField(
        max_length=1500
    )

    fecha = models.CharField(
        max_length=255,
        null=True,
        blank=True
    )

    def __str__(self):

        return self.nombre


class PerfilUsuario(models.Model):
    """Un perfil por cada User de Django, con su rol en el sistema. No se le agrega el
    campo 'rol' directo a auth_user porque esa tabla es de la app django.contrib.auth:
    Django no deja que otra app le agregue un campo ahi de forma soportada (sin recurrir a
    SQL crudo + parches en tiempo de arranque, fragil ante cambios de Django). Esta tabla
    aparte, mostrada como seccion dentro de la misma pantalla de edicion del User en el
    admin (ver data/admin.py), da el mismo resultado practico sin ese riesgo.

    ADMINISTRADOR: ve todo, sin restriccion.
    DECANO: ve todo lo que caiga bajo CUALQUIERA de sus 3 asignaciones (facultades, carreras
        o materias sueltas) - la union de las tres, no una jerarquia excluyente. Puede
        ademas ser Docente de sus propias materias al mismo tiempo (no es un rol exclusivo,
        solo agrega visualizacion extra sobre lo que ya veria como Docente).
    DOCENTE: rol por defecto: ve unicamente lo propio (sus materias).
    VISITANTE: acceso de solo lectura a Resumen, Estudiantes y Reportes (ve todas las
        materias, igual que Administrador, pero sin nada de Materias/Docentes/Alertas/
        Predicciones/Extraccion/Configuracion). Una unica cuenta compartida (no una por
        visitante): se crea asociada a un Profesor ficticio fijo (moodle_id reservado, sin
        materias reales) para no tener que relajar la validacion de login/registro
        existente, que hoy exige que el username coincida con un Profesor - el boton
        "Visitante" del login entra directo a esa cuenta, sin pedir nada (ver
        data.roles.get_or_crear_visitante_compartido)."""

    ADMINISTRADOR = 'administrador'
    DECANO = 'decano'
    DOCENTE = 'docente'
    VISITANTE = 'visitante'
    ROLES = [
        (ADMINISTRADOR, 'Administrador'),
        (DECANO, 'Decano'),
        (DOCENTE, 'Docente'),
        (VISITANTE, 'Visitante'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='perfil'
    )

    rol = models.CharField(max_length=20, choices=ROLES, default=DOCENTE)

    # Alcance del Decano: union de estas 3 (solo se usan cuando rol == DECANO).
    facultades = models.ManyToManyField(
        Facultad,
        blank=True,
        related_name='decanos',
        help_text='Solo para rol Decano: ve todas las carreras/materias de estas facultades.',
    )
    carreras = models.ManyToManyField(
        Carrera,
        blank=True,
        related_name='decanos',
        help_text='Solo para rol Decano: ve todas las materias de estas carreras.',
    )
    materias = models.ManyToManyField(
        Materia,
        blank=True,
        related_name='decanos',
        help_text='Solo para rol Decano: ve estas materias sueltas, sin asignar toda la carrera.',
    )

    actualizado = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} ({self.get_rol_display()})"
