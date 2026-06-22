"""Camada de envio — desenhada para ser PLUGÁVEL.

Hoje o WhatsApp usa o modelo wa.me (gera links que o navegador do usuário abre,
grátis e sem risco de ban). Quando a Hevile tiver número dedicado + templates
aprovados + opt-in, basta implementar `ProvedorMetaCloud` e trocar o provedor —
o resto do sistema não muda.
"""
import base64
import html
import re
import smtplib
import urllib.parse
from email import encoders
from email.mime.base import MIMEBase
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


def _montar_anexos(msg, anexos):
    """Anexa arquivos (lista de {filename, mimetype, b64}) à mensagem."""
    for a in anexos or []:
        try:
            conteudo = base64.b64decode(a.get("b64", ""))
        except Exception:
            continue
        part = MIMEBase("application", "octet-stream")
        part.set_payload(conteudo)
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition", f'attachment; filename="{a.get("filename", "anexo")}"'
        )
        msg.attach(part)


def enviar_emails(usuario, assunto, mensagem, destinatarios, anexos=None):
    """Envia um e-mail individual para cada destinatário (sem expor a lista).

    Cada destinatário pode trazer um `corpo` já personalizado (vindo do front);
    senão usamos `mensagem` com {nome} substituído. `anexos` vão em todos.
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

    assinatura = (usuario.assinatura or "").strip()
    enviados, erros = 0, []
    try:
        server = _conectar_smtp(host, port, user, pwd)
        for dest in destinatarios:
            try:
                outer = MIMEMultipart("mixed")
                outer["Subject"] = assunto
                outer["From"] = remetente
                outer["To"] = dest["email"]

                # corpo já personalizado pelo front, ou fallback com {nome}
                corpo = dest.get("corpo") or mensagem.replace("{nome}", dest.get("nome", ""))

                if assinatura:
                    # e-mail em HTML (assinatura com logo/formatação) + alternativa em texto
                    alt = MIMEMultipart("alternative")
                    texto = corpo + "\n\n" + re.sub(r"<[^>]+>", "", assinatura).strip()
                    alt.attach(MIMEText(texto, "plain", "utf-8"))
                    corpo_html = html.escape(corpo).replace("\n", "<br>")
                    html_body = (
                        '<div style="font-family:Arial,sans-serif;font-size:14px;color:#222">'
                        f"{corpo_html}</div><br>{assinatura}"
                    )
                    alt.attach(MIMEText(html_body, "html", "utf-8"))
                    outer.attach(alt)
                else:
                    outer.attach(MIMEText(corpo, "plain", "utf-8"))

                _montar_anexos(outer, anexos)
                server.sendmail(user, dest["email"], outer.as_string())
                enviados += 1
            except Exception as e:
                erros.append(f"{dest.get('email')}: {e}")
        server.quit()
        return {"ok": True, "enviados": enviados, "erros": erros}
    except Exception as e:
        return {"ok": False, "erro": str(e)}
