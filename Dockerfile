# ── Build stage : compile dlib (nécessite cmake + build-essential) ───────────
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml .

# Installe les dépendances (dlib compile ici, ~8 min) dans un venv isolé
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir .

# ── Runtime stage : image légère sans outils de compilation ──────────────────
FROM python:3.11-slim

# Dépendances système runtime (OpenCV headless + libs dlib)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libgomp1 \
    curl bzip2 \
    && rm -rf /var/lib/apt/lists/*

# Récupère le venv compilé (avec dlib) depuis le builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Télécharge le modèle de landmarks dlib (95 Mo) au build
RUN mkdir -p models && \
    curl -sL "https://github.com/davisking/dlib-models/raw/master/shape_predictor_68_face_landmarks.dat.bz2" \
      -o models/m.dat.bz2 && \
    bunzip2 models/m.dat.bz2 && \
    mv models/m.dat models/shape_predictor_68_face_landmarks.dat

COPY backend/ ./backend/
COPY frontend/ ./frontend/

EXPOSE 8000

# 1 seul worker : état WebSocket en mémoire, pas multi-process safe
CMD ["uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--ws-ping-interval", "20", "--ws-ping-timeout", "60"]
