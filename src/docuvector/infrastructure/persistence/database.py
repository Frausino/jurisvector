"""Engine SQLAlchemy e factory de sessões.

Concentra criação do engine e de sessões em um único módulo para facilitar
substituição em testes e controle de pool de conexões.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from docuvector.config.settings import Settings, get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Engine singleton para o processo atual.

    Cacheado para evitar abrir múltiplos pools de conexão.
    Pool dimensionado para uso didático (5 conexões + 5 overflow); em
    produção real seria parametrizado por variável de ambiente.
    """
    settings: Settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=1800,
        echo=False,
        future=True,
    )


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """Factory de sessões SQLAlchemy 2.0.

    Cacheada para que `Session` use sempre o mesmo engine configurado.
    """
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )


@contextmanager
def session_scope() -> Iterator[Session]:
    """Sessão como context manager com commit/rollback automáticos.

    Padrão para scripts e jobs que não usam a DI do FastAPI.
    Uso típico:

        with session_scope() as db_session:
            db_session.add(record)
    """
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def provide_session() -> Iterator[Session]:
    """Dependency FastAPI: injeta uma sessão por requisição.

    Uso no router:

        def endpoint(db_session: Annotated[Session, Depends(provide_session)]):
            ...
    """
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
