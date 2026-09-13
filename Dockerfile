# RAG-EVDA — enterprise AI-search visibility auditor
# Build:  docker build -t ragevda .
# Run:    docker compose up web   (or: docker run --rm -p 9000:9000 ragevda)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_OFFLINE=0

WORKDIR /app

# System deps for lxml/spacy tokenizers; cleaned up in the same layer.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libxml2 libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml ./
RUN pip install --upgrade pip && pip install -r requirements.txt \
    && python -m spacy download en_core_web_sm

# Pre-cache modern default embedding (nomic, Apache-2.0, CPU-fast) + legacy
# MiniLM fallback + multilingual sentiment so audit-time runs stay offline.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('nomic-ai/nomic-embed-text-v1.5')" \
 && python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')" \
 && python -c "from transformers import AutoTokenizer, AutoModelForSequenceClassification as M; AutoTokenizer.from_pretrained('tabularisai/multilingual-sentiment-analysis'); M.from_pretrained('tabularisai/multilingual-sentiment-analysis')"

COPY ragevda/ ./ragevda/
COPY config.example.yaml README.md ./

# Non-root: least privilege (enterprise requirement). web_output stays writable.
RUN useradd -m -u 10001 ragevda && mkdir -p /app/web_output && chown -R ragevda:ragevda /app
USER ragevda

EXPOSE 9000
VOLUME ["/app/web_output"]
# Bind loopback by default; set RAGEVDA_BIND=0.0.0.0 explicitly to expose.
CMD ["python", "-m", "ragevda.cli", "web", "--host", "127.0.0.1", "--port", "9000"]
