"""Comandos de gestão do sistema.

Uso:
  python manage.py init-db                          # cria as tabelas
  python manage.py importar "../AGENDOR PESSOAS.xlsx"  # importa a planilha para o banco
  python manage.py criar-admin --nome "Victor" --email victor@hevile.com.br --senha "..."
"""
import argparse
import sys

# Console do Windows usa cp1252 e quebra com emoji/acentos — força UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import pandas as pd
from werkzeug.security import generate_password_hash

from db import SessionLocal, init_db
from models import Contato, Usuario
from utils import limpar_email, limpar_telefone

# Mapa: coluna da planilha do Agendor -> campo do nosso modelo
COLS = {
    "Código da pessoa": "agendor_id",
    "Nome": "nome",
    "Empresa relacionada": "empresa",
    "Cargo": "cargo",
    "E-mail": "email",
    "WhatsApp": "whatsapp",
    "Categoria": "categoria",
    "Cidade": "cidade",
    "Estado": "estado",
}


def _txt(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return s or None


def importar(caminho: str):
    df = pd.read_excel(caminho)
    faltando = [c for c in COLS if c not in df.columns]
    if faltando:
        print(f"⚠️  Colunas ausentes na planilha (serão ignoradas): {faltando}")

    s = SessionLocal()
    novos = atualizados = sem_id = 0
    vistos_contato = {}      # (whatsapp,email) -> nome  (para detectar duplicatas reais)
    duplicatas = []

    for _, r in df.iterrows():
        nome = _txt(r.get("Nome")) or "(sem nome)"
        agendor_id = r.get("Código da pessoa")
        agendor_id = int(agendor_id) if pd.notna(agendor_id) else None

        whatsapp = limpar_telefone(r.get("WhatsApp"))
        email = limpar_email(r.get("E-mail"))

        # detecta duplicata real (mesma pessoa cadastrada 2x): mesmo zap + mesmo email
        chave = (whatsapp, email)
        if whatsapp and email and chave in vistos_contato:
            duplicatas.append((nome, vistos_contato[chave], agendor_id))
        elif whatsapp and email:
            vistos_contato[chave] = nome

        dados = dict(
            nome=nome,
            empresa=_txt(r.get("Empresa relacionada")),
            cargo=_txt(r.get("Cargo")),
            email=email,
            whatsapp=whatsapp,
            categoria=_txt(r.get("Categoria")) or "Sem categoria",
            cidade=_txt(r.get("Cidade")),
            estado=_txt(r.get("Estado")),
        )

        existente = None
        if agendor_id is not None:
            existente = s.query(Contato).filter_by(agendor_id=agendor_id).first()
        else:
            sem_id += 1

        if existente:
            for k, v in dados.items():
                setattr(existente, k, v)
            atualizados += 1
        else:
            s.add(Contato(agendor_id=agendor_id, **dados))
            novos += 1

    s.commit()
    total = s.query(Contato).count()
    com_wpp = s.query(Contato).filter(Contato.whatsapp.isnot(None)).count()
    com_email = s.query(Contato).filter(Contato.email.isnot(None)).count()
    s.close()

    print(f"\n✅ Importação concluída.")
    print(f"   Novos: {novos} | Atualizados: {atualizados} | Sem código Agendor: {sem_id}")
    print(f"   Total no banco: {total} | com WhatsApp: {com_wpp} | com e-mail: {com_email}")
    if duplicatas:
        print(f"\n⚠️  {len(duplicatas)} possível(is) duplicata(s) real(is) (mesmo WhatsApp + e-mail):")
        for nome, outro, aid in duplicatas:
            print(f"     - {nome} (id {aid}) == {outro}")


def criar_admin(nome, email, senha):
    s = SessionLocal()
    if s.query(Usuario).filter_by(email=email).first():
        print(f"⚠️  Já existe usuário com e-mail {email}.")
        s.close()
        return
    u = Usuario(
        nome=nome,
        email=email,
        senha_hash=generate_password_hash(senha),
        is_admin=True,
        email_remetente=email,
    )
    s.add(u)
    s.commit()
    s.close()
    print(f"✅ Admin criado: {email}")


def main():
    p = argparse.ArgumentParser(description="Gestão do Campanha Hevile")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db", help="cria as tabelas no banco")

    pi = sub.add_parser("importar", help="importa a planilha para o banco")
    pi.add_argument("caminho", help="caminho do .xlsx")

    pa = sub.add_parser("criar-admin", help="cria um usuário administrador")
    pa.add_argument("--nome", required=True)
    pa.add_argument("--email", required=True)
    pa.add_argument("--senha", required=True)

    args = p.parse_args()

    if args.cmd == "init-db":
        init_db()
        print("✅ Tabelas criadas.")
    elif args.cmd == "importar":
        init_db()
        importar(args.caminho)
    elif args.cmd == "criar-admin":
        init_db()
        criar_admin(args.nome, args.email, args.senha)


if __name__ == "__main__":
    sys.exit(main())
