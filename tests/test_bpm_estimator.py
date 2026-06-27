import numpy as np
import pytest

from backend.core.bpm_estimator import compute_snr, bpm_is_valid


def _synthetic_rgb(bpm: float, fps: float = 10.0, duration: float = 10.0, noise: float = 0.02) -> np.ndarray:
    """Génère un signal RGB synthétique avec une fréquence cardiaque connue."""
    n = int(fps * duration)
    t = np.linspace(0, duration, n)
    f = bpm / 60.0
    pulse = np.sin(2 * np.pi * f * t)
    rng = np.random.default_rng(42)
    r = 80.0  + 0.5 * pulse + noise * rng.standard_normal(n)
    g = 100.0 + 2.0 * pulse + noise * rng.standard_normal(n)
    b = 60.0  + 0.8 * pulse + noise * rng.standard_normal(n)
    return np.stack([r, g, b], axis=1)  # (N, 3)


def test_snr_pure_sine():
    """Un sinus pur dans la bande cardiaque doit avoir un SNR élevé."""
    fps = 10.0
    n = int(fps * 10)
    t = np.linspace(0, 10, n)
    bvp = np.sin(2 * np.pi * 1.2 * t)  # 72 BPM
    snr = compute_snr(bvp, fps=fps)
    assert snr > 0.5, f"SNR trop bas sur sinus pur : {snr:.3f}"


def test_snr_sine_higher_than_noise():
    """Un sinus pur doit avoir un SNR significativement plus élevé que du bruit blanc."""
    fps = 10.0
    n = 100
    t = np.linspace(0, n / fps, n)
    sine_bvp = np.sin(2 * np.pi * 1.2 * t)
    rng = np.random.default_rng(0)
    noise_bvp = rng.standard_normal(n)
    snr_sine = compute_snr(sine_bvp, fps=fps)
    snr_noise = compute_snr(noise_bvp, fps=fps)
    assert snr_sine > snr_noise + 0.2, (
        f"SNR sinus ({snr_sine:.3f}) pas assez supérieur au bruit ({snr_noise:.3f})"
    )


@pytest.mark.parametrize("bpm", [40.0, 72.0, 120.0, 200.0])
def test_bpm_valid_range(bpm):
    assert bpm_is_valid(bpm)


@pytest.mark.parametrize("bpm", [39.9, 200.1, 0.0, -10.0, 300.0])
def test_bpm_invalid_range(bpm):
    assert not bpm_is_valid(bpm)
