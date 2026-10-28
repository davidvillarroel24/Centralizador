from datetime import timedelta

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

    email = models.EmailField(
        unique=True
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
    sino de la institucion entera. Hoy solo la nota minima de aprobacion (TECBA: 61/100),
    que usa tanto el panel de Predicciones (banda de riesgo) como el comando
    `exportar_dataset_ml` (para etiquetar las filas de entrenamiento)."""

    nota_aprobacion = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=61,
        help_text='Nota minima sobre 100 para considerar un parcial aprobado.',
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
    VISITANTE: cuenta con acceso minimo (Resumen + filtro de facultad/carrera); se crea
        asociada a un Profesor ficticio (moodle_id reservado, sin materias reales) para
        no tener que relajar la validacion de login/registro existente, que hoy exige que
        el username coincida con un Profesor."""

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
