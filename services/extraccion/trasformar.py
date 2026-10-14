from services.data_utils import run_export


def extraer_transformar(ids, profesor, archivo=None):
    if not ids:
        raise ValueError('Debes indicar al menos un id de curso (Materia.id) para generar el Excel.')
    if profesor is None:
        raise ValueError(
            'Tu cuenta no está vinculada a ningún Profesor, así que no hay pesos de '
            'categoría de dónde partir. Configuralos primero en /configuracion/.'
        )
    return run_export.generar_excel(ids, profesor, archivo=archivo)
