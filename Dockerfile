FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Cria as tabelas (idempotente) e sobe o servidor de produção (gunicorn).
CMD ["sh", "-c", "python manage.py init-db && gunicorn -b 0.0.0.0:8000 -w 2 --timeout 120 app:app"]
