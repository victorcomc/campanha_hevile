# Campanha Hevile — versão web

Reescrita web/multiusuário do app de campanhas. Substitui o `.exe` + planilha Excel por:

- **Banco de dados PostgreSQL** (sem corromper com acesso simultâneo)
- **Login por usuário** (cada um com sua identidade e conta de e-mail própria)
- **WhatsApp via wa.me** (grátis), com a arquitetura pronta para a **Cloud API do Meta** no futuro (ver `envio.py`)
- Correção do **bug do WhatsApp** (número não ganha mais um `0` no fim)
- Edição de contato por **ID** (resolve o problema dos nomes repetidos)

## Estrutura

| Arquivo | O que faz |
|---|---|
| `app.py` | Aplicação Flask + todas as rotas |
| `models.py` | Tabelas: `usuarios`, `contatos`, `campanhas` |
| `db.py` / `config.py` | Conexão e configuração (tudo via variável de ambiente) |
| `envio.py` | Camada de envio (WhatsApp wa.me + e-mail SMTP; stub do Meta) |
| `crypto.py` | Criptografa a senha de e-mail dos usuários |
| `utils.py` | Limpeza de telefone (com a correção) e fuzzy match |
| `manage.py` | Comandos: `init-db`, `importar`, `criar-admin` |
| `templates/` | `index.html` (app) e `login.html` |
| `Dockerfile` | Imagem de produção (gunicorn) |

---

## Rodar localmente (desenvolvimento)

```bash
pip install -r requirements.txt

# 1. cria as tabelas (usa SQLite local se DATABASE_URL estiver vazio)
python manage.py init-db

# 2. importa a planilha para o banco (já corrige os WhatsApp)
python manage.py importar "../AGENDOR PESSOAS.xlsx"

# 3. cria seu usuário
python manage.py criar-admin --nome "Victor" --email victor.gabriele@hevile.com.br --senha "suaSenha"

# 4. sobe o app
python app.py            # http://127.0.0.1:5000
```

---

## Deploy no Coolify (Hetzner)

### 1. Suba este projeto para um repositório Git (GitHub/GitLab)

### 2. Crie o banco no Coolify
- **+ New Resource → Database → PostgreSQL**
- Anote a **Connection String interna** (algo como
  `postgres://usuario:senha@nome-do-servico:5432/banco`).

### 3. Crie a aplicação no Coolify
- **+ New Resource → Application → do seu repositório Git**
- Build Pack: **Dockerfile** (este projeto já tem)
- Porta exposta: **8000**

### 4. Configure as variáveis de ambiente (aba *Environment Variables*)
```
DATABASE_URL = postgres://usuario:senha@nome-do-servico:5432/banco   (a do passo 2)
SECRET_KEY   = (gere: python -c "import secrets; print(secrets.token_hex(32))")
FERNET_KEY   = (gere: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
```
> Guarde a `FERNET_KEY` — se ela mudar, as senhas de e-mail já salvas param de funcionar.

### 5. Deploy
O container roda `init-db` (cria as tabelas) e sobe o gunicorn automaticamente.
Configure o domínio/HTTPS no próprio Coolify.

### 6. Importar a base e criar o primeiro usuário (uma vez)
Mais fácil rodar **da sua máquina apontando para o Postgres do Coolify**
(exponha a porta do banco no Coolify ou rode via terminal do container):

```bash
# no seu PC, com a DATABASE_URL pública do Postgres do Coolify:
set DATABASE_URL=postgres://usuario:senha@HOST_PUBLICO:5432/banco   # (PowerShell: $env:DATABASE_URL=...)
python manage.py importar "../AGENDOR PESSOAS.xlsx"
python manage.py criar-admin --nome "Victor" --email victor.gabriele@hevile.com.br --senha "..."
```

Pronto — acesse o domínio, faça login e use.

---

## Ligar a Cloud API do Meta no futuro

Em `envio.py` já existe a classe `ProvedorMetaCloud` (stub). Quando a Hevile tiver
número dedicado, templates aprovados e opt-in dos contatos, basta implementá-la e
trocar `PROVEDOR_WHATSAPP = ProvedorMetaCloud(...)`. O resto do sistema não muda.
