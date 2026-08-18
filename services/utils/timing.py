import time
from functools import wraps

def medir_tiempo(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        inicio = time.time()
        print(f"\n⏱ Iniciando: {func.__name__}")

        resultado = func(*args, **kwargs)

        final = time.time()
        print(f"⏱ Finalizado: {func.__name__}")
        print(f"⏱ Tiempo: {final - inicio:.2f} segundos\n")

        return resultado

    return wrapper
