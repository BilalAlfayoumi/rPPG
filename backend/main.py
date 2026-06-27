import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.routers import ws_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("rPPG server démarré")
    yield
    logger.info("rPPG server arrêté")


app = FastAPI(title="rPPG Heart Rate Monitor", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="frontend"), name="static")
app.include_router(ws_router.router)


@app.get("/")
async def serve_index():
    return FileResponse("frontend/index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}
