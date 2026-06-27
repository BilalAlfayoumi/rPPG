import cv2
import numpy as np

from backend.config import FRAME_HEIGHT, FRAME_WIDTH


def decode_jpeg_bytes(data: bytes) -> np.ndarray | None:
    """
    Décode des bytes JPEG bruts en image BGR numpy.
    Redimensionne à FRAME_WIDTH×FRAME_HEIGHT si nécessaire.
    Retourne None si les bytes sont invalides.
    """
    buf = np.frombuffer(data, dtype=np.uint8)
    frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if frame is None:
        return None
    if frame.shape[1] != FRAME_WIDTH or frame.shape[0] != FRAME_HEIGHT:
        frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
    return frame
