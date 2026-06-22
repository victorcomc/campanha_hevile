"""Comandos de gestão do sistema.

Uso:
  python manage.py init-db                              # cria as tabelas
  python manage.py importar "../AGENDOR PESSOAS.xlsx"   # importa a planilha (local)
  python manage.py seed-embed                           # importa do seed criptografado (no servidor)
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

SEED_FILE = "seed_data.enc"

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


def _linhas_da_planilha(caminho):
    """Lê o .xlsx e devolve uma lista de dicts já LIMPOS (telefone/e-mail corrigidos)."""
    df = pd.read_excel(caminho)
    faltando = [c for c in COLS if c not in df.columns]
    if faltando:
        print(f"⚠️  Colunas ausentes na planilha (serão ignoradas): {faltando}")
    registros = []
    for _, r in df.iterrows():
        agendor_id = r.get("Código da pessoa")
        registros.append({
            "agendor_id": int(agendor_id) if pd.notna(agendor_id) else None,
            "nome": _txt(r.get("Nome")) or "(sem nome)",
            "empresa": _txt(r.get("Empresa relacionada")),
            "cargo": _txt(r.get("Cargo")),
            "email": limpar_email(r.get("E-mail")),
            "whatsapp": limpar_telefone(r.get("WhatsApp")),
            "categoria": _txt(r.get("Categoria")) or "Sem categoria",
            "cidade": _txt(r.get("Cidade")),
            "estado": _txt(r.get("Estado")),
        })
    return registros


def _upsert(registros):
    """Insere/atualiza contatos a partir de uma lista de dicts limpos. Idempotente por agendor_id."""
    s = SessionLocal()
    novos = atualizados = sem_id = 0
    vistos, duplicatas = {}, []
    for d in registros:
        chave = (d["whatsapp"], d["email"])
        if d["whatsapp"] and d["email"]:
            if chave in vistos:
                duplicatas.append((d["nome"], vistos[chave], d["agendor_id"]))
            else:
                vistos[chave] = d["nome"]

        existente = None
        if d["agendor_id"] is not None:
            existente = s.query(Contato).filter_by(agendor_id=d["agendor_id"]).first()
        else:
            sem_id += 1

        if existente:
            for k, v in d.items():
                if k != "agendor_id":
                    setattr(existente, k, v)
            atualizados += 1
        else:
            s.add(Contato(**d))
            novos += 1

    s.commit()
    total = s.query(Contato).count()
    com_wpp = s.query(Contato).filter(Contato.whatsapp.isnot(None)).count()
    com_email = s.query(Contato).filter(Contato.email.isnot(None)).count()
    s.close()

    print("\n✅ Importação concluída.")
    print(f"   Novos: {novos} | Atualizados: {atualizados} | Sem código Agendor: {sem_id}")
    print(f"   Total no banco: {total} | com WhatsApp: {com_wpp} | com e-mail: {com_email}")
    if duplicatas:
        print(f"\n⚠️  {len(duplicatas)} possível(is) duplicata(s) real(is) (mesmo WhatsApp + e-mail):")
        for nome, outro, aid in duplicatas:
            print(f"     - {nome} (id {aid}) == {outro}")


def importar(caminho):
    _upsert(_linhas_da_planilha(caminho))


def gerar_seed(caminho_planilha, destino=SEED_FILE):
    """Lê a planilha, criptografa os contatos com a FERNET_KEY e grava o seed cifrado."""
    import gzip
    import json

    from crypto import _fernet

    registros = _linhas_da_planilha(caminho_planilha)
    bruto = gzip.compress(json.dumps(registros, ensure_ascii=False).encode("utf-8"))
    token = _fernet().encrypt(bruto)
    with open(destino, "wb") as f:
        f.write(token)
    print(f"✅ Seed criptografado gerado: {destino} ({len(token)} bytes, {len(registros)} contatos)")


def seed_embed(origem=SEED_FILE):
    """Lê o seed cifrado, descriptografa com a FERNET_KEY e popula o banco."""
    import gzip
    import json

    from crypto import _fernet

    with open(origem, "rb") as f:
        token = f.read()
    registros = json.loads(gzip.decompress(_fernet().decrypt(token)).decode("utf-8"))
    _upsert(registros)


def criar_usuario(nome, email, senha, is_admin=False):
    email = email.strip().lower()
    s = SessionLocal()
    if s.query(Usuario).filter_by(email=email).first():
        print(f"⚠️  Já existe usuário com e-mail {email}.")
        s.close()
        return
    u = Usuario(
        nome=nome, email=email, senha_hash=generate_password_hash(senha),
        is_admin=is_admin, email_remetente=email,
    )
    s.add(u)
    s.commit()
    s.close()
    tipo = "Admin" if is_admin else "Usuário"
    print(f"✅ {tipo} criado: {email}")


def main():
    p = argparse.ArgumentParser(description="Gestão do Campanha Hevile")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db", help="cria as tabelas no banco")

    pi = sub.add_parser("importar", help="importa a planilha (.xlsx) para o banco")
    pi.add_argument("caminho")

    pg = sub.add_parser("gerar-seed", help="gera o seed criptografado a partir da planilha")
    pg.add_argument("caminho")

    sub.add_parser("seed-embed", help="popula o banco a partir do seed criptografado")

    pa = sub.add_parser("criar-admin", help="cria um usuário administrador")
    pa.add_argument("--nome", required=True)
    pa.add_argument("--email", required=True)
    pa.add_argument("--senha", required=True)

    pu = sub.add_parser("criar-usuario", help="cria um usuário (use --admin para administrador)")
    pu.add_argument("--nome", required=True)
    pu.add_argument("--email", required=True)
    pu.add_argument("--senha", required=True)
    pu.add_argument("--admin", action="store_true", help="torna o usuário administrador")

    args = p.parse_args()

    if args.cmd == "init-db":
        init_db()
        print("✅ Tabelas criadas.")
    elif args.cmd == "importar":
        init_db()
        importar(args.caminho)
    elif args.cmd == "gerar-seed":
        gerar_seed(args.caminho)
    elif args.cmd == "seed-embed":
        init_db()
        seed_embed()
    elif args.cmd == "criar-admin":
        init_db()
        criar_usuario(args.nome, args.email, args.senha, is_admin=True)
    elif args.cmd == "criar-usuario":
        init_db()
        criar_usuario(args.nome, args.email, args.senha, is_admin=args.admin)


if __name__ == "__main__":
    sys.exit(main())
