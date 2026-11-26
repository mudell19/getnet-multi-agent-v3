FROM python:3.12-slim@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    TZ=America/Sao_Paulo

RUN pip install --no-cache-dir uv==0.13.6 && useradd --uid 10001 --create-home app

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev
COPY data/crawl_cache ./data/crawl_cache
COPY data/merchants.json ./data/merchants.json
RUN mkdir -p /app/data/state && chown -R app:app /app/data/state

ARG REV=dev
ENV APP_REV=$REV PATH=/app/.venv/bin:$PATH
LABEL org.opencontainers.image.revision=$REV

USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=180s --retries=12 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=4)"
CMD ["uvicorn", "getnet_multi_agent.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
