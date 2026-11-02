# PMI quant engine (FastAPI) — production image, built from the monorepo root context.
FROM python:3.13-slim

RUN useradd -m appuser
WORKDIR /engine

COPY services/quant-engine/pyproject.toml ./
COPY services/quant-engine/app ./app
COPY services/quant-engine/providers ./providers
COPY services/quant-engine/ingestion ./ingestion
COPY services/quant-engine/indicators ./indicators
RUN pip install --no-cache-dir . \
    && chown -R appuser:appuser /engine

USER appuser
EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
