from services.utils import run_scraping


def extraer_participantes(ids, cookie=None, stop_event=None, perpage=None):
    # run_scraping.participantes() ya guarda en participantes.json; no volver a guardar aca.
    kwargs = {'cookie': cookie, 'stop_event': stop_event}
    if perpage is not None:
        kwargs['perpage'] = perpage
    return run_scraping.participantes(ids, **kwargs)
