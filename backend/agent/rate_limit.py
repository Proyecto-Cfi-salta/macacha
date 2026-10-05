import math
import threading
import time
from collections import deque
from typing import Callable

_MAX_IP_EN_MEMORIA = 1000


class LimitadorPorIP:
    def __init__(self, reloj: Callable[[], float] = time.monotonic):
        self._reloj = reloj
        self._eventos: dict[str, deque[float]] = {}
        self._candado = threading.Lock()

    def verificar(self, ip: str, limite: int, ventana: float = 60.0) -> int | None:
        ahora = self._reloj()
        with self._candado:
            eventos = self._eventos.setdefault(ip, deque())
            while eventos and ahora - eventos[0] >= ventana:
                eventos.popleft()
            if len(eventos) >= limite:
                return max(1, math.ceil(ventana - (ahora - eventos[0])))
            eventos.append(ahora)
            if len(self._eventos) > _MAX_IP_EN_MEMORIA:
                self._podar(ahora, ventana)
            return None

    def reiniciar(self) -> None:
        with self._candado:
            self._eventos.clear()

    def _podar(self, ahora: float, ventana: float) -> None:
        vencidas = [ip for ip, e in self._eventos.items() if not e or ahora - e[-1] >= ventana]
        for ip in vencidas:
            del self._eventos[ip]


def ip_cliente(x_forwarded_for: str | None, host_directo: str | None, saltos_proxy: int) -> str:
    if x_forwarded_for and saltos_proxy > 0:
        entradas = [e.strip() for e in x_forwarded_for.split(",") if e.strip()]
        if len(entradas) >= saltos_proxy:
            return entradas[-saltos_proxy]
    return host_directo or "desconocida"
