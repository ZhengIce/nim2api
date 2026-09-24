# syntax=docker/dockerfile:1

FROM node:20-alpine AS frontend

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    NIM_GATEWAY_CONFIG=/config/config.toml \
    NIM_GATEWAY_DATA_DIR=/data

ARG APP_UID=10001
ARG APP_GID=10001

RUN groupadd --gid "${APP_GID}" gateway \
    && useradd --uid "${APP_UID}" --gid gateway --create-home --shell /usr/sbin/nologin gateway

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=gateway:gateway *.py config.example.toml README.md ./
COPY --from=frontend --chown=gateway:gateway /build/static ./static

RUN mkdir -p /config /data \
    && touch /config/.keep /data/.keep \
    && chown -R gateway:gateway /app /config /data

USER gateway

EXPOSE 5010

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5010/healthz', timeout=3).read()"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5010"]
