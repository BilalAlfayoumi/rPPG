import asyncio
import uuid

from backend.core.face_roi import FaceROI
from backend.core.signal_processor import SignalProcessor
from backend.config import TARGET_FPS


class WebSocketSession:
    """État complet d'un client WebSocket connecté."""

    def __init__(self):
        self.session_id: str = str(uuid.uuid4())
        self.signal_processor: SignalProcessor = SignalProcessor(fps=TARGET_FPS)
        self.face_detector: FaceROI = FaceROI()  # 1 instance par session (non thread-safe partagée)
        self.last_bpm: float | None = None
        self.last_snr: float = 0.0
        self.last_bvp_tail: list[float] = []
        self.processing_lock: asyncio.Lock = asyncio.Lock()

    def close(self):
        self.face_detector.close()


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, WebSocketSession] = {}

    def create(self) -> WebSocketSession:
        session = WebSocketSession()
        self._sessions[session.session_id] = session
        return session

    def destroy(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session:
            session.close()

    def count(self) -> int:
        return len(self._sessions)
