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
from xml.sax.saxutils import escape

from django.db.models import Prefetch
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

from data.models import AccesoCurso, Estudiante, Materia, Profesor, Tarea, Unidad

# Paleta institucional para Excel/PDF (pedida 2026-11-27): encabezado en el rojo-naranja
# más fuerte, bandas alternadas de filas en el tono más claro, para que los reportes
# descargados se vean consistentes con el resto de la identidad visual de la app.
COLOR_ENCABEZADO = 'D94423'
COLOR_BANDA_CLARA = 'FBE8DC'
COLOR_BORDE = '0D0D0D'

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

UMBRAL_INACTIVIDAD_ESTATICA_DIAS = 30


def _accesos_estudiantes_con_fecha_aprox(materias_qs):
    """[(estudiante, materia, fecha_aprox), ...] - acceso REAL (no proxy de entregas, a
    diferencia del modelo de inactividad) de cada estudiante a cada materia, aproximando
    la fecha igual que datos_reporte_acceso(): AccesoCurso solo trae el texto relativo que
    mandó Moodle ("343 días 13 horas"), así que se resta ese delta a
    AccesoCurso.actualizado (el momento en que se extrajo esa fila)."""
    accesos = AccesoCurso.objects.filter(materia__in=materias_qs).select_related('materia')
    estudiantes_por_id = {e.moodle_userid: e for e in Estudiante.objects.all()}

    resultado = []
    for acceso in accesos:
        estudiante = estudiantes_por_id.get(acceso.moodle_userid)
        if not estudiante:
            continue  # en el padrón de Moodle pero todavía no importado como Estudiante
        delta = parsear_ultimo_acceso(acceso.ultimo_acceso)
        if delta is None:
            continue
        resultado.append((estudiante, acceso.materia, acceso.actualizado - delta))
    return resultado


def estudiantes_inactivos_por_materia(materias_qs, umbral_dias=UMBRAL_INACTIVIDAD_ESTATICA_DIAS):
    """[{'estudiante_id', 'estudiante_nombre', 'materia', 'dias_inactivo'}, ...] - un
    estudiante puede entrar seguido a una materia y no entrar hace rato a otra; esto
    reporta cada (estudiante, materia) por separado, a diferencia de la versión "general"
    (ver estudiantes_inactivos_general) que mira su acceso más reciente entre todas."""
    ahora = datetime.now(timezone.utc)
    filas = []
    for estudiante, materia, fecha_aprox in _accesos_estudiantes_con_fecha_aprox(materias_qs):
        dias_inactivo = (ahora - fecha_aprox).days
        if dias_inactivo >= umbral_dias:
            filas.append({
                'estudiante_id': estudiante.id,
                'estudiante_nombre': estudiante.nombre,
                'materia': materia.nombre,
                'dias_inactivo': dias_inactivo,
            })
    return filas


def estudiantes_inactivos_general(materias_qs, umbral_dias=UMBRAL_INACTIVIDAD_ESTATICA_DIAS):
    """Por estudiante, el acceso MÁS RECIENTE entre TODAS sus materias (puede no entrar a
    varias pero sí a una en particular, seguido) - solo cuenta como inactivo "en general"
    si ni siquiera esa más reciente supera el umbral."""
    ahora = datetime.now(timezone.utc)
    mas_reciente_por_estudiante = {}
    for estudiante, _materia, fecha_aprox in _accesos_estudiantes_con_fecha_aprox(materias_qs):
        actual = mas_reciente_por_estudiante.get(estudiante.id)
        if actual is None or fecha_aprox > actual['fecha_aprox']:
            mas_reciente_por_estudiante[estudiante.id] = {
                'estudiante_id': estudiante.id,
                'estudiante_nombre': estudiante.nombre,
                'fecha_aprox': fecha_aprox,
            }

    filas = []
    for datos in mas_reciente_por_estudiante.values():
        dias_inactivo = (ahora - datos['fecha_aprox']).days
        if dias_inactivo >= umbral_dias:
            filas.append({
                'estudiante_id': datos['estudiante_id'],
                'estudiante_nombre': datos['estudiante_nombre'],
                'dias_inactivo': dias_inactivo,
            })
    return filas


def _filtrar_por_busqueda(filas, q):
    """Mismo criterio que el cuadro de búsqueda global de DataTables en la pantalla (busca
    como texto en cualquier columna) - para que "Descargar Excel/PDF" baje lo que se está
    viendo filtrado/buscado en ese momento, no todo el reporte sin filtrar (decisión
    2026-11-28). Sin `q`, no filtra nada."""
    if not q:
        return filas
    q = q.strip().lower()
    if not q:
        return filas
    return [f for f in filas if q in ' '.join(str(v) for v in f.values() if v is not None).lower()]


def datos_reporte_acceso(materias_qs, rol='todos', materia_id='', q=''):
    accesos = AccesoCurso.objects.filter(materia__in=materias_qs).select_related('materia')
    if materia_id:
        accesos = accesos.filter(materia_id=materia_id)

    profesores_por_id = {p.moodle_id: p.nombre for p in Profesor.objects.all()}
    estudiantes_por_id = {e.moodle_userid: e.nombre for e in Estudiante.objects.all()}

    filas = []
    for acceso in accesos:
        es_docente = acceso.moodle_userid in profesores_por_id
        es_estudiante = acceso.moodle_userid in estudiantes_por_id
        if not es_docente and not es_estudiante:
            # Aparece en el padrón de Moodle (ya se corrió "4. Extraer e importar último
            # acceso") pero todavía no se importó como Profesor ni Estudiante en este
            # sistema (falta correr "3. Importar estudiantes"/"Importar profesores" para
            # esa materia). Antes se mostraba como "(sin identificar, id X)", pero eso se
            # leía como un error grave en vez de "todavía falta un paso" - se oculta hasta
            # que se importe (decisión 2026-11-28).
            continue
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

        nombre = profesores_por_id[acceso.moodle_userid] if es_docente else estudiantes_por_id[acceso.moodle_userid]

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
    return _filtrar_por_busqueda(filas, q)


def datos_reporte_contenido(materias_qs, tipo, docente_id='', q=''):
    """tipo='assign' -> tareas asignadas; tipo='url' -> material de apoyo. Mismo
    agrupamiento Docente -> Materia -> Unidad para ambos.

    FIX N+1 (encontrado 2026-11-24, /reportes/ tardaba varios segundos): antes se hacía
    prefetch_related('unidades__tareas__archivos_tarea') y después, por cada unidad,
    `unidad.tareas.filter(tipo=tipo)` - agregarle un .filter() a un manager ya prefetcheado
    hace que Django ignore el cache y vuelva a consultar la base, una vez por unidad (282
    unidades x 2 tipos de reporte = miles de queries de más). Ahora el filtro por tipo (y
    el order_by de ambos niveles) va DENTRO del Prefetch, así entra en el mismo query
    prefetcheado de una sola vez."""
    docentes = Profesor.objects.filter(materias__in=materias_qs).distinct().order_by('nombre')
    if docente_id:
        docentes = docentes.filter(pk=docente_id)

    tareas_qs = Tarea.objects.filter(tipo=tipo).order_by('titulo').prefetch_related('archivos_tarea')
    unidades_qs = Unidad.objects.order_by('nombre').prefetch_related(
        Prefetch('tareas', queryset=tareas_qs, to_attr='tareas_filtradas')
    )

    filas = []
    for docente in docentes:
        materias = docente.materias.filter(pk__in=materias_qs).order_by('nombre').prefetch_related(
            Prefetch('unidades', queryset=unidades_qs, to_attr='unidades_ordenadas')
        )
        for materia in materias:
            for unidad in materia.unidades_ordenadas:
                for tarea in unidad.tareas_filtradas:
                    if tipo == 'assign':
                        extra = tarea.cierre
                    else:
                        # BUG (encontrado 2026-11-10): antes esto siempre mostraba
                        # tarea.url (la pagina de Moodle de ese material), nunca el link
                        # externo real que el docente puso (Drive, YouTube, etc.) - esa
                        # extraccion no existia todavia (ver scraping/scrapers/
                        # materiales.py). Ahora prefiere url_entrega (el link externo) y,
                        # si no hay, el archivo propio (ArchivoTarea) cuando el material
                        # es solo un archivo subido sin link - tarea.url queda de ultimo
                        # recurso (ej. un cuestionario, que no tiene ninguna de las dos).
                        archivos = list(tarea.archivos_tarea.all())
                        archivo = archivos[0] if archivos else None
                        extra = tarea.url_entrega or (archivo.url if archivo else None) or tarea.url
                    filas.append({
                        'docente': docente.nombre,
                        'materia': materia.nombre,
                        'unidad': unidad.nombre,
                        'titulo': tarea.titulo,
                        'extra': extra,
                        'url': tarea.url,
                    })
    return _filtrar_por_busqueda(filas, q)


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
    relleno_encabezado = PatternFill(start_color=COLOR_ENCABEZADO, end_color=COLOR_ENCABEZADO, fill_type='solid')
    for celda in ws[1]:
        celda.font = Font(bold=True, color='FFFFFF')
        celda.fill = relleno_encabezado
        celda.alignment = Alignment(vertical='center')

    relleno_banda = PatternFill(start_color=COLOR_BANDA_CLARA, end_color=COLOR_BANDA_CLARA, fill_type='solid')
    for fila in filas:
        ws.append([_valor_celda(fila, clave) for clave, _etiqueta in info['columnas']])
        if ws.max_row % 2 == 0:
            for celda in ws[ws.max_row]:
                celda.fill = relleno_banda

    for columna in ws.columns:
        largo = max((len(str(c.value)) for c in columna if c.value is not None), default=10)
        ws.column_dimensions[columna[0].column_letter].width = min(largo + 2, 60)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


def _texto_quebrable(texto, cada=40):
    """Un token sin espacios más largo que `cada` (típicamente una URL) nunca se corta solo
    al ajustar el Paragraph de reportlab - se queda recto y se sale de su columna. Le mete
    un espacio de ancho cero cada tantos caracteres para darle puntos de corte, sin cambiar
    cómo se ve ni se copia el texto."""
    partes = []
    for palabra in texto.split(' '):
        if len(palabra) > cada:
            palabra = '​'.join(palabra[i:i + cada] for i in range(0, len(palabra), cada))
        partes.append(palabra)
    return ' '.join(partes)


def generar_pdf_reporte(tipo, filas):
    info = REPORTES[tipo]
    buffer = BytesIO()
    pagina = landscape(A4)
    margen = 24
    doc = SimpleDocTemplate(
        buffer, pagesize=pagina, title=info['titulo'],
        leftMargin=margen, rightMargin=margen, topMargin=margen, bottomMargin=margen,
    )
    estilos = getSampleStyleSheet()
    estilo_celda = ParagraphStyle('ReporteCelda', parent=estilos['Normal'], fontSize=8, leading=10)
    estilo_encabezado = ParagraphStyle(
        'ReporteEncabezado', parent=estilo_celda, textColor=colors.white, fontName='Helvetica-Bold',
    )

    columnas = info['columnas']
    # Columnas de igual ancho, repartiendo todo el espacio disponible entre márgenes - el
    # texto se envuelve dentro de cada celda (Paragraph) en vez de expandir la columna más
    # allá de la página, que era lo que cortaba la primera/última columna (bug reportado
    # 2026-11-27, ver captura: "nidad" en vez de "Unidad").
    ancho_columna = (pagina[0] - 2 * margen) / len(columnas)

    def celda(fila, clave, estilo):
        return Paragraph(_texto_quebrable(escape(str(_valor_celda(fila, clave)))), estilo)

    encabezados = [Paragraph(escape(etiqueta), estilo_encabezado) for _clave, etiqueta in columnas]
    datos = [encabezados] + [
        [celda(fila, clave, estilo_celda) for clave, _etiqueta in columnas]
        for fila in filas
    ]

    tabla = Table(datos, colWidths=[ancho_columna] * len(columnas), repeatRows=1)
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(f'#{COLOR_ENCABEZADO}')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor(f'#{COLOR_BORDE}')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor(f'#{COLOR_BANDA_CLARA}')]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))

    elementos = [Paragraph(info['titulo'], estilos['Title']), Spacer(1, 12), tabla]
    doc.build(elementos)
    buffer.seek(0)
    return buffer
