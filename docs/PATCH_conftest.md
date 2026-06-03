# Patch para `tests/conftest.py` — gap #7 da auditoria

## O que adicionar

Localize o bloco de `setdefault` para LLM no `_set_test_environment()`:

```python
    os.environ.setdefault("OPENAI_LLM_MODEL", "gpt-4o-mini")
    os.environ.setdefault("OPENAI_LLM_TEMPERATURE", "0.2")
    os.environ.setdefault("OPENAI_LLM_MAX_TOKENS", "600")
```

E **adicione logo após** as 4 linhas abaixo:

```python
    # Bloco 5: LLM como provider pluggable. Em teste, o default é
    # `mock` (sem rede, sem chave). Em dev/prod o operador troca para
    # `ollama` ou `openai`.
    os.environ.setdefault("LLM_DEFAULT_PROVIDER", "mock")
    os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
    os.environ.setdefault("OLLAMA_MODEL", "qwen2.5:7b")
    os.environ.setdefault("OLLAMA_TIMEOUT_SECONDS", "60")
```

## Comando rápido (sed) para Linux/WSL

```bash
sed -i '/os.environ.setdefault("OPENAI_LLM_MAX_TOKENS", "600")/a\
\
    # Bloco 5: LLM como provider pluggable. Em teste, o default é\
    # `mock` (sem rede, sem chave). Em dev/prod o operador troca para\
    # `ollama` ou `openai`.\
    os.environ.setdefault("LLM_DEFAULT_PROVIDER", "mock")\
    os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")\
    os.environ.setdefault("OLLAMA_MODEL", "qwen2.5:7b")\
    os.environ.setdefault("OLLAMA_TIMEOUT_SECONDS", "60")' tests/conftest.py
```

## Por quê

O `test_list_llm_providers_returns_mock_and_ollama_by_default` assume
`body["default"] == "mock"`. Hoje funciona por coincidência: o default
do `Settings.llm_default_provider` é `LlmProviderName.MOCK`. Mas se
alguém alterar o default no `Settings`, o teste passa a depender de
um valor não fixado no ambiente de teste.

RGN-T1 atualizada: configuração de teste fica explícita no `conftest`,
nunca herdada do default da aplicação.
