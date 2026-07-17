"""Modelos do banco. Substituem a planilha Excel como fonte de dados."""
from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


def agora():
    return datetime.now(timezone.utc)


class Usuario(Base, UserMixin):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(180), unique=True, nullable=False, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    # True = senha definida por admin; força a pessoa a trocar no próximo login.
    senha_temporaria: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Identidade de remetente (cabeçalho do app + assinatura)
    whatsapp_remetente: Mapped[str | None] = mapped_column(String(40))
    email_remetente: Mapped[str | None] = mapped_column(String(180))

    # Conta de envio de e-mail (SMTP). A senha vai CRIPTOGRAFADA (ver crypto.py).
    email_senha_cripto: Mapped[str | None] = mapped_column(Text)
    provedor: Mapped[str] = mapped_column(String(20), default="outlook")
    smtp_host: Mapped[str] = mapped_column(String(120), default="smtp.office365.com")
    smtp_port: Mapped[int] = mapped_column(Integer, default=587)
    # Assinatura do e-mail (HTML), colada pelo usuário a partir do Outlook.
    assinatura: Mapped[str | None] = mapped_column(Text)

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    campanhas: Mapped[list["Campanha"]] = relationship(back_populates="usuario")


class Contato(Base):
    __tablename__ = "contatos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Código original do Agendor (identidade estável para evitar duplicar nomes iguais)
    agendor_id: Mapped[int | None] = mapped_column(Integer, unique=True, index=True)

    nome: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    empresa: Mapped[str | None] = mapped_column(String(255), index=True)
    cargo: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(180))
    whatsapp: Mapped[str | None] = mapped_column(String(20))  # só dígitos, com DDI 55
    categoria: Mapped[str] = mapped_column(String(80), default="Sem categoria", index=True)
    cidade: Mapped[str | None] = mapped_column(String(120))
    estado: Mapped[str | None] = mapped_column(String(60))

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora, onupdate=agora
    )

    def to_dict(self):
        return {
            "id": self.id,
            "nome": self.nome,
            "empresa": self.empresa or "",
            "cargo": self.cargo or "",
            "categoria": self.categoria or "Sem categoria",
            "whatsapp": self.whatsapp,
            "email": self.email,
        }


class Campanha(Base):
    """Histórico de cruzamentos de planilha (substitui a pasta historico/ + index.json)."""
    __tablename__ = "campanhas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    nome_orig: Mapped[str] = mapped_column(String(255))
    total: Mapped[int] = mapped_column(Integer, default=0)
    encontrados: Mapped[int] = mapped_column(Integer, default=0)
    nao_encontrados: Mapped[int] = mapped_column(Integer, default=0)
    # Guardamos o arquivo enviado para permitir reprocessar contra a base atualizada.
    arquivo_bytes: Mapped[bytes | None] = mapped_column(LargeBinary)
    arquivo_ext: Mapped[str | None] = mapped_column(String(10))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)

    usuario: Mapped["Usuario"] = relationship(back_populates="campanhas")


class Empresa(Base):
    """Base de EMPRESAS do Agendor (AGENDOR EMPRESAS.xlsx)."""
    __tablename__ = "empresas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    razao: Mapped[str | None] = mapped_column(String(255))
    cnpj: Mapped[str | None] = mapped_column(String(20))
    categoria: Mapped[str] = mapped_column(String(80), default="Sem categoria", index=True)
    origem: Mapped[str | None] = mapped_column(String(120))
    responsavel: Mapped[str | None] = mapped_column(String(120), index=True)
    whatsapp: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(180))
    cidade: Mapped[str | None] = mapped_column(String(120))
    estado: Mapped[str | None] = mapped_column(String(60))
    website: Mapped[str | None] = mapped_column(String(200))

    def to_dict(self):
        return {
            "nome": self.nome,
            "razao": self.razao or "",
            "cnpj": self.cnpj or "",
            "categoria": self.categoria or "Sem categoria",
            "origem": self.origem or "",
            "responsavel": self.responsavel or "",
            "whatsapp": self.whatsapp,
            "email": self.email,
            "cidade": self.cidade or "",
            "estado": self.estado or "",
            "website": self.website or "",
        }


class Tarefa(Base):
    """Envios (WhatsApp/E-mail) registrados como tarefas p/ exportar de volta ao Agendor."""
    __tablename__ = "tarefas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), index=True)
    quando: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora)
    canal: Mapped[str] = mapped_column(String(20))          # "WhatsApp" | "E-mail"
    nome: Mapped[str | None] = mapped_column(String(200))   # pessoa/contato
    empresa: Mapped[str | None] = mapped_column(String(255))
    whatsapp: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(180))
    categoria: Mapped[str | None] = mapped_column(String(80))
    descricao: Mapped[str | None] = mapped_column(Text)
    usuario_nome: Mapped[str | None] = mapped_column(String(120))  # quem realizou (do login)

    def to_dict(self):
        return {
            "id": self.id,
            "quando": self.quando.strftime("%d/%m/%Y %H:%M") if self.quando else "",
            "canal": self.canal or "",
            "nome": self.nome or "",
            "empresa": self.empresa or "",
            "whatsapp": self.whatsapp or "",
            "email": self.email or "",
            "categoria": self.categoria or "",
            "descricao": self.descricao or "",
            "usuario": self.usuario_nome or "",
        }
