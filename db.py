"""Conexão com o banco via SQLAlchemy. Funciona igual em SQLite (dev) e PostgreSQL (produção)."""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session

from config import Config

_url = Config.DATABASE_URL
# Coolify/Heroku às vezes entregam "postgres://" — o SQLAlchemy quer "postgresql+psycopg2://".
if _url.startswith("postgres://"):
    _url = _url.replace("postgres://", "postgresql+psycopg2://", 1)
elif _url.startswith("postgresql://"):
    _url = _url.replace("postgresql://", "postgresql+psycopg2://", 1)

_engine_kwargs = {"pool_pre_ping": True, "future": True}
if _url.startswith("sqlite"):
    # SQLite precisa disso para ser usado por múltiplas threads (servidor web).
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(_url, **_engine_kwargs)
SessionLocal = scoped_session(
    sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
)
Base = declarative_base()


def init_db():
    """Cria as tabelas se não existirem."""
    import models  # noqa: F401  (garante o registro dos modelos)
    Base.metadata.create_all(engine)
