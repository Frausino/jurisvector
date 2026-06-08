"""Cliente LLM para Ollama local via API HTTP.

Decisão: `httpx` direto, sem adicionar o SDK `ollama-python` como
dependência. A API do Ollama é trivial (1 endpoint, 1 método), e
puxar SDK para isso seria over-engineering.

Endpoint usado: `POST {base_url}/api/chat` com `stream=False`.
Documentação: https://github.com/ollama/ollama/blob/main/docs/api.md

Métricas:
- `tokens_used`: `prompt_eval_count + eval_count` (quando disponíveis).
- `cost_usd`: SEMPRE 0.0 — execução local não tem custo monetário.
  Sprint 4 pode mapear custo em watt-hora, mas isso é outra dimensão.
- `latency_ms`: medido client-side. Ollama também devolve `total_duration`
  em nanossegundos, mas usamos o tempo de wall clock para ser
  comparável com OpenAI.
- `model`: echo do modelo solicitado (não confiamos no echo do servidor,
  que às vezes muda quando o modelo é resolvido por alias).
"""

from __future__ import annotations

import time

import httpx

from docuvector.domain.exceptions import LlmGenerationError
from docuvector.domain.interfaces.llm_client import LlmCompletion
from docuvector.infrastructure.llm.ollama_performance_registry import (
    OllamaPerformanceRegistry,
)
from docuvector.infrastructure.llm.request_scheduler import RequestScheduler

_scheduler = RequestScheduler(max_concurrent_requests=1)

_registry = OllamaPerformanceRegistry()


class OllamaLlmClient:
    """Implementa `LlmClient` falando com um servidor Ollama local."""

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float = 60.0,
        temperature: float = 0.2,
        max_tokens: int = 600,
    ) -> None:
        # Normaliza removendo barra final para evitar `//api/chat`.
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._temperature = temperature
        self._max_tokens = max_tokens

    def complete(self, system_prompt: str, user_prompt: str) -> LlmCompletion:
        """Executa a inferência local e devolve texto + métricas."""
        if not user_prompt.strip():
            raise LlmGenerationError("Prompt do usuário está vazio.")

        request_payload = {
            "model": self._model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {
                "temperature": self._temperature,
                "num_predict": self._max_tokens,
            },
        }

        request_started_at = time.perf_counter()

        try:
            with _scheduler.acquire():
                response = httpx.post(
                    f"{self._base_url}/api/chat",
                    json=request_payload,
                    timeout=httpx.Timeout(
                        connect=10.0,
                        read=self._timeout_seconds,
                        write=30.0,
                        pool=30.0,
                    ),
                )

            response.raise_for_status()

        except httpx.HTTPError as ollama_failure:
            raise LlmGenerationError(
                f"Falha na chamada ao Ollama em {self._base_url}: {ollama_failure}"
            ) from ollama_failure

        elapsed_milliseconds = int((time.perf_counter() - request_started_at) * 1000)

        response_json = response.json()

        total_duration_ns = int(response_json.get("total_duration", 0) or 0)

        load_duration_ns = int(response_json.get("load_duration", 0) or 0)

        eval_count = int(response_json.get("eval_count", 0) or 0)

        _registry.update(
            self._model,
            tokens_generated=eval_count,
            total_duration_seconds=(total_duration_ns / 1_000_000_000),
            load_duration_seconds=(load_duration_ns / 1_000_000_000),
        )

        return self._build_completion(
            response_json,
            elapsed_milliseconds,
        )

    def _build_completion(
        self,
        ollama_response: dict[str, object],
        elapsed_milliseconds: int,
    ) -> LlmCompletion:
        """Extrai texto e métricas da resposta JSON do Ollama."""
        message_block = ollama_response.get("message")
        if not isinstance(message_block, dict):
            raise LlmGenerationError("Ollama devolveu resposta sem 'message'.")

        message_content = message_block.get("content", "")
        if not isinstance(message_content, str):
            raise LlmGenerationError("Ollama devolveu 'content' em formato inesperado.")

        prompt_eval_count = ollama_response.get("prompt_eval_count", 0)
        eval_count = ollama_response.get("eval_count", 0)
        tokens_used = (int(prompt_eval_count) if isinstance(prompt_eval_count, int) else 0) + (
            int(eval_count) if isinstance(eval_count, int) else 0
        )

        return LlmCompletion(
            text=message_content.strip(),
            tokens_used=tokens_used,
            cost_usd=0.0,
            latency_ms=elapsed_milliseconds,
            model=self._model,
        )
