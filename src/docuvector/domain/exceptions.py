"""Hierarquia de exceções da camada de domínio.

Erros de domínio não devem expor detalhes de infraestrutura ao cliente HTTP.
A camada de apresentação traduz cada um em status code apropriado.
"""

from __future__ import annotations


class DocuvectorError(Exception):
    """Raiz de todas as exceções de domínio do DocuVector Lite."""


class AuthenticationError(DocuvectorError):
    """Credenciais inválidas ou token inválido/expirado.

    Mensagem ao usuário é sempre genérica para não permitir enumeração
    (não distinguir email inexistente de senha errada).
    """


class AuthorizationError(DocuvectorError):
    """Usuário autenticado tentando ação fora de seu nível de acesso."""


class ResourceNotFoundError(DocuvectorError):
    """Recurso não encontrado, OU usuário sem permissão para vê-lo.

    Por design (RGN-10), camada de apresentação retorna HTTP 404 ao cliente
    em ambos os casos para mascarar a existência do recurso.
    O audit log diferencia: `status=forbidden` para acesso indevido,
    `status=failure` para inexistência real.
    """


class ValidationError(DocuvectorError):
    """Regra de negócio violada (ex.: senha fraca, e-mail malformado)."""


class DuplicateResourceError(DocuvectorError):
    """Tentativa de criar recurso que viola constraint de unicidade."""


# =============================================================
# Pipeline RAG (Sprint 3+)
# =============================================================
class DocumentExtractionError(DocuvectorError):
    """Falha ao extrair texto de um documento (PDF corrompido, etc)."""


class DocumentTooLargeError(ValidationError):
    """Tamanho do upload acima do limite configurado em UPLOAD_MAX_BYTES."""


class UnsupportedFileFormatError(ValidationError):
    """Formato de arquivo enviado não está em FileFormat."""


class EmbeddingGenerationError(DocuvectorError):
    """Provedor de embeddings retornou erro ou vetor de dimensão inválida."""


class VectorStoreError(DocuvectorError):
    """Falha em operação do VectorStore (indexação, busca, deleção)."""


class LlmGenerationError(DocuvectorError):
    """Falha na chamada ao LLM (rede, rate limit, conteúdo bloqueado)."""
