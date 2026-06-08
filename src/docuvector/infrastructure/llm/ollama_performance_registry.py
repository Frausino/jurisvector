from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from time import time


@dataclass(slots=True)
class ModelPerformance:
    model: str
    avg_tokens_per_second: float
    avg_load_seconds: float
    samples: int
    last_updated: float


class OllamaPerformanceRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._models: dict[str, ModelPerformance] = {}

    def get(self, model: str) -> ModelPerformance | None:
        return self._models.get(model)

    def update(
        self,
        model: str,
        *,
        tokens_generated: int,
        total_duration_seconds: float,
        load_duration_seconds: float,
    ) -> None:
        if tokens_generated <= 0:
            return

        tps = tokens_generated / max(total_duration_seconds, 0.001)

        with self._lock:
            current = self._models.get(model)

            if current is None:
                self._models[model] = ModelPerformance(
                    model=model,
                    avg_tokens_per_second=tps,
                    avg_load_seconds=load_duration_seconds,
                    samples=1,
                    last_updated=time(),
                )
                return

            n = current.samples + 1

            current.avg_tokens_per_second = (
                (current.avg_tokens_per_second * current.samples) + tps
            ) / n

            current.avg_load_seconds = (
                (current.avg_load_seconds * current.samples) + load_duration_seconds
            ) / n

            current.samples = n
            current.last_updated = time()
