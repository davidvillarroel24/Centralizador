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
- El pedido de parada (boton "Detener extraccion") se guarda en la misma fila
  (TrabajoExtraccion.detener), no en memoria del proceso: con gunicorn corriendo mas de
  un worker, el click podia atenderlo un worker distinto al que tiene la extraccion
  corriendo, y un threading.Event() en memoria de ese otro worker nunca se enterraba. En
  la base, cualquier worker lo ve.
"""
import time
import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from data.models import TrabajoExtraccion

LOCK_TIMEOUT_SECONDS = 120  # 2 minutos, igual al valor ya acordado en PLAN_DESARROLLO.md


class DbStopEvent:
    """Reemplazo de threading.Event() con la misma interfaz que ya usan los scrapers
    (`.is_set()`), pero respaldado en TrabajoExtraccion.detener en vez de memoria del
    proceso. Cachea la lectura un segundo: los loops de scraping (fetch_section,
    obtener_tareas_async...) pueden llamar is_set() muchas veces por segundo y no tiene
    sentido pegarle a la base en cada una."""

    _CACHE_SECONDS = 1.0

    def __init__(self, job_id):
        self.job_id = job_id
        self._cached = False
        self._cached_at = 0.0

    def is_set(self):
        ahora = time.monotonic()
        if ahora - self._cached_at < self._CACHE_SECONDS:
            return self._cached
        self._cached = TrabajoExtraccion.objects.filter(
            pk=1, job_id=self.job_id, detener=True
        ).exists()
        self._cached_at = ahora
        return self._cached


def try_acquire_lock(usuario):
    """Intenta tomar el candado. Devuelve (job_id, aviso): job_id es None si ya hay una
    extraccion en curso de otro usuario y todavia no vencio su timeout (aviso tambien
    None en ese caso). Si el candado estaba vencido (el proceso que lo tenia murio sin
    liberarlo - ej. gunicorn mato el worker por timeout) se fuerza su liberacion y se
    devuelve en `aviso` quien lo tenia y desde cuando, para que quien dispara la nueva
    extraccion vea que paso algo raro en la anterior (antes esto quedaba invisible, sin
    ningun log ni rastro)."""
    with transaction.atomic():
        candado, _ = TrabajoExtraccion.objects.select_for_update().get_or_create(pk=1)

        aviso = None
        if candado.en_curso:
            vencido = (
                candado.iniciado is not None
                and timezone.now() - candado.iniciado > timedelta(seconds=LOCK_TIMEOUT_SECONDS)
            )
            if not vencido:
                return None, None
            segundos = int((timezone.now() - candado.iniciado).total_seconds())
            aviso = (
                f'Se liberó automáticamente un candado vencido: lo tenía "{candado.usuario}" '
                f'hace {segundos}s sin liberarlo (probablemente un worker murió a mitad de la '
                f'extracción anterior).'
            )
            print(f"[extraction_lock] {aviso}")

        job_id = uuid.uuid4().hex
        candado.job_id = job_id
        candado.usuario = usuario
        candado.en_curso = True
        candado.iniciado = timezone.now()
        candado.detener = False
        candado.save()

    return job_id, aviso


def release_lock(job_id):
    """Libera el candado si todavia pertenece a job_id (evita que un release tardio de un
    job viejo pise el lock de uno nuevo que ya lo tomo tras un timeout)."""
    TrabajoExtraccion.objects.filter(pk=1, job_id=job_id).update(
        en_curso=False, detener=False
    )


def current_lock():
    """Estado actual del candado, para mostrar en la UI (quien lo tiene, desde cuando)."""
    return TrabajoExtraccion.objects.filter(pk=1, en_curso=True).first()


def request_stop():
    """Marca en la base el pedido de parada del job en curso. Devuelve True si habia uno
    para detener. Cualquier worker que llame a esto lo deja visible para cualquier otro
    worker que este corriendo la extraccion (ver DbStopEvent)."""
    candado = current_lock()
    if not candado:
        return False
    filas = TrabajoExtraccion.objects.filter(pk=1, job_id=candado.job_id).update(detener=True)
    return filas > 0


def get_stop_event(job_id):
    return DbStopEvent(job_id)
