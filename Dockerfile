# J.A.R.V.I.S. Cloud Brain — Railway/Docker deployment
# Builds ONLY the backend (FastAPI + MongoDB + Emergent LLM).
# Frontend deploy separately (Vercel/Netlify/Railway static site).

FROM python:3.11-slim

# Install system deps (needed by some Python wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for better layer caching
COPY backend/requirements.txt ./requirements.txt

# Install Python deps.
# emergentintegrations is on a private CloudFront index (public HTTPS, no auth).
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ \
        -r requirements.txt

# Copy backend code
COPY backend/ /app/

# Railway/Heroku pattern: use the PORT env var if provided
ENV PORT=8001
EXPOSE 8001

# Healthcheck against our own /api/ endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-8001}/api/" || exit 1

# Uvicorn honors $PORT via shell expansion
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8001}"]
