"""Parsing e carga das bases do Agendor (Pessoas e Empresas) a partir de DataFrames.

Reaproveitado pelo manage.py (seed/CLI) e pelas rotas de upload do app.py.
"""
import pandas as pd

from models import Contato, Empresa
from utils import limpar_email, limpar_telefone


def _txt(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return s or None


def parse_contatos_df(df):
    """DataFrame da exportação de PESSOAS do Agendor -> lista de dicts limpos."""
    regs = []
    for _, r in df.iterrows():
        aid = r.get("Código da pessoa")
        regs.append({
            "agendor_id": int(aid) if pd.notna(aid) else None,
            "nome": _txt(r.get("Nome")) or "(sem nome)",
            "empresa": _txt(r.get("Empresa relacionada")),
            "cargo": _txt(r.get("Cargo")),
            "email": limpar_email(r.get("E-mail")),
            "whatsapp": limpar_telefone(r.get("WhatsApp")),
            "categoria": _txt(r.get("Categoria")) or "Sem categoria",
            "cidade": _txt(r.get("Cidade")),
            "estado": _txt(r.get("Estado")),
        })
    return regs


def parse_empresas_df(df):
    """DataFrame da exportação de EMPRESAS do Agendor -> lista de dicts limpos."""
    regs = []
    for _, r in df.iterrows():
        nome = _txt(r.get("Nome Fantasia")) or _txt(r.get("Razão Social"))
        if not nome:
            continue
        zap = (limpar_telefone(r.get("WhatsApp"))
               or limpar_telefone(r.get("Celular"))
               or limpar_telefone(r.get("Telefone")))
        cnpj_raw = _txt(r.get("CNPJ")) or ""
        cnpj = "".join(c for c in cnpj_raw.split(".")[0] if c.isdigit())
        regs.append({
            "nome": nome,
            "razao": _txt(r.get("Razão Social")),
            "cnpj": cnpj or None,
            "categoria": _txt(r.get("Categoria")) or "Sem categoria",
            "origem": _txt(r.get("Origem do cliente")),
            "responsavel": _txt(r.get("Usuário responsável")),
            "whatsapp": zap,
            "email": limpar_email(r.get("E-mail")),
            "cidade": _txt(r.get("Cidade")),
            "estado": _txt(r.get("Estado")),
            "website": _txt(r.get("Website")),
        })
    return regs


def upsert_contatos(session, registros):
    """Insere/atualiza contatos por agendor_id (preserva edições manuais e ids)."""
    novos = atualizados = 0
    for d in registros:
        existente = None
        if d["agendor_id"] is not None:
            existente = session.query(Contato).filter_by(agendor_id=d["agendor_id"]).first()
        if existente:
            for k, v in d.items():
                if k != "agendor_id":
                    setattr(existente, k, v)
            atualizados += 1
        else:
            session.add(Contato(**d))
            novos += 1
    session.commit()
    return {"novos": novos, "atualizados": atualizados, "total": session.query(Contato).count()}


def substituir_empresas(session, registros):
    """Substitui toda a base de empresas (a exportação do Agendor é a fonte da verdade)."""
    session.query(Empresa).delete()
    for d in registros:
        session.add(Empresa(**d))
    session.commit()
    return {"total": len(registros)}
