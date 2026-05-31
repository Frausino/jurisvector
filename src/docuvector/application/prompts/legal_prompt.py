"""Template de prompt para Q&A sobre documentos jurídicos.

Decisões de design:

1.  **PT-BR como idioma de instrução E de resposta.** Documentos do
    DocuVector são contratos, peças e jurisprudência em português.
    Forçar o LLM a operar no mesmo idioma reduz alucinação por
    "tradução interna" no modelo.

2.  **Citações inline obrigatórias `[1]`, `[2]`...** O LLM recebe os
    trechos numerados; precisa referenciar de volta. O front-end usa
    esses números para destacar a fonte. Sem citações, a resposta é
    inútil para uso forense.

3.  **Resposta "não tenho contexto suficiente" é VÁLIDA.** Melhor
    abster-se do que inventar. O modelo recebe instrução explícita
    para isso, e o use case marca `grounded=False` para o front
    exibir um indicador.

4.  **Sem JSON estruturado.** Texto livre com citações inline é
    mais robusto que parsing de JSON, que falha em ~5% das chamadas
    do gpt-4o-mini. Trade-off: parsing menos rigoroso, mas resposta
    sempre renderiza.
"""

from __future__ import annotations

from collections.abc import Sequence

from docuvector.domain.entities import RetrievedChunk

_SYSTEM_PROMPT_LEGAL_QA = (
    "Você é um assistente jurídico especializado em análise de contratos, "
    "peças processuais e jurisprudência brasileira. Sua tarefa é responder "
    "perguntas com base EXCLUSIVAMENTE nos trechos de documentos fornecidos.\n\n"
    "REGRAS OBRIGATÓRIAS:\n\n"
    "1. Responda SEMPRE em português brasileiro formal e técnico.\n\n"
    "2. Cite as fontes inline usando colchetes com o número do trecho, "
    "por exemplo [1], [2]. Quando uma afirmação se apoiar em múltiplos "
    "trechos, combine os números: [1][3].\n\n"
    "3. Se os trechos fornecidos NÃO contiverem informação suficiente "
    "para responder, diga exatamente: "
    '"Não tenho contexto suficiente nos documentos fornecidos para '
    'responder a essa pergunta com segurança." '
    "Não invente, não generalize com base em conhecimento jurídico geral "
    "e não preencha lacunas.\n\n"
    "4. NÃO emita opinião jurídica vinculante nem ofereça "
    "aconselhamento. Limite-se a relatar o que os documentos dizem.\n\n"
    "5. Mantenha a resposta concisa: 2 a 5 frases. Se a pergunta exigir "
    'lista (ex.: "quais são as cláusulas de rescisão?"), use itens '
    "enumerados, sempre citando.\n\n"
    "6. Preserve a terminologia exata dos documentos (nomes de partes, "
    "números de cláusulas, datas) tal como aparecem nos trechos."
)


def build_user_prompt(query: str, retrieved_chunks: Sequence[RetrievedChunk]) -> str:
    """Monta a parte de usuário do prompt: trechos numerados + pergunta.

    Os chunks já chegam ordenados por similaridade decrescente
    (responsabilidade do `RetrievalUseCase`). A numeração começa em 1
    para casar com o estilo de citação `[1]`, `[2]`...

    Se a lista vier vazia, retornamos uma instrução explícita: o LLM
    deve responder a frase canônica de abstenção. Isso fecha a porta
    para o LLM "improvisar" quando não há contexto.
    """
    if not retrieved_chunks:
        return (
            "Nenhum trecho de documento foi recuperado para esta pergunta. "
            'Responda exatamente: "Não tenho contexto suficiente nos '
            "documentos fornecidos para responder a essa pergunta com "
            'segurança."\n\n'
            f"Pergunta: {query}"
        )

    numbered_passages: list[str] = []
    for citation_number, chunk in enumerate(retrieved_chunks, start=1):
        passage_block = (
            f"[{citation_number}] Documento: {chunk.document_filename} "
            f"(trecho {chunk.chunk_index + 1})\n"
            f"{chunk.text.strip()}"
        )
        numbered_passages.append(passage_block)

    context_block = "\n\n".join(numbered_passages)
    return (
        "Trechos de documentos disponíveis para consulta:\n\n"
        f"{context_block}\n\n"
        "---\n\n"
        f"Pergunta: {query}\n\n"
        "Responda usando apenas os trechos acima, citando as fontes "
        "com [1], [2] etc."
    )


def get_system_prompt() -> str:
    """Retorna o system prompt jurídico (constante, mas exposta como função)."""
    return _SYSTEM_PROMPT_LEGAL_QA
