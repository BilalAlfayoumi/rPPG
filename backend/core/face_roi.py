"""
Détection du visage et extraction de la ROI.

Stratégie principale : landmarks faciaux dlib (68 points) → ROI précise et
stable (front via sourcils, joues via œil/nez/mâchoire). Repli automatique sur
OpenCV Haar Cascade si le modèle dlib est absent.

La moyenne RGB n'est calculée que sur les pixels de PEAU (segmentation YCrCb),
ce qui élimine cheveux, ombres et bords — robuste aux teints.
"""

from pathlib import Path

import cv2
import numpy as np

# Seuils de peau YCrCb (robustes aux variations de teint/éclairage)
_CR_MIN, _CR_MAX = 133, 173
_CB_MIN, _CB_MAX = 77, 127

_BOX_SMOOTH = 0.6  # lissage temporel de la box (repli Haar)

_MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "shape_predictor_68_face_landmarks.dat"
_CASCADE_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"

# Indices de landmarks dlib pour les ROI
_BROWS = list(range(17, 27))          # sourcils (base du front)
_LEFT_CHEEK = [2, 3, 4, 48, 31, 40]   # joue gauche (mâchoire, bouche, nez, sous-œil)
_RIGHT_CHEEK = [14, 13, 12, 54, 35, 47]  # joue droite (symétrique)


def _skin_mean(pixels_bgr: np.ndarray) -> tuple[np.ndarray | None, float]:
    """Moyenne RGB des pixels de peau (filtre YCrCb)."""
    if len(pixels_bgr) == 0:
        return None, 0.0
    ycrcb = cv2.cvtColor(pixels_bgr.reshape(-1, 1, 3), cv2.COLOR_BGR2YCrCb).reshape(-1, 3)
    cr, cb = ycrcb[:, 1], ycrcb[:, 2]
    skin = (cr >= _CR_MIN) & (cr <= _CR_MAX) & (cb >= _CB_MIN) & (cb <= _CB_MAX)
    skin_pixels = pixels_bgr[skin]
    if len(skin_pixels) < 20:
        return None, 0.0
    conf = float(len(skin_pixels)) / max(len(pixels_bgr), 1)
    rgb_mean = np.mean(skin_pixels[:, ::-1].astype(np.float32), axis=0)  # BGR → RGB
    return rgb_mean, conf


class FaceROI:
    def __init__(self):
        self._use_dlib = _MODEL_PATH.is_file()
        if self._use_dlib:
            import dlib

            self._detector = dlib.get_frontal_face_detector()
            self._predictor = dlib.shape_predictor(str(_MODEL_PATH))
        else:
            self._detector = cv2.CascadeClassifier(_CASCADE_PATH)
            if self._detector.empty():
                raise RuntimeError(f"Cascade introuvable : {_CASCADE_PATH}")
        self._prev_box: np.ndarray | None = None

    # ── Méthode dlib (landmarks) ────────────────────────────────────────────

    def _extract_dlib(self, frame_bgr: np.ndarray):
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        faces = self._detector(gray, 0)
        if not faces:
            return None, 0.0

        face = max(faces, key=lambda r: r.width() * r.height())
        shape = self._predictor(gray, face)
        pts = np.array([[shape.part(i).x, shape.part(i).y] for i in range(68)], dtype=np.int32)

        # Front : sourcils remontés de ~30 % de la hauteur du visage
        offset = int(0.30 * face.height())
        brows = pts[_BROWS]
        top = brows.copy()
        top[:, 1] -= offset
        forehead = np.vstack([brows, top[::-1]])

        mask = np.zeros(gray.shape, np.uint8)
        for poly in (forehead, pts[_LEFT_CHEEK], pts[_RIGHT_CHEEK]):
            cv2.fillConvexPoly(mask, cv2.convexHull(poly), 255)

        return _skin_mean(frame_bgr[mask == 255])

    # ── Repli Haar Cascade ──────────────────────────────────────────────────

    def _extract_haar(self, frame_bgr: np.ndarray):
        h0, w0 = frame_bgr.shape[:2]
        enlarged = cv2.resize(frame_bgr, (w0 * 2, h0 * 2), interpolation=cv2.INTER_LINEAR)
        gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
        cv2.equalizeHist(gray, gray)
        faces = self._detector.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=3, minSize=(40, 40),
            flags=cv2.CASCADE_SCALE_IMAGE,
        )
        if len(faces) == 0:
            return None, 0.0
        box = np.array(max(faces, key=lambda f: f[2] * f[3]), dtype=np.float32) / 2.0
        if self._prev_box is not None:
            box = _BOX_SMOOTH * self._prev_box + (1 - _BOX_SMOOTH) * box
        self._prev_box = box
        x, y, w, h = box.astype(int)

        patches = [
            frame_bgr[y + int(0.05 * h):y + int(0.30 * h), x + int(0.30 * w):x + int(0.70 * w)],
            frame_bgr[y + int(0.35 * h):y + int(0.60 * h), x + int(0.05 * w):x + int(0.25 * w)],
            frame_bgr[y + int(0.35 * h):y + int(0.60 * h), x + int(0.75 * w):x + int(0.95 * w)],
        ]
        patches = [p for p in patches if p.size > 0]
        if not patches:
            return None, 0.0
        return _skin_mean(np.concatenate([p.reshape(-1, 3) for p in patches], axis=0))

    # ── API publique ────────────────────────────────────────────────────────

    def extract_roi_rgb(self, frame_bgr: np.ndarray) -> tuple[np.ndarray | None, float]:
        """Retourne (rgb_mean shape (3,), confidence) ou (None, 0.0)."""
        if self._use_dlib:
            return self._extract_dlib(frame_bgr)
        return self._extract_haar(frame_bgr)

    def close(self):
        pass
