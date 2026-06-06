from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from threading import Semaphore


class RequestScheduler:
    """Controla concorrência local do Ollama."""

    def __init__(
        self,
        max_concurrent_requests: int = 1,
    ) -> None:
        self._semaphore = Semaphore(max_concurrent_requests)

    @contextmanager
    def acquire(self) -> Iterator[None]:
        """Reserva um slot de execução."""
        self._semaphore.acquire()
        try:
            yield
        finally:
            self._semaphore.release()
