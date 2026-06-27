import numpy as np
from scipy.signal import welch


def compute_snr(bvp: np.ndarray, fps: float, min_hz: float = 0.65, max_hz: float = 4.0) -> float:
    """SNR = puissance dans la bande cardiaque / puissance totale."""
    freqs, psd = welch(bvp, fs=fps, nperseg=min(len(bvp), 256))
    band_mask = (freqs >= min_hz) & (freqs <= max_hz)
    total_power = np.sum(psd)
    if total_power == 0:
        return 0.0
    return float(np.sum(psd[band_mask]) / total_power)


def bpm_is_valid(bpm: float) -> bool:
    return 40.0 <= bpm <= 200.0
