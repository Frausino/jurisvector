"""Camada de Aplicação: casos de uso que orquestram o domínio.

Cada use case tem responsabilidade única e recebe dependências
via construtor (Dependency Inversion). Nunca importa FastAPI nem
SQLAlchemy diretamente.
"""
