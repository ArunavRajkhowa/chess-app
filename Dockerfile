# One image: native Stockfish, the Python backend, the built frontend. About 490 MB.
# dist is the same on every architecture: build it once, natively, not under emulation.
FROM --platform=$BUILDPLATFORM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN node scripts/copy-engine.mjs && npm run build

FROM python:3.12-slim
# A host (Render, SnapDeploy) puts HTTPS in front: trust its X-Forwarded-* headers.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 STOCKFISH_PATH=/usr/games/stockfish HOST=0.0.0.0 PORT=8765 FORWARDED_ALLOW_IPS=*
RUN apt-get update && apt-get install -y --no-install-recommends stockfish && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY backend backend
COPY data data
COPY --from=frontend /app/frontend/dist frontend/dist
EXPOSE 8765
# sh reads the host's PORT (Render sets it) at start; exec hands uvicorn the stop signal.
CMD ["sh", "-c", "exec python -m uvicorn backend.app:app --host 0.0.0.0 --port \"$PORT\""]
