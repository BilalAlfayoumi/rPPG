FROM python:3.11-slim

WORKDIR /app

# Dépendances serveur uniquement (légères : pas d'OpenCV ni dlib).
# L'extraction ROI se fait côté navigateur (MediaPipe JS).
COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY backend/ ./backend/
COPY frontend/ ./frontend/

EXPOSE 8000

# 1 seul worker : état WebSocket en mémoire, pas multi-process safe
CMD ["uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--ws-ping-interval", "20", "--ws-ping-timeout", "60"]
