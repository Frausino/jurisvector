from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv

load_dotenv()

PASTA_BASE = "base"


def criar_db():
    documentos = carregar_documentos()
    chunks = dividir_chunks(documentos)
    vetorizar_chunks(chunks)


def carregar_documentos():
    loader = PyPDFDirectoryLoader(PASTA_BASE, glob="*.pdf")
    return loader.load()


def dividir_chunks(documentos):

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=2000, chunk_overlap=500, length_function=len, add_start_index=True
    )

    chunks = splitter.split_documents(documentos)

    print("chunks:", len(chunks))

    return chunks


def vetorizar_chunks(chunks):

    embeddings = OpenAIEmbeddings()

    Chroma.from_documents(chunks, embeddings, persist_directory="data_base")

    print("banco de dados criado")


criar_db()
