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

# NOTE: requirements.txt builds the project itself (`-e .` via hatchling),
# so the build metadata (pyproject.toml + README.md) AND the package source
# must be present BEFORE `pip install` runs. Copying them in a later layer
# fails with "OSError: Readme file does not exist: README.md".
COPY requirements.txt pyproject.toml README.md ./
COPY ragevda/ ./ragevda/
RUN pip install --upgrade pip && pip install -r requirements.txt \
    && python -m spacy download en_core_web_sm

# Pre-cache modern default embedding (nomic, Apache-2.0, CPU-fast) + legacy
# MiniLM fallback + multilingual sentiment so audit-time runs stay offline.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('nomic-ai/nomic-embed-text-v1.5')" \
 && python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')" \
 && python -c "from transformers import AutoTokenizer, AutoModelForSequenceClassification as M; AutoTokenizer.from_pretrained('tabularisai/multilingual-sentiment-analysis'); M.from_pretrained('tabularisai/multilingual-sentiment-analysis')"

COPY config.example.yaml ./

# Non-root: least privilege (enterprise requirement). web_output stays writable.
RUN useradd -m -u 10001 ragevda && mkdir -p /app/web_output && chown -R ragevda:ragevda /app
USER ragevda

EXPOSE 9000
VOLUME ["/app/web_output"]
# Render/Heroku-style platforms inject $PORT and require 0.0.0.0; local docker
# stays loopback-only unless RAGEVDA_BIND is set explicitly.
CMD ["sh", "-c", "if [ -n \"$PORT\" ]; then HOST=0.0.0.0; else HOST=${RAGEVDA_BIND:-127.0.0.1}; fi; python -m ragevda.cli web --host \"$HOST\" --port \"${PORT:-9000}\""]
