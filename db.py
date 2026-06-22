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
    """Cria as tabelas se não existirem e aplica migrações leves."""
    import models  # noqa: F401  (garante o registro dos modelos)
    Base.metadata.create_all(engine)
    _migrar()


def _migrar():
    """Migrações idempotentes para bancos já existentes (sem Alembic)."""
    from sqlalchemy import inspect as sa_inspect, text

    insp = sa_inspect(engine)
    if "usuarios" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("usuarios")}
    if "senha_temporaria" not in cols:
        # FALSE para os usuários já existentes (não força quem já tem senha própria).
        falso = "0" if engine.dialect.name == "sqlite" else "FALSE"
        with engine.begin() as conn:
            conn.execute(text(
                f"ALTER TABLE usuarios ADD COLUMN senha_temporaria BOOLEAN NOT NULL DEFAULT {falso}"
            ))
    if "assinatura" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE usuarios ADD COLUMN assinatura TEXT"))
