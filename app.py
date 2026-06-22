"""Campanha Hevile — versão web multiusuário (Flask + PostgreSQL).

Substitui o app antigo (.exe + planilha Excel). Mesmas funcionalidades, agora:
  - banco de dados de verdade (sem corromper com acesso simultâneo)
  - login por usuário (cada um com sua identidade e conta de e-mail)
  - WhatsApp via wa.me, com camada pronta para a Cloud API do Meta (ver envio.py)
"""
import csv
import io
from functools import wraps

import pandas as pd
from flask import (
    Flask, jsonify, redirect, render_template, request, url_for,
)
from flask_login import (
    LoginManager, current_user, login_required, login_user, logout_user,
)
from werkzeug.security import check_password_hash, generate_password_hash

import envio
from config import Config
from crypto import cripto
from db import SessionLocal, init_db
from models import Campanha, Contato, Usuario
from utils import limpar_email, limpar_telefone, similaridade

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,   # JS não acessa o cookie de sessão
    SESSION_COOKIE_SAMESITE="Lax",  # mitiga CSRF
    MAX_CONTENT_LENGTH=30 * 1024 * 1024,  # limite de 30MB (planilhas + anexos de e-mail)
)

login_manager = LoginManager(app)
login_manager.login_view = "login"

# Colunas de nome/empresa que procuramos na planilha de campanha (em ordem de prioridade)
PRIORIDADE = ["CONSIGNATÁRIO", "CONSIGNATARIO", "IMPORTADOR", "EMPRESA",
              "RAZÃO SOCIAL", "RAZAO SOCIAL", "SHIPPER", "NOME"]

SCORE_MINIMO = 55  # corte de similaridade para considerar "encontrado"


@login_manager.user_loader
def carregar_usuario(uid):
    return SessionLocal().get(Usuario, int(uid))


@app.teardown_appcontext
def encerrar_sessao(exc=None):
    SessionLocal.remove()


def db():
    return SessionLocal()


def admin_required(f):
    """Protege rotas que só administradores podem acessar."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("login"))
        if not current_user.is_admin:
            return jsonify(ok=False, erro="Apenas administradores podem fazer isso."), 403
        return f(*args, **kwargs)
    return wrapper


# ─────────────────────────── Autenticação ───────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        senha = request.form.get("senha") or ""
        u = db().query(Usuario).filter(Usuario.email == email).first()
        if u and check_password_hash(u.senha_hash, senha):
            login_user(u)
            return redirect(url_for("index"))
        return render_template("login.html", erro="E-mail ou senha incorretos."), 401
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/trocar_senha", methods=["GET", "POST"])
@login_required
def trocar_senha():
    forcado = current_user.senha_temporaria
    if request.method == "POST":
        atual = request.form.get("atual") or ""
        nova = request.form.get("nova") or ""
        conf = request.form.get("conf") or ""
        # Em troca voluntária exige a senha atual; na forçada a pessoa acabou de logar com ela.
        if not forcado and not check_password_hash(current_user.senha_hash, atual):
            return render_template("trocar_senha.html", forcado=forcado, erro="Senha atual incorreta."), 401
        if len(nova) < 6:
            return render_template("trocar_senha.html", forcado=forcado, erro="A nova senha deve ter pelo menos 6 caracteres."), 400
        if nova != conf:
            return render_template("trocar_senha.html", forcado=forcado, erro="As senhas não conferem."), 400
        s = db()
        u = s.get(Usuario, current_user.id)
        u.senha_hash = generate_password_hash(nova)
        u.senha_temporaria = False
        s.commit()
        return redirect(url_for("index"))
    return render_template("trocar_senha.html", forcado=forcado)


# ─────────────────────────── Página principal ───────────────────────────
@app.route("/")
@login_required
def index():
    # Se a senha foi definida por um admin, obriga a trocar antes de usar o sistema.
    if current_user.senha_temporaria:
        return redirect(url_for("trocar_senha"))
    s = db()
    categorias = sorted({
        c[0] for c in s.query(Contato.categoria).distinct() if c[0]
    })
    total = s.query(Contato).count()
    com_whatsapp = s.query(Contato).filter(Contato.whatsapp.isnot(None)).count()
    com_email = s.query(Contato).filter(Contato.email.isnot(None)).count()
    return render_template(
        "index.html",
        categorias=categorias,
        total=total,
        com_whatsapp=com_whatsapp,
        com_email=com_email,
        nome_remetente=current_user.nome or "",
        whatsapp_remetente=current_user.whatsapp_remetente or "",
        email_remetente=current_user.email_remetente or "",
        is_admin=current_user.is_admin,
    )


# ─────────────────────────── Gestão de usuários (admin) ───────────────────────────
@app.route("/usuarios")
@admin_required
def listar_usuarios():
    s = db()
    us = s.query(Usuario).order_by(Usuario.nome).all()
    return jsonify([
        {"id": u.id, "nome": u.nome, "email": u.email, "is_admin": u.is_admin}
        for u in us
    ])


@app.route("/criar_usuario", methods=["POST"])
@admin_required
def criar_usuario():
    data = request.json or {}
    nome = (data.get("nome") or "").strip()
    email = (data.get("email") or "").strip().lower()
    senha = data.get("senha") or ""
    is_admin = bool(data.get("is_admin"))
    if not nome or not email or not senha:
        return jsonify(ok=False, erro="Preencha nome, e-mail e senha.")
    if len(senha) < 6:
        return jsonify(ok=False, erro="A senha deve ter pelo menos 6 caracteres.")
    s = db()
    if s.query(Usuario).filter(Usuario.email == email).first():
        return jsonify(ok=False, erro="Já existe um usuário com esse e-mail.")
    try:
        u = Usuario(
            nome=nome, email=email,
            senha_hash=generate_password_hash(senha),
            is_admin=is_admin, email_remetente=email,
            senha_temporaria=True,  # força a pessoa a definir a própria senha no 1º login
        )
        s.add(u)
        s.commit()
        return jsonify(ok=True, id=u.id)
    except Exception as e:
        return jsonify(ok=False, erro=str(e))


@app.route("/resetar_senha", methods=["POST"])
@admin_required
def resetar_senha():
    data = request.json or {}
    uid = data.get("id")
    nova = data.get("senha") or ""
    if len(nova) < 6:
        return jsonify(ok=False, erro="A senha deve ter pelo menos 6 caracteres.")
    s = db()
    u = s.get(Usuario, int(uid)) if uid is not None else None
    if not u:
        return jsonify(ok=False, erro="Usuário não encontrado.")
    u.senha_hash = generate_password_hash(nova)
    u.senha_temporaria = True  # ao admin resetar, a pessoa redefine no próximo login
    s.commit()
    return jsonify(ok=True)


@app.route("/excluir_usuario", methods=["POST"])
@admin_required
def excluir_usuario():
    data = request.json or {}
    uid = int(data.get("id")) if data.get("id") is not None else None
    if uid == current_user.id:
        return jsonify(ok=False, erro="Você não pode excluir o próprio usuário.")
    s = db()
    u = s.get(Usuario, uid) if uid is not None else None
    if not u:
        return jsonify(ok=False, erro="Usuário não encontrado.")
    s.delete(u)
    s.commit()
    return jsonify(ok=True)


# ─────────────────────────── Contatos ───────────────────────────
@app.route("/contatos")
@login_required
def contatos():
    s = db()
    categoria = request.args.get("categoria", "")
    canal = request.args.get("canal", "todos")
    q = s.query(Contato)
    if categoria:
        q = q.filter(Contato.categoria == categoria)
    if canal == "whatsapp":
        q = q.filter(Contato.whatsapp.isnot(None))
    elif canal == "email":
        q = q.filter(Contato.email.isnot(None))
    dados = [c.to_dict() for c in q.order_by(Contato.nome).all()]
    return jsonify(dados)


@app.route("/adicionar_contato", methods=["POST"])
@login_required
def adicionar_contato():
    data = request.json or {}
    nome = (data.get("nome") or "").strip()
    if not nome:
        return jsonify(ok=False, erro="Nome é obrigatório.")
    try:
        s = db()
        c = Contato(
            nome=nome,
            empresa=(data.get("empresa") or "").strip() or None,
            cargo=(data.get("cargo") or "").strip() or None,
            email=limpar_email(data.get("email")),
            whatsapp=limpar_telefone(data.get("whatsapp")),
            categoria=(data.get("categoria") or "").strip() or "Sem categoria",
        )
        s.add(c)
        s.commit()
        return jsonify(ok=True, id=c.id)
    except Exception as e:
        return jsonify(ok=False, erro=str(e))


@app.route("/editar_contato", methods=["POST"])
@login_required
def editar_contato():
    data = request.json or {}
    # Agora identificamos pelo ID (não pelo nome) — resolve o problema dos nomes repetidos.
    cid = data.get("id")
    try:
        s = db()
        c = s.get(Contato, int(cid)) if cid is not None else None
        if not c:
            return jsonify(ok=False, erro="Contato não encontrado.")
        if "whatsapp" in data:
            c.whatsapp = limpar_telefone(data.get("whatsapp"))
        if "email" in data:
            c.email = limpar_email(data.get("email"))
        if data.get("categoria"):
            c.categoria = data["categoria"]
        s.commit()
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, erro=str(e))


# ─────────────────────────── Envio ───────────────────────────
@app.route("/enviar_whatsapp", methods=["POST"])
@login_required
def enviar_whatsapp():
    data = request.json or {}
    mensagem = data.get("mensagem", "")
    destinatarios = data.get("destinatarios", [])
    if not mensagem.strip():
        return jsonify(ok=False, erro="Escreva a mensagem antes de enviar.")
    resultado = envio.preparar_whatsapp(destinatarios, mensagem)
    return jsonify(ok=True, **resultado)


@app.route("/enviar_email", methods=["POST"])
@login_required
def enviar_email():
    data = request.json or {}
    assunto = data.get("assunto", "")
    mensagem = data.get("mensagem", "")
    destinatarios = data.get("destinatarios", [])
    anexos = data.get("anexos", [])
    return jsonify(envio.enviar_emails(current_user, assunto, mensagem, destinatarios, anexos))


# ─────────────────────────── Configurações do usuário ───────────────────────────
@app.route("/config")
@login_required
def get_config():
    u = current_user
    return jsonify(
        nome=u.nome or "",
        whatsapp=u.whatsapp_remetente or "",
        email=u.email_remetente or "",
        tem_senha=bool(u.email_senha_cripto),  # nunca devolvemos a senha em si
        provedor=u.provedor or "outlook",
        smtp_host=u.smtp_host or "smtp.office365.com",
        smtp_port=str(u.smtp_port or 587),
        assinatura=u.assinatura or "",
    )


@app.route("/salvar_config", methods=["POST"])
@login_required
def salvar_config():
    data = request.json or {}
    if not (data.get("email") or "").strip():
        return jsonify(ok=False, erro="Informe o e-mail de saída.")
    try:
        s = db()
        u = s.get(Usuario, current_user.id)
        u.nome = (data.get("nome") or "").strip()
        u.whatsapp_remetente = (data.get("whatsapp") or "").strip()
        u.email_remetente = (data.get("email") or "").strip()
        u.provedor = data.get("provedor") or "outlook"
        u.smtp_host = (data.get("smtp_host") or "smtp.office365.com").strip()
        u.smtp_port = int(data.get("smtp_port") or 587)
        if "assinatura" in data:
            u.assinatura = data.get("assinatura") or None
        # só atualiza a senha se o usuário digitou uma nova (senão mantém a atual)
        if data.get("senha"):
            u.email_senha_cripto = cripto(data["senha"])
        s.commit()
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, erro=str(e))


@app.route("/testar_email", methods=["POST"])
@login_required
def testar_email():
    data = request.json or {}
    host = data.get("smtp_host", "smtp.office365.com")
    port = data.get("smtp_port", 587)
    user = (data.get("email") or "").strip()
    pwd = data.get("senha") or ""
    # se o usuário não redigitou a senha, usa a já salva (criptografada)
    if not pwd and current_user.email_senha_cripto:
        from crypto import descripto
        pwd = descripto(current_user.email_senha_cripto)
    if not user or not pwd:
        return jsonify(ok=False, erro="Preencha o e-mail e a senha antes de testar.")
    ok, erro = envio.testar_conexao_email(host, port, user, pwd)
    return jsonify(ok=ok, erro=erro)


# ─────────────────────────── Cruzamento de campanha ───────────────────────────
def _ler_planilha(file_bytes, filename):
    if filename.lower().endswith(".csv"):
        # Detecta o separador entre candidatos comuns (NÃO usar sep=None: ele
        # pode "adivinhar" uma letra como separador e quebrar a planilha).
        amostra = file_bytes[:8192].decode("utf-8", errors="replace")
        try:
            sep = csv.Sniffer().sniff(amostra, delimiters=[",", ";", "\t", "|"]).delimiter
        except Exception:
            sep = ";" if amostra.count(";") > amostra.count(",") else ","
        for enc in ("utf-8-sig", "latin-1"):
            try:
                return pd.read_csv(io.BytesIO(file_bytes), sep=sep, engine="python", encoding=enc)
            except Exception:
                continue
        return pd.read_csv(io.BytesIO(file_bytes), sep=sep, engine="python", encoding="latin-1")
    return pd.read_excel(io.BytesIO(file_bytes))


def _cruzar(df_camp):
    colunas_norm = {str(c).strip().upper(): c for c in df_camp.columns}
    col = next((colunas_norm[p] for p in PRIORIDADE if p in colunas_norm), df_camp.columns[0])
    nomes = df_camp[col].dropna().astype(str).str.strip().unique().tolist()
    nomes = [n for n in nomes if n and n.lower() != "nan"]

    base = [(c.nome or "", c.empresa or "", c) for c in db().query(Contato).all()]
    encontrados, nao_encontrados, ja = [], [], set()
    for nome_p in nomes:
        melhor_score, melhor = 0, None
        for nome_c, emp_c, c in base:
            sc = max(similaridade(nome_p, nome_c), similaridade(nome_p, emp_c))
            if sc > melhor_score:
                melhor_score, melhor = sc, c
        if melhor is not None and melhor_score >= SCORE_MINIMO and melhor.id not in ja:
            ja.add(melhor.id)
            encontrados.append(
                {"nome_planilha": nome_p, "score": melhor_score, "contato": melhor.to_dict()}
            )
        else:
            nao_encontrados.append(nome_p)
    encontrados.sort(key=lambda x: x["score"], reverse=True)
    return {"total": len(nomes), "encontrados": encontrados, "nao_encontrados": nao_encontrados}


@app.route("/cruzar_campanha", methods=["POST"])
@login_required
def cruzar_campanha():
    file = request.files.get("arquivo")
    if not file:
        return jsonify(ok=False, erro="Nenhum arquivo enviado.")
    try:
        file_bytes = file.read()
        df_camp = _ler_planilha(file_bytes, file.filename)
    except Exception as e:
        return jsonify(ok=False, erro=f"Erro ao ler o arquivo: {e}")

    resultado = _cruzar(df_camp)

    try:
        s = db()
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "xlsx"
        camp = Campanha(
            usuario_id=current_user.id,
            nome_orig=file.filename,
            total=resultado["total"],
            encontrados=len(resultado["encontrados"]),
            nao_encontrados=len(resultado["nao_encontrados"]),
            arquivo_bytes=file_bytes,
            arquivo_ext=ext,
        )
        s.add(camp)
        s.commit()
    except Exception as e:
        app.logger.error(f"Erro ao salvar histórico: {e}")

    return jsonify(ok=True, **resultado)


@app.route("/historico")
@login_required
def get_historico():
    s = db()
    itens = (
        s.query(Campanha)
        .filter(Campanha.usuario_id == current_user.id)
        .order_by(Campanha.criado_em.desc())
        .limit(20)
        .all()
    )
    return jsonify([
        {
            "id": c.id,
            "nome_orig": c.nome_orig,
            "data": c.criado_em.strftime("%d/%m/%Y %H:%M") if c.criado_em else "",
            "total": c.total,
            "encontrados": c.encontrados,
        }
        for c in itens
    ])


@app.route("/reprocessar/<int:cid>")
@login_required
def reprocessar(cid):
    s = db()
    camp = s.get(Campanha, cid)
    if not camp or camp.usuario_id != current_user.id:
        return jsonify(ok=False, erro="Arquivo não encontrado no histórico.")
    if not camp.arquivo_bytes:
        return jsonify(ok=False, erro="Arquivo físico não encontrado.")
    try:
        df_camp = _ler_planilha(camp.arquivo_bytes, f"x.{camp.arquivo_ext or 'xlsx'}")
    except Exception as e:
        return jsonify(ok=False, erro=f"Erro ao ler o arquivo: {e}")
    return jsonify(ok=True, **_cruzar(df_camp))


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000, host="127.0.0.1")
