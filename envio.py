"""Camada de envio — desenhada para ser PLUGÁVEL.

Hoje o WhatsApp usa o modelo wa.me (gera links que o navegador do usuário abre,
grátis e sem risco de ban). Quando a Hevile tiver número dedicado + templates
aprovados + opt-in, basta implementar `ProvedorMetaCloud` e trocar o provedor —
o resto do sistema não muda.
"""
import smtplib
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from crypto import descripto


# ─────────────────────────── WhatsApp ───────────────────────────
class ProvedorWaMe:
    """Modelo atual: devolve links wa.me para o front abrir. Envio manual."""
    modo = "wa.me"

    def preparar(self, destinatarios, mensagem):
        links = []
        for c in destinatarios:
            numero = c.get("whatsapp")
            if not numero:
                continue
            texto = mensagem.replace("{nome}", c.get("nome", ""))
            url = "https://wa.me/" + numero + "?text=" + urllib.parse.quote(texto)
            links.append({"nome": c.get("nome", ""), "link": url})
        return {"modo": self.modo, "links": links}


class ProvedorMetaCloud:
    """STUB — futuro envio automático via WhatsApp Cloud API (Meta).

    Quando ativarmos: enviar template aprovado para cada destinatário com opt-in,
    respeitando os limites de qualidade da conta. Requer token + phone_number_id.
    """
    modo = "meta"

    def preparar(self, destinatarios, mensagem):
        raise NotImplementedError(
            "Envio automático pela Cloud API do Meta ainda não habilitado. "
            "Requer número dedicado, templates aprovados e opt-in dos contatos."
        )


# Provedor ativo (trocar aqui quando a Cloud API entrar)
PROVEDOR_WHATSAPP = ProvedorWaMe()


def preparar_whatsapp(destinatarios, mensagem):
    return PROVEDOR_WHATSAPP.preparar(destinatarios, mensagem)


# ─────────────────────────── E-mail (SMTP) ───────────────────────────
def _conectar_smtp(host, port, user, pwd):
    """Conexão SMTP autenticada. SSL na 465, STARTTLS nas demais."""
    if int(port) == 465:
        server = smtplib.SMTP_SSL(host, int(port), timeout=15)
    else:
        server = smtplib.SMTP(host, int(port), timeout=15)
        server.ehlo()
        server.starttls()
        server.ehlo()
    server.login(user, pwd)
    return server


def testar_conexao_email(host, port, user, pwd):
    """Retorna (ok, erro)."""
    try:
        server = _conectar_smtp(host, port, user, pwd)
        server.quit()
        return True, None
    except Exception as e:
        return False, str(e)


def enviar_emails(usuario, assunto, mensagem, destinatarios):
    """Envia um e-mail individual para cada destinatário (sem expor a lista).

    `usuario` é o modelo Usuario logado; a senha SMTP é descriptografada aqui.
    Retorna dict {ok, enviados, erros} ou {ok:False, erro}.
    """
    user = usuario.email_remetente
    pwd = descripto(usuario.email_senha_cripto)
    if not user or not pwd:
        return {"ok": False, "erro": "Configure seu e-mail e senha em ⚙️ Configurações."}

    host = usuario.smtp_host or "smtp.office365.com"
    port = usuario.smtp_port or 587
    nome_rem = usuario.nome or ""
    remetente = f"{nome_rem} <{user}>" if nome_rem else user

    enviados, erros = 0, []
    try:
        server = _conectar_smtp(host, port, user, pwd)
        for dest in destinatarios:
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = assunto
                msg["From"] = remetente
                msg["To"] = dest["email"]
                corpo = mensagem.replace("{nome}", dest.get("nome", ""))
                msg.attach(MIMEText(corpo, "plain", "utf-8"))
                server.sendmail(user, dest["email"], msg.as_string())
                enviados += 1
            except Exception as e:
                erros.append(f"{dest.get('email')}: {e}")
        server.quit()
        return {"ok": True, "enviados": enviados, "erros": erros}
    except Exception as e:
        return {"ok": False, "erro": str(e)}
