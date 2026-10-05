from django.conf import settings
from django.db import models


class Profesor(models.Model):
    moodle_id = models.IntegerField(unique=True)
    nombre = models.CharField(max_length=255)
    url = models.URLField()
    moodle_session_hash = models.CharField(max_length=255, blank=True, null=True)
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
