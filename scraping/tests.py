import asyncio
from unittest import mock

from django.test import SimpleTestCase

from scraping.scrapers import detallesprofesores
from scraping.scrapers.detallesprofesores import parsear_entregas, procesar_tarea_docente
from scraping.scrapers.participantes import fetch_participantes_curso, ultima_pagina

URL_TAREA = "https://moodle.example/mod/assign/view.php?id=77&action=grading&perpage=100"

# Planilla de calificacion tal como la ve un docente del curso (puede calificar).
ENCABEZADOS_DOCENTE = [
    "Seleccionar", "Imagen del usuario", "Nombre / Apellido(s)", "Dirección de correo",
    "Estado", "Calificación", "Editar", "Última modificación (entrega)", "Archivos enviados",
    "Comentarios de la entrega", "Última modificación (calificación)",
    "Comentarios de retroalimentación", "Calificación final",
]
# La misma planilla vista por un Decano - confirmado en TECBA probando con una cuenta real
# (2026-11-08): c0..c9, sin "Seleccionar" (c0 del docente, no hay checkbox para elegir en
# bloque), sin el correo (c3 del docente) ni "Editar" (c6 del docente).
ENCABEZADOS_DECANO = [
    "Imagen del usuario", "Nombre / Apellido(s)", "Estado", "Calificación",
    "Última modificación", "Archivos enviados", "Comentarios",
    "Última modificación (calificación)", "Comentarios de retroalimentación", "Calificación final",
]


def _celda(encabezado, userid, entrego, con_checkbox=True):
    if encabezado == "Seleccionar":
        return f'<input type="checkbox" name="selectedusers" value="{userid}">' if con_checkbox else ""
    if encabezado == "Imagen del usuario":
        return f'<a href="https://moodle.example/user/view.php?id={userid}&course=1"><img src="x.png"></a>'
    if encabezado.startswith("Nombre"):
        return f'<a href="https://moodle.example/user/view.php?id={userid}&course=1">Estudiante {userid}</a>'
    if encabezado.startswith("Dirección"):
        return f"est{userid}@example.com"
    if encabezado == "Estado":
        return "Enviado para calificar" if entrego else "Sin entrega"
    if encabezado == "Archivos enviados":
        return f'<a href="https://moodle.example/pluginfile.php/{userid}/t.pdf">t.pdf</a>' if entrego else ""
    # Resto: un texto unico por columna, para comprobar que cada campo sale de la suya.
    return f"{encabezado} {userid}"


def _barra_paginas(ultima, dinamica=False):
    """Barra de paginacion de Moodle. dinamica=True imita la tabla de participantes:
    links con href="#" y el numero (desde 1) en data-page-number."""
    if dinamica:
        items = "".join(
            f'<li class="page-item" data-page-number="{p + 1}"><a class="page-link" href="#">{p + 1}</a></li>'
            for p in range(ultima + 1)
        )
    else:
        items = '<li class="page-item active"><a class="page-link" href="#">1</a></li>' + "".join(
            f'<li class="page-item"><a class="page-link" href="{URL_TAREA}&amp;page={p}">{p + 1}</a></li>'
            for p in range(1, ultima + 1)
        )
    # La barra A-Z de nombres tambien usa page-link: no tiene que contar como pagina.
    items += f'<li class="page-item"><a class="page-link" href="{URL_TAREA}&amp;tifirst=Z&amp;page=99">Z</a></li>'
    return f'<nav aria-label="Página" class="pagination"><ul class="pagination">{items}</ul></nav>'


def _planilla(encabezados, userids, entregaron=(), ultima=0, con_checkbox=True):
    ths = "".join(f'<th class="header c{i}">{h}</th>' for i, h in enumerate(encabezados))
    filas = "".join(
        "<tr>" + "".join(
            f'<td class="cell c{i}">{_celda(h, u, u in entregaron, con_checkbox)}</td>' for i, h in enumerate(encabezados)
        ) + "</tr>"
        for u in userids
    )
    tabla = f'<table class="generaltable"><thead><tr>{ths}</tr></thead><tbody>{filas}</tbody></table>'
    return tabla + (_barra_paginas(ultima) if ultima else "")


class ParsearEntregasTests(SimpleTestCase):

    def test_planilla_de_docente_igual_que_antes(self):
        filas = parsear_entregas(_planilla(ENCABEZADOS_DOCENTE, [101, 102], entregaron={101}))
        self.assertEqual([f["userid"] for f in filas], ["101", "102"])
        f = filas[0]
        self.assertEqual(f["nombre"], "Estudiante 101")
        self.assertEqual(f["email"], "est101@example.com")
        self.assertEqual(f["estado"], "Enviado para calificar")
        self.assertEqual(f["calificacion"], "Calificación 101")
        self.assertEqual(f["ultima_mod_entrega"], "Última modificación (entrega) 101")
        self.assertEqual(f["archivos"], ["t.pdf"])
        self.assertEqual(f["comentarios_entrega"], "Comentarios de la entrega 101")
        self.assertEqual(f["ultima_mod_calificacion"], "Última modificación (calificación) 101")
        self.assertEqual(f["comentarios_feedback"], "Comentarios de retroalimentación 101")
        self.assertEqual(f["calificacion_final"], "Calificación final 101")
        self.assertEqual(filas[1]["estado"], "Sin entrega")

    def test_planilla_de_decano_saca_el_id_del_perfil_porque_no_hay_checkbox(self):
        # Antes se leia con las posiciones del docente y cada campo salia de otra columna
        # (ademas se asumia que si tenia "Seleccionar", cuando en realidad el Decano nunca
        # tiene esa columna - el userid sale siempre del link al perfil en "Nombre").
        self._verificar_decano()

    def test_la_eleccion_es_por_cantidad_de_columnas_no_por_encabezado(self):
        # Mismos 10 encabezados con otro texto: se lee igual, por posicion.
        otros = [f"Columna {i}" for i in range(len(ENCABEZADOS_DECANO))]
        html = _planilla(ENCABEZADOS_DECANO, [101], entregaron={101})
        for viejo, nuevo in zip(ENCABEZADOS_DECANO, otros):
            html = html.replace(f">{viejo}</th>", f">{nuevo}</th>")
        self.assertEqual(parsear_entregas(html)[0]["estado"], "Enviado para calificar")

    def _verificar_decano(self):
        filas = parsear_entregas(_planilla(ENCABEZADOS_DECANO, [101, 102], entregaron={101}))
        self.assertEqual([f["userid"] for f in filas], ["101", "102"])
        f = filas[0]
        self.assertEqual(f["nombre"], "Estudiante 101")
        self.assertIsNone(f["email"])
        self.assertEqual(f["estado"], "Enviado para calificar")
        self.assertEqual(f["calificacion"], "Calificación 101")
        self.assertEqual(f["ultima_mod_entrega"], "Última modificación 101")
        self.assertEqual(f["archivos"], ["t.pdf"])
        self.assertEqual(f["comentarios_entrega"], "Comentarios 101")
        self.assertEqual(f["ultima_mod_calificacion"], "Última modificación (calificación) 101")
        self.assertEqual(f["comentarios_feedback"], "Comentarios de retroalimentación 101")
        self.assertEqual(f["calificacion_final"], "Calificación final 101")
        self.assertEqual(filas[1]["estado"], "Sin entrega")

    def test_sin_tabla_devuelve_none(self):
        self.assertIsNone(parsear_entregas("<html>login</html>"))


class UltimaPaginaTests(SimpleTestCase):

    def test_sin_paginacion(self):
        self.assertEqual(ultima_pagina(_planilla(ENCABEZADOS_DOCENTE, [1])), 0)

    def test_links_comunes_con_page_en_el_href(self):
        self.assertEqual(ultima_pagina(_barra_paginas(4)), 4)

    def test_tabla_dinamica_con_href_numeral(self):
        self.assertEqual(ultima_pagina(_barra_paginas(2, dinamica=True)), 2)


class PaginacionEntregasTests(SimpleTestCase):
    """Moodle ignora &perpage=100 y pagina de a 10: un curso de 42 traia solo 10."""

    def _procesar(self, paginas):
        async def fetch_falso(session, url, semaphore):
            return paginas[url]

        with mock.patch.object(detallesprofesores, "fetch", side_effect=fetch_falso):
            return asyncio.run(
                procesar_tarea_docente(None, URL_TAREA, "Unidad 1", "Práctica 1", asyncio.Semaphore(5))
            )

    def test_trae_todas_las_paginas(self):
        userids = list(range(1, 43))
        paginas = {URL_TAREA: _planilla(ENCABEZADOS_DECANO, userids[0:10], entregaron={3}, ultima=4)}
        for p in range(1, 5):
            paginas[f"{URL_TAREA}&page={p}"] = _planilla(
                ENCABEZADOS_DECANO, userids[p * 10:(p + 1) * 10], entregaron={41}, ultima=4,
            )
        resultado = self._procesar(paginas)
        self.assertEqual(resultado["id"], "77")
        self.assertEqual(len(resultado["estudiantes"]), 42)
        entregados = [e["userid"] for e in resultado["estudiantes"] if e["estado"] != "Sin entrega"]
        self.assertEqual(entregados, ["3", "41"])

    def test_sin_paginacion_hace_un_solo_pedido(self):
        resultado = self._procesar({URL_TAREA: _planilla(ENCABEZADOS_DOCENTE, [1, 2])})
        self.assertEqual(len(resultado["estudiantes"]), 2)


# Tabla de participantes vista por un Decano - columnas confirmadas en TECBA.
def _participantes(userids, ultima=0):
    ths = "".join(
        f'<th class="header c{i}">{h}</th>'
        for i, h in enumerate(["Nombre / Apellido(s)", "Roles", "Grupos", "Último acceso al curso", "Estatus"])
    )
    filas = "".join(
        f'<tr><th class="cell c0"><a href="https://moodle.example/user/view.php?id={u}&course=1">Persona {u}</a></th>'
        f'<td class="cell c1">Estudiante</td><td class="cell c2">Grupo A</td>'
        f'<td class="cell c3">{u} días</td><td class="cell c4">Activo</td></tr>'
        for u in userids
    )
    tabla = f'<table id="participants"><thead><tr>{ths}</tr></thead><tbody>{filas}</tbody></table>'
    return tabla + (_barra_paginas(ultima, dinamica=True) if ultima else "")


class _RespuestaFalsa:
    def __init__(self, url, html):
        self.url, self._html = url, html

    async def text(self):
        return self._html

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _SesionFalsa:
    def __init__(self, paginas):
        self.paginas, self.pedidas = paginas, []

    def get(self, url):
        self.pedidas.append(url)
        return _RespuestaFalsa(url, self.paginas[url])


class PaginacionParticipantesTests(SimpleTestCase):

    def test_trae_todas_las_paginas_de_la_tabla_dinamica(self):
        base = "https://moodle.example/user/index.php?id=1"
        url = f"{base}&perpage=300"
        userids = list(range(1, 43))
        sesion = _SesionFalsa({
            url: _participantes(userids[0:20], ultima=2),
            f"{url}&page=1": _participantes(userids[20:40], ultima=2),
            f"{url}&page=2": _participantes(userids[40:], ultima=2),
        })
        participantes = asyncio.run(
            fetch_participantes_curso(sesion, base, 5, 300, asyncio.Semaphore(5))
        )
        self.assertEqual(len(participantes), 42)
        self.assertEqual(sesion.pedidas, [url, f"{url}&page=1", f"{url}&page=2"])
        p = participantes[0]
        self.assertEqual((p["moodle_userid"], p["nombre"], p["materia_id"]), (1, "Persona 1", 5))
        self.assertEqual(p["roles"], ["Estudiante"])
        self.assertEqual(p["ultimo_acceso"], "1 días")
