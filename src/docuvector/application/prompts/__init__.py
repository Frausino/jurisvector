"""Templates de prompt para LLM."""

from docuvector.application.prompts.legal_prompt import (
    build_user_prompt,
    get_system_prompt,
)

__all__ = ["build_user_prompt", "get_system_prompt"]
