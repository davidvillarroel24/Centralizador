"""Candado global de extraccion: evita que dos usuarios distintos disparen un scraping
contra Moodle al mismo tiempo (ver plan de mejoras 2026-09-29, seccion 2).

Diseno:
- Una unica fila en TrabajoExtraccion (pk=1) actua como mutex. Se toma con
  select_for_update() sobre esa fila fija -> dos requests concurrentes se serializan de
  verdad (el segundo espera a que el primero termine su bloque `atomic`, que es corto:
  solo lee/escribe esa fila, NO corre el scraping adentro de la transaccion).
- Si la fila ya esta en_curso pero paso el timeout (job "muerto" que nunca la libero), se
  fuerza a liberar y se le entrega el candado a quien lo pidio.
- El paralelismo *interno* de una extraccion (asyncio.Semaphore en los scrapers) no pasa
  por aca - este candado solo decide si arranca una extraccion nueva o no.
- El registro en memoria `_stop_events` sostiene el boton de emergencia (detener
  extraccion). Vive en el proceso del worker web; valido porque Render free corre un solo
  proceso (misma premisa que ya usa el candado de un solo carril).
"""
import threading
import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from data.models import TrabajoExtraccion

LOCK_TIMEOUT_SECONDS = 120  # 2 minutos, igual al valor ya acordado en PLAN_DESARROLLO.md

_stop_events = {}
_registry_lock = threading.Lock()


def try_acquire_lock(usuario):
    """Intenta tomar el candado. Devuelve el job_id si lo consigue, o None si ya hay una
    extraccion en curso de otro usuario y todavia no vencio su timeout."""
    with transaction.atomic():
        candado, _ = TrabajoExtraccion.objects.select_for_update().get_or_create(pk=1)

        if candado.en_curso:
            vencido = (
                candado.iniciado is not None
                and timezone.now() - candado.iniciado > timedelta(seconds=LOCK_TIMEOUT_SECONDS)
            )
            if not vencido:
                return None
            _forget_event(candado.job_id)

        job_id = uuid.uuid4().hex
        candado.job_id = job_id
        candado.usuario = usuario
        candado.en_curso = True
        candado.iniciado = timezone.now()
        candado.save()

    with _registry_lock:
        _stop_events[job_id] = threading.Event()
    return job_id


def release_lock(job_id):
    """Libera el candado si todavia pertenece a job_id (evita que un release tardio de un
    job viejo pise el lock de uno nuevo que ya lo tomo tras un timeout)."""
    with transaction.atomic():
        TrabajoExtraccion.objects.select_for_update().filter(pk=1, job_id=job_id).update(
            en_curso=False
        )
    _forget_event(job_id)


def current_lock():
    """Estado actual del candado, para mostrar en la UI (quien lo tiene, desde cuando)."""
    return TrabajoExtraccion.objects.filter(pk=1, en_curso=True).first()


def request_stop():
    """Marca el evento de parada del job en curso. Devuelve True si habia uno para detener."""
    candado = current_lock()
    if not candado:
        return False
    with _registry_lock:
        event = _stop_events.get(candado.job_id)
    if event is None:
        return False
    event.set()
    return True


def get_stop_event(job_id):
    with _registry_lock:
        return _stop_events.get(job_id)


def _forget_event(job_id):
    if not job_id:
        return
    with _registry_lock:
        _stop_events.pop(job_id, None)
