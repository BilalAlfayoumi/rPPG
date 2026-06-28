import asyncio
import uuid

from backend.core.signal_processor import SignalProcessor
from backend.config import TARGET_FPS


class WebSocketSession:
    """État complet d'un client WebSocket connecté (un buffer rPPG par connexion)."""

    def __init__(self):
        self.session_id: str = str(uuid.uuid4())
        self.signal_processor: SignalProcessor = SignalProcessor(fps=TARGET_FPS)
        self.last_bpm: float | None = None
        self.last_snr: float = 0.0
        self.last_bvp_tail: list[float] = []
        self.processing_lock: asyncio.Lock = asyncio.Lock()


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, WebSocketSession] = {}

    def create(self) -> WebSocketSession:
        session = WebSocketSession()
        self._sessions[session.session_id] = session
        return session

    def destroy(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def count(self) -> int:
        return len(self._sessions)
