# RAG-EVDA — zero-cost local AI-search visibility auditor
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

# Pre-cache the default embedding + sentiment models so audit-time runs offline.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')" \
 && python -c "from transformers import AutoTokenizer, AutoModelForSequenceClassification as M; AutoTokenizer.from_pretrained('cardiffnlp/twitter-roberta-base-sentiment-latest'); M.from_pretrained('cardiffnlp/twitter-roberta-base-sentiment-latest')"

COPY ragevda/ ./ragevda/
COPY config.example.yaml README.md ./

EXPOSE 9000
VOLUME ["/app/web_output"]
CMD ["python", "-m", "ragevda.cli", "web", "--host", "0.0.0.0", "--port", "9000"]
