"""
Pipeline rPPG : buffer RGB glissant → POS/CHROM → filtrage → FFT → BPM.

Algorithmes implémentés d'après les papiers originaux :
- CHROM : de Haan & Jeanne (2013), IEEE Trans. Biomed. Eng. 60(10)
- POS   : Wang, den Brinker, Stuijk & de Haan (2017), IEEE Trans. Biomed. Eng. 64(7)

Robustesse (anti-sauts harmoniques 1/2× et 2×) :
- detrending linéaire avant projection
- fenêtre de Hann + FFT zero-paddée + interpolation parabolique du pic
- lissage temporel par médiane glissante des derniers BPM
"""

from collections import deque

import numpy as np
from scipy.signal import butter, detrend, filtfilt

from backend.config import (
    BPM_HISTORY_SIZE,
    BPM_REFRESH_FRAMES,
    BUFFER_SIZE,
    BUTTERWORTH_ORDER,
    MIN_FRAMES_FOR_BPM,
    MIN_HZ,
    MAX_HZ,
    MIN_SNR_FOR_UPDATE,
    NFFT,
    RPPG_METHOD,
    TARGET_FPS,
)
from backend.core.bpm_estimator import bpm_is_valid, compute_snr


def _chrom(sig: np.ndarray) -> np.ndarray:
    """
    CHROM — de Haan & Jeanne 2013.
    sig : (N, 3) — colonnes R, G, B. Retourne bvp (N,).
    """
    r, g, b = sig[:, 0], sig[:, 1], sig[:, 2]
    r_n = r / (np.mean(r) + 1e-9)
    g_n = g / (np.mean(g) + 1e-9)
    b_n = b / (np.mean(b) + 1e-9)

    xs = 3 * r_n - 2 * g_n
    ys = 1.5 * r_n + g_n - 1.5 * b_n

    alpha = np.std(xs) / (np.std(ys) + 1e-9)
    return xs - alpha * ys


def _pos(sig: np.ndarray) -> np.ndarray:
    """
    POS (Plane-Orthogonal-to-Skin) — Wang et al. 2017.
    sig : (N, 3) — colonnes R, G, B. Retourne bvp (N,).

    Projection sur le plan orthogonal au ton de peau :
      S1 = G - B
      S2 = G + B - 2R
      h  = S1 + (std(S1)/std(S2)) * S2
    """
    c = sig.T  # (3, N)
    mean = np.mean(c, axis=1, keepdims=True)
    cn = c / (mean + 1e-9)  # normalisation temporelle par canal

    s1 = cn[1] - cn[2]                 # G - B
    s2 = cn[1] + cn[2] - 2 * cn[0]     # G + B - 2R

    alpha = np.std(s1) / (np.std(s2) + 1e-9)
    h = s1 + alpha * s2
    return h - np.mean(h)


def _project(sig: np.ndarray, method: str = RPPG_METHOD) -> np.ndarray:
    """Applique detrending puis la méthode rPPG demandée."""
    sig = detrend(sig, axis=0)  # retire la dérive lente (lumière)
    if method == "CHROM":
        return _chrom(sig)
    return _pos(sig)


def _bandpass(signal: np.ndarray, fps: float, min_hz: float, max_hz: float, order: int) -> np.ndarray:
    nyq = fps / 2.0
    low = min_hz / nyq
    high = min(max_hz / nyq, 0.99)
    b, a = butter(order // 2, [low, high], btype="bandpass")
    return filtfilt(b, a, signal)


def _bpm_from_bvp(bvp: np.ndarray, fps: float, min_hz: float, max_hz: float) -> float:
    """
    Fréquence dominante par FFT zero-paddée + fenêtre de Hann
    + interpolation parabolique du pic (précision sous la résolution FFT).
    """
    n = len(bvp)
    windowed = bvp * np.hanning(n)
    spectrum = np.abs(np.fft.rfft(windowed, n=NFFT))
    freqs = np.fft.rfftfreq(NFFT, d=1.0 / fps)

    band_idx = np.where((freqs >= min_hz) & (freqs <= max_hz))[0]
    if len(band_idx) == 0:
        return 0.0

    peak = band_idx[np.argmax(spectrum[band_idx])]

    # Interpolation parabolique sur les 3 points autour du pic
    if 0 < peak < len(spectrum) - 1:
        y0, y1, y2 = spectrum[peak - 1], spectrum[peak], spectrum[peak + 1]
        denom = y0 - 2 * y1 + y2
        offset = 0.5 * (y0 - y2) / denom if abs(denom) > 1e-9 else 0.0
        peak_freq = freqs[peak] + offset * (freqs[1] - freqs[0])
    else:
        peak_freq = freqs[peak]

    return peak_freq * 60.0


class SignalProcessor:
    def __init__(self, fps: float = TARGET_FPS, method: str = RPPG_METHOD):
        self.fps = fps
        self.method = method
        self.rgb_buffer: deque[np.ndarray] = deque(maxlen=BUFFER_SIZE)
        self._bpm_history: deque[float] = deque(maxlen=BPM_HISTORY_SIZE)
        self._frames_since_last_bpm: int = 0

    def add_rgb_sample(self, rgb: np.ndarray) -> bool:
        """Ajoute un échantillon RGB (3,). Retourne True si un calcul BPM doit être déclenché."""
        self.rgb_buffer.append(rgb.astype(np.float32))
        self._frames_since_last_bpm += 1
        return (
            len(self.rgb_buffer) >= MIN_FRAMES_FOR_BPM
            and self._frames_since_last_bpm >= BPM_REFRESH_FRAMES
        )

    def compute_bpm(self) -> tuple[float | None, float, list[float]]:
        """
        Pipeline complet BLOQUANT — appeler via run_in_executor.
        Retourne (bpm_lissé | None, snr_confidence, bvp_tail_64pts).
        """
        self._frames_since_last_bpm = 0
        sig = np.array(list(self.rgb_buffer), dtype=np.float32)  # (N, 3)

        bvp = _project(sig, self.method)
        bvp_filtered = _bandpass(bvp, self.fps, MIN_HZ, MAX_HZ, BUTTERWORTH_ORDER)

        raw_bpm = _bpm_from_bvp(bvp_filtered, self.fps, MIN_HZ, MAX_HZ)
        snr = compute_snr(bvp_filtered, self.fps, MIN_HZ, MAX_HZ)
        tail = bvp_filtered[-64:].tolist()

        # N'intègre dans l'historique que les BPM plausibles et de qualité suffisante
        if bpm_is_valid(raw_bpm) and snr >= MIN_SNR_FOR_UPDATE:
            self._bpm_history.append(raw_bpm)

        if not self._bpm_history:
            return None, snr, tail

        # Médiane glissante : rejette les sauts harmoniques isolés (44, 150…)
        smoothed = float(np.median(self._bpm_history))
        return smoothed, snr, tail

    @property
    def buffer_fill(self) -> float:
        return len(self.rgb_buffer) / BUFFER_SIZE
