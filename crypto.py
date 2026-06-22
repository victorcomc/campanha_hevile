"""Criptografia da senha de e-mail (SMTP) dos usuários — nunca guardamos senha em texto puro."""
import base64
import hashlib

from cryptography.fernet import Fernet

from config import Config


def _fernet() -> Fernet:
    key = Config.FERNET_KEY
    if key:
        return Fernet(key.encode() if isinstance(key, str) else key)
    # Sem FERNET_KEY definida: deriva uma a partir da SECRET_KEY (suficiente para dev).
    # Em produção, DEFINA FERNET_KEY no Coolify para a chave ser estável entre deploys.
    digest = hashlib.sha256(Config.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def cripto(texto: str | None) -> str | None:
    if not texto:
        return None
    return _fernet().encrypt(texto.encode()).decode()


def descripto(token: str | None) -> str | None:
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except Exception:
        return None
