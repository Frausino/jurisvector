from langchain_chroma.vectorstores import Chroma
from langchain_classic.prompts import ChatPromptTemplate
from langchain_openai import OpenAIEmbeddings
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()

CAMINHO_DATA_BASE = "data_base"

prompt_template = """
Resposnda a pergunta do usuário:
{pergunta}

com base nessas informações:

{base_conhecimento}

Se você não encontrar a resposta para a pergunta do usuário nessas informações,
responda não sei te dizer isso
"""


def perguntar():
    pergunta = input("Escreva sua pergunta: ")

    # Carregar BD
    funcao_embedding = OpenAIEmbeddings()

    data_base_carregado = Chroma(
        persist_directory=CAMINHO_DATA_BASE, embedding_function=funcao_embedding
    )

    # Comparar a pergunta do user (embedding) com BD
    resultados_das_respostas_comparadas = (
        data_base_carregado.similarity_search_with_relevance_scores(pergunta, k=5)
    )

    if (
        len(resultados_das_respostas_comparadas) == 0
        or resultados_das_respostas_comparadas[0][1] < 0.7
    ):
        print("Não encontrou informações relevantes")
        return

    textos_resultado_all = []

    for resultados_page_content in resultados_das_respostas_comparadas:
        texto = resultados_page_content[0].page_content
        textos_resultado_all.append(texto)

    base_conhecimento = "\n\n----\n\n".join(textos_resultado_all)

    prompt = ChatPromptTemplate.from_template(prompt_template)

    prompt = prompt.invoke(
        {"pergunta": pergunta, "base_conhecimento": base_conhecimento}
    )

    modelo = ChatOpenAI()

    resposta = modelo.invoke(prompt)

    print("\nResposta:\n")
    print(resposta.content)


perguntar()
