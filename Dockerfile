# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

ARG INSTALL_DEV=0

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements/ requirements/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements/base.txt && \
    if [ "$INSTALL_DEV" = "1" ] || [ "$INSTALL_DEV" = "true" ]; then \
        pip install --no-cache-dir -r requirements/dev.txt; \
    fi

FROM python:3.12-slim AS final

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --home-dir /home/appuser --shell /bin/bash appuser

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

RUN mkdir -p /app/media /app/staticfiles && \
    chown -R appuser:appuser /app

COPY --chown=appuser:appuser . /app
RUN chmod +x /app/docker/entrypoint.sh

USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
