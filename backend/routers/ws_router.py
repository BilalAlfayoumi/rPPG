import asyncio
import logging
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.core.session import SessionManager

logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                    format="%(levelname)s  %(name)s: %(message)s")
logger = logging.getLogger(__name__)

router = APIRouter()
_session_manager = SessionManager()
_executor = ThreadPoolExecutor(max_workers=4)


@router.websocket("/ws/rppg")
async def rppg_websocket(websocket: WebSocket):
    """
    Reçoit les moyennes RGB de la peau (extraites côté navigateur via MediaPipe),
    applique le pipeline rPPG (POS/CHROM → filtre → FFT) et renvoie le BPM.
    """
    await websocket.accept()
    session = _session_manager.create()
    loop = asyncio.get_event_loop()
    logger.info(f"Session ouverte : {session.session_id} — {_session_manager.count()} connecté(s)")

    try:
        async for msg in websocket.iter_json():
            if msg.get("type") != "rgb" or "rgb" not in msg:
                continue

            rgb = np.asarray(msg["rgb"], dtype=np.float32)
            if rgb.shape != (3,):
                continue

            should_compute = session.signal_processor.add_rgb_sample(rgb)

            if should_compute and not session.processing_lock.locked():
                async with session.processing_lock:
                    bpm, snr, tail = await loop.run_in_executor(
                        _executor, session.signal_processor.compute_bpm
                    )
                    session.last_bpm = bpm
                    session.last_snr = snr
                    session.last_bvp_tail = tail

            fill = session.signal_processor.buffer_fill
            if session.last_bpm is None:
                await websocket.send_json({"type": "collecting", "bpm": None,
                                           "buffer_fill": round(fill, 2)})
            else:
                await websocket.send_json({
                    "type": "bpm_update",
                    "bpm": round(session.last_bpm, 1),
                    "confidence": round(session.last_snr, 2),
                    "buffer_fill": round(fill, 2),
                    "bvp_signal": session.last_bvp_tail,
                })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Erreur session {session.session_id} : {e}")
    finally:
        _session_manager.destroy(session.session_id)
        logger.info(f"Session fermée : {session.session_id} — {_session_manager.count()} connecté(s)")
