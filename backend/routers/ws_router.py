import asyncio
import logging
import sys
from concurrent.futures import ThreadPoolExecutor

# Afficher les logs de l'app dans la console uvicorn
logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                    format="%(levelname)s  %(name)s: %(message)s")

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.core.session import SessionManager
from backend.utils.frame_decoder import decode_jpeg_bytes

logger = logging.getLogger(__name__)

router = APIRouter()
_session_manager = SessionManager()
_executor = ThreadPoolExecutor(max_workers=4)


@router.websocket("/ws/rppg")
async def rppg_websocket(websocket: WebSocket):
    await websocket.accept()
    session = _session_manager.create()
    loop = asyncio.get_event_loop()
    logger.info(f"Session ouverte : {session.session_id} — {_session_manager.count()} connecté(s)")

    try:
        async for message in websocket.iter_bytes():
            # 1. Décodage JPEG dans le thread pool (bloquant)
            frame = await loop.run_in_executor(_executor, decode_jpeg_bytes, message)

            if frame is None:
                await websocket.send_json({"type": "error", "message": "frame invalide"})
                continue

            # 2. Extraction ROI (landmarks dlib) dans le thread pool (bloquant)
            rgb_mean, _ = await loop.run_in_executor(
                _executor, session.face_detector.extract_roi_rgb, frame
            )

            if rgb_mean is None:
                await websocket.send_json({
                    "type": "no_face",
                    "bpm": None,
                    "buffer_fill": round(session.signal_processor.buffer_fill, 2),
                })
                continue

            # 3. Ajouter l'échantillon au buffer glissant
            should_compute = session.signal_processor.add_rgb_sample(rgb_mean)

            # 4. Recalcul BPM si le seuil est atteint (avec lock pour éviter chevauchement)
            if should_compute and not session.processing_lock.locked():
                async with session.processing_lock:
                    bpm, snr, tail = await loop.run_in_executor(
                        _executor, session.signal_processor.compute_bpm
                    )
                    session.last_bpm = bpm
                    session.last_snr = snr
                    session.last_bvp_tail = tail

            # 5. Réponse au client
            fill = session.signal_processor.buffer_fill

            if session.last_bpm is None:
                await websocket.send_json({
                    "type": "collecting",
                    "bpm": None,
                    "buffer_fill": round(fill, 2),
                })
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
