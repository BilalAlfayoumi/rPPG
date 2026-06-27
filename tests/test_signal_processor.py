import numpy as np
import pytest

from backend.core.signal_processor import SignalProcessor


def _feed_synthetic(processor: SignalProcessor, bpm: float, fps: float = 10.0, duration: float = 10.0):
    """Injecte un signal RGB synthétique à une fréquence cardiaque donnée."""
    n = int(fps * duration)
    t = np.linspace(0, duration, n)
    f = bpm / 60.0
    pulse = np.sin(2 * np.pi * f * t)
    rng = np.random.default_rng(0)
    noise = 0.02
    for i in range(n):
        rgb = np.array([
            80.0  + 0.5 * pulse[i] + noise * rng.standard_normal(),
            100.0 + 2.0 * pulse[i] + noise * rng.standard_normal(),
            60.0  + 0.8 * pulse[i] + noise * rng.standard_normal(),
        ], dtype=np.float32)
        processor.add_rgb_sample(rgb)


def test_buffer_fill():
    proc = SignalProcessor(fps=10.0)
    assert proc.buffer_fill == 0.0
    _feed_synthetic(proc, bpm=72.0, duration=5.0)
    assert proc.buffer_fill == pytest.approx(0.5, abs=0.05)


def test_compute_bpm_returns_valid_result():
    """Pipeline complet sur signal synthétique 72 BPM — doit retourner un BPM plausible."""
    proc = SignalProcessor(fps=10.0)
    _feed_synthetic(proc, bpm=72.0, duration=10.0)

    bpm, snr, tail = proc.compute_bpm()

    assert bpm is not None, "BPM None sur signal synthétique propre"
    assert 40.0 <= bpm <= 200.0, f"BPM hors plage physiologique : {bpm}"
    assert 0.0 <= snr <= 1.0, f"SNR hors [0,1] : {snr}"
    assert len(tail) <= 64


def test_compute_bpm_accuracy():
    """Le BPM estimé doit être à ±15 BPM de la valeur cible sur signal propre."""
    proc = SignalProcessor(fps=10.0)
    target_bpm = 75.0
    _feed_synthetic(proc, bpm=target_bpm, duration=10.0)

    bpm, _, _ = proc.compute_bpm()

    assert bpm is not None
    assert abs(bpm - target_bpm) < 15.0, f"BPM estimé ({bpm:.1f}) trop éloigné de {target_bpm}"


def test_add_rgb_triggers_compute():
    """add_rgb_sample doit retourner True quand le seuil de recalcul est atteint."""
    from backend.config import MIN_FRAMES_FOR_BPM, BPM_REFRESH_FRAMES

    proc = SignalProcessor(fps=10.0)
    rgb = np.array([100.0, 120.0, 80.0], dtype=np.float32)

    triggered = False
    for i in range(MIN_FRAMES_FOR_BPM + BPM_REFRESH_FRAMES):
        result = proc.add_rgb_sample(rgb)
        if result:
            triggered = True
            break

    assert triggered, "add_rgb_sample n'a jamais retourné True"
