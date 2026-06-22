"""Configuração central — tudo vem de variáveis de ambiente (.env em dev, painel do Coolify em produção)."""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Chave de sessão do Flask. OBRIGATÓRIO trocar em produção (definir no Coolify).
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-troque-esta-chave-em-producao")

    # Banco. Em dev cai para SQLite local; em produção o Coolify injeta a DATABASE_URL do Postgres.
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///campanha_hevile.db")

    # Chave Fernet para criptografar a senha de e-mail (SMTP) de cada usuário.
    # Gere uma com:  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    FERNET_KEY = os.getenv("FERNET_KEY")

    # Caminho da planilha usada na importação inicial (seed).
    EXCEL_SEED = os.getenv("EXCEL_SEED", "../AGENDOR PESSOAS.xlsx")
