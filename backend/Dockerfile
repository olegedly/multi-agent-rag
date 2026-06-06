# ============================================================
# Stage 1: Python dependencies
# ============================================================
FROM python:3.13-slim AS deps

WORKDIR /install

COPY pyproject.toml ./

RUN pip install --no-cache-dir --root-user-action=ignore --upgrade pip setuptools wheel && \
    pip install --no-cache-dir --root-user-action=ignore .

# ============================================================
# Stage 2: Runtime
# ============================================================
FROM python:3.13-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=deps /usr/local/bin/ /usr/local/bin/

COPY --from=deps /usr/local/lib/python3.13/site-packages \
                 /usr/local/lib/python3.13/site-packages

COPY backend/ /app/backend/

WORKDIR /app

# pyproject.toml so `fastapi run` can read [tool.fastapi] entrypoint
COPY --from=deps /install/pyproject.toml ./

EXPOSE 8000

CMD ["fastapi", "run", "--port", "8000", "--host", "0.0.0.0"]
