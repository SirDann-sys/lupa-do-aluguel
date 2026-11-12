# syntax=docker/dockerfile:1

# 1) Dependências compiladas num estágio separado: a imagem final não leva pip cache.
FROM python:3.12-slim AS dependencias
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/instalado -r requirements.txt

# 2) Imagem final: só o runtime, o código e um usuário sem privilégios.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000
RUN useradd --create-home --uid 10001 lupa && mkdir -p /srv/backend && chown lupa:lupa /srv/backend
COPY --from=dependencias /instalado /usr/local
WORKDIR /srv/backend
COPY --chown=lupa:lupa backend/alembic.ini ./
COPY --chown=lupa:lupa backend/migrations ./migrations
COPY --chown=lupa:lupa backend/app ./app
USER lupa
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health', timeout=4)"
# Migra o banco e sobe a API. --proxy-headers: o Render fica na frente, com HTTPS.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app_producao --factory --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
