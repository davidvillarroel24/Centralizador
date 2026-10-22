"""Construcción de datos + generación de Excel/PDF para la pantalla de Reportes
(web/views.py::reportes_view y reportes_descargar). Tres reportes, cada uno con la misma
pareja de writers genéricos (generar_excel/generar_pdf) para no duplicar el armado del
archivo tres veces:

- 'acceso': último acceso de docentes/estudiantes, general o por materia. AccesoCurso solo
  trae el texto crudo que manda Moodle ("343 días 13 horas", "ahora", "Nunca") - no hay
  timestamp real guardado - así que se aproxima la fecha real restando ese texto parseado
  a AccesoCurso.actualizado (el momento en que se extrajo/importó esa fila). Por eso el
  reporte aclara que la fecha es aproximada, calculada al momento de la última extracción
  de "último acceso" para esa materia - no es la hora exacta en que esa persona entró.
- 'tareas': tareas (Tarea.tipo='assign') que cada docente publicó, agrupadas por materia/
  unidad (tema).
- 'material': material de apoyo (Tarea.tipo='url' - enlaces y archivos que no son
  entregables, ver import_to_db.py) que cada docente subió, mismo agrupamiento.
"""
import re
from datetime import datetime, timedelta, timezone
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

from data.models import AccesoCurso, Estudiante, Materia, Profesor

_UNIDADES = (
    ('segundo', timedelta(seconds=1)),
    ('minuto', timedelta(minutes=1)),
    ('hora', timedelta(hours=1)),
    ('dia', timedelta(days=1)),
    ('semana', timedelta(weeks=1)),
    ('mes', timedelta(days=30)),
    ('ano', timedelta(days=365)),
)


def _sin_acentos(texto):
    return (
        texto.replace('á', 'a').replace('é', 'e').replace('í', 'i')
        .replace('ó', 'o').replace('ú', 'u').replace('ñ', 'n')
    )


def parsear_ultimo_acceso(texto):
    """"351 días 17 horas" -> timedelta(...). None si no se pudo interpretar (vacío,
    "Nunca", formato inesperado)."""
    if not texto:
        return None
    texto = _sin_acentos(texto.strip().lower())
    if texto in ('ahora', 'justo ahora'):
        return timedelta(0)
    total = timedelta(0)
    encontrado = False
    for cantidad, unidad in re.findall(r'(\d+)\s*([a-z]+)', texto):
        for nombre, paso in _UNIDADES:
            if unidad.startswith(nombre):
                total += paso * int(cantidad)
                encontrado = True
                break
    return total if encontrado else None


FECHA_SENTINEL_ANTIGUA = datetime.min.replace(tzinfo=timezone.utc)


def datos_reporte_acceso(materias_qs, rol='todos', materia_id=''):
    accesos = AccesoCurso.objects.filter(materia__in=materias_qs).select_related('materia')
    if materia_id:
        accesos = accesos.filter(materia_id=materia_id)

    profesores_por_id = {p.moodle_id: p.nombre for p in Profesor.objects.all()}
    estudiantes_por_id = {e.moodle_userid: e.nombre for e in Estudiante.objects.all()}

    filas = []
    for acceso in accesos:
        es_docente = acceso.moodle_userid in profesores_por_id
        es_estudiante = acceso.moodle_userid in estudiantes_por_id
        if rol == 'docente' and not es_docente:
            continue
        if rol == 'estudiante' and not es_estudiante:
            continue

        # Una misma persona puede estar en ambas tablas a la vez (ej. un docente que
        # tambien aparece como estudiante en otro curso) - el rol mostrado refleja TODO lo
        # que es, no solo el que se uso para decidir si entra en el filtro.
        roles_fila = []
        if es_docente:
            roles_fila.append('Docente')
        if es_estudiante:
            roles_fila.append('Estudiante')
        rol_fila = ', '.join(roles_fila) if roles_fila else '—'

        if es_docente:
            nombre = profesores_por_id[acceso.moodle_userid]
        elif es_estudiante:
            nombre = estudiantes_por_id[acceso.moodle_userid]
        else:
            # Aparece en el padron de Moodle pero todavia no se importo como Profesor ni
            # Estudiante en este sistema (falta correr "Importar profesores/estudiantes").
            nombre = f"(sin identificar, id {acceso.moodle_userid})"

        delta = parsear_ultimo_acceso(acceso.ultimo_acceso)
        fecha_aprox = acceso.actualizado - delta if delta is not None else None

        filas.append({
            'nombre': nombre,
            'rol': rol_fila,
            'materia': acceso.materia.nombre,
            'ultimo_acceso_texto': acceso.ultimo_acceso or '—',
            'fecha_aprox': fecha_aprox,
        })

    filas.sort(key=lambda f: f['fecha_aprox'] or FECHA_SENTINEL_ANTIGUA, reverse=True)
    return filas


def datos_reporte_contenido(materias_qs, tipo, docente_id=''):
    """tipo='assign' -> tareas asignadas; tipo='url' -> material de apoyo. Mismo
    agrupamiento Docente -> Materia -> Unidad para ambos."""
    docentes = Profesor.objects.filter(materias__in=materias_qs).distinct().order_by('nombre')
    if docente_id:
        docentes = docentes.filter(pk=docente_id)

    filas = []
    for docente in docentes:
        materias = docente.materias.filter(pk__in=materias_qs).order_by('nombre').prefetch_related('unidades__tareas')
        for materia in materias:
            for unidad in materia.unidades.all().order_by('nombre'):
                for tarea in unidad.tareas.filter(tipo=tipo).order_by('titulo'):
                    filas.append({
                        'docente': docente.nombre,
                        'materia': materia.nombre,
                        'unidad': unidad.nombre,
                        'titulo': tarea.titulo,
                        'extra': tarea.cierre if tipo == 'assign' else tarea.url,
                        'url': tarea.url,
                    })
    return filas


REPORTES = {
    'acceso': {
        'titulo': 'Último acceso',
        'columnas': [
            ('nombre', 'Nombre'), ('rol', 'Rol'), ('materia', 'Materia'),
            ('ultimo_acceso_texto', 'Último acceso'), ('fecha_aprox', 'Fecha aproximada'),
        ],
    },
    'tareas': {
        'titulo': 'Tareas asignadas por docente',
        'columnas': [
            ('docente', 'Docente'), ('materia', 'Materia'), ('unidad', 'Tema/Unidad'),
            ('titulo', 'Tarea'), ('extra', 'Cierre'), ('url', 'Enlace'),
        ],
    },
    'material': {
        'titulo': 'Material de apoyo subido por docente',
        'columnas': [
            ('docente', 'Docente'), ('materia', 'Materia'), ('unidad', 'Tema/Unidad'),
            ('titulo', 'Material'), ('extra', 'Enlace'),
        ],
    },
}


def _valor_celda(fila, clave):
    valor = fila.get(clave)
    if isinstance(valor, datetime):
        return valor.strftime('%Y-%m-%d %H:%M')
    return valor if valor not in (None, '') else '—'


def generar_excel_reporte(tipo, filas):
    info = REPORTES[tipo]
    wb = Workbook()
    ws = wb.active
    ws.title = info['titulo'][:31]

    encabezados = [etiqueta for _clave, etiqueta in info['columnas']]
    ws.append(encabezados)
    for celda in ws[1]:
        celda.font = Font(bold=True)

    for fila in filas:
        ws.append([_valor_celda(fila, clave) for clave, _etiqueta in info['columnas']])

    for columna in ws.columns:
        largo = max((len(str(c.value)) for c in columna if c.value is not None), default=10)
        ws.column_dimensions[columna[0].column_letter].width = min(largo + 2, 60)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


def generar_pdf_reporte(tipo, filas):
    info = REPORTES[tipo]
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), title=info['titulo'])
    estilos = getSampleStyleSheet()

    encabezados = [etiqueta for _clave, etiqueta in info['columnas']]
    datos = [encabezados] + [
        [_valor_celda(fila, clave) for clave, _etiqueta in info['columnas']]
        for fila in filas
    ]

    tabla = Table(datos, repeatRows=1)
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3a2a5c')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f3f0fa')]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))

    elementos = [Paragraph(info['titulo'], estilos['Title']), Spacer(1, 12), tabla]
    doc.build(elementos)
    buffer.seek(0)
    return buffer
