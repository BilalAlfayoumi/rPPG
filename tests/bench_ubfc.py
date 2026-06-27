"""
Benchmark de précision du pipeline rPPG sur le dataset UBFC-rPPG.

Mesure MAE, RMSE et corrélation de Pearson entre le BPM estimé et la
vérité terrain (oxymètre de contact), et compare CHROM vs POS.

─────────────────────────────────────────────────────────────────────────────
OBTENIR LE DATASET (UBFC-rPPG, "DATASET_2")
  Demande d'accès : https://sites.google.com/view/ybenezeth/ubfcrppg
  Arborescence attendue :
    data/UBFC/
      subject1/
        vid.avi
        ground_truth.txt   # 3 lignes : [0]=PPG  [1]=HR(BPM)  [2]=timestamps(s)
      subject3/
        ...

UTILISATION
  make bench                      # benchmark complet sur data/UBFC
  uv run python tests/bench_ubfc.py --data data/UBFC
  uv run python tests/bench_ubfc.py --self-test   # valide la mécanique sans dataset
─────────────────────────────────────────────────────────────────────────────
"""

import argparse
import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import TARGET_FPS  # noqa: E402
from backend.core.signal_processor import SignalProcessor  # noqa: E402

# Le benchmark teste EXACTEMENT le pipeline déployé : on sous-échantillonne
# les vidéos UBFC (30 fps) au débit réel de l'app (TARGET_FPS, ~10 fps), puis
# on rejoue le flux dans SignalProcessor (avec son lissage médiane + gating SNR).


def estimate_bpm_series(rgb: np.ndarray, fps: float, method: str):
    """
    Rejoue le flux RGB dans SignalProcessor comme en temps réel.
    Retourne (temps_centres, bpms_lissés).
    """
    sp = SignalProcessor(fps=fps, method=method)
    centers, bpms = [], []
    for i, sample in enumerate(rgb):
        if sp.add_rgb_sample(sample):
            bpm, _, _ = sp.compute_bpm()
            if bpm is not None:
                centers.append(i / fps)
                bpms.append(bpm)
    return np.array(centers), np.array(bpms)


def metrics(est: np.ndarray, gt: np.ndarray):
    """
    MAE, RMSE, Pearson r sur les points valides.
    Les points où la vérité terrain est non physiologique (HR hors [40, 200])
    sont écartés : certaines vidéos UBFC ont des segments d'oxymètre corrompus
    (ex. subject11 descend à 1 BPM), qu'on ne peut pas évaluer.
    """
    mask = (est > 0) & np.isfinite(est) & np.isfinite(gt) & (gt >= 40) & (gt <= 200)
    est, gt = est[mask], gt[mask]
    if len(est) < 2:
        return float("nan"), float("nan"), float("nan")
    mae = float(np.mean(np.abs(est - gt)))
    rmse = float(np.sqrt(np.mean((est - gt) ** 2)))
    r = float(np.corrcoef(est, gt)[0, 1])
    return mae, rmse, r


# ── Lecture du dataset UBFC ─────────────────────────────────────────────────

def extract_rgb_from_video(video_path: str, fps: float) -> np.ndarray:
    """Lit la vidéo, sous-échantillonne à `fps`, extrait le RGB moyen de la ROI."""
    import cv2

    from backend.core.face_roi import FaceROI

    face = FaceROI()
    cap = cv2.VideoCapture(video_path)
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(src_fps / fps))

    rgb, idx, last = [], 0, None
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if idx % step == 0:
            mean, _ = face.extract_roi_rgb(frame)
            if mean is None:
                mean = last if last is not None else np.array([128, 128, 128], np.float32)
            last = mean
            rgb.append(mean)
        idx += 1
    cap.release()
    return np.array(rgb, dtype=np.float32)


def load_ground_truth(gt_path: str):
    """UBFC DATASET_2 : ligne 1 = HR (BPM), ligne 2 = timestamps (s)."""
    data = np.loadtxt(gt_path)
    return data[2], data[1]  # (times, hr)


def run_dataset(data_dir: str, methods: list[str]):
    subjects = sorted(glob.glob(os.path.join(data_dir, "*")))
    subjects = [s for s in subjects if os.path.isfile(os.path.join(s, "vid.avi"))]

    if not subjects:
        print(f"Aucun sujet trouvé dans {data_dir} (cherche */vid.avi).")
        print("Voir les instructions de téléchargement en tête de ce fichier.")
        return

    print(f"{len(subjects)} sujet(s) trouvé(s).\n")
    results = {m: {"mae": [], "rmse": [], "r": []} for m in methods}

    for subj in subjects:
        name = os.path.basename(subj)
        rgb = extract_rgb_from_video(os.path.join(subj, "vid.avi"), TARGET_FPS)
        t_gt, hr_gt = load_ground_truth(os.path.join(subj, "ground_truth.txt"))

        line = f"  {name:<12}"
        for m in methods:
            centers, bpms = estimate_bpm_series(rgb, TARGET_FPS, m)
            hr_aligned = np.interp(centers, t_gt, hr_gt)
            mae, rmse, r = metrics(bpms, hr_aligned)
            results[m]["mae"].append(mae)
            results[m]["rmse"].append(rmse)
            results[m]["r"].append(r)
            line += f"   {m}: MAE={mae:5.1f} RMSE={rmse:5.1f} r={r:+.2f}"
        print(line)

    print("\n" + "=" * 60)
    print("MOYENNE GLOBALE")
    for m in methods:
        mae = np.nanmean(results[m]["mae"])
        rmse = np.nanmean(results[m]["rmse"])
        r = np.nanmean(results[m]["r"])
        print(f"  {m:<6}  MAE = {mae:.2f} BPM   RMSE = {rmse:.2f} BPM   r = {r:+.3f}")


# ── Self-test (sans dataset) ────────────────────────────────────────────────

def synthetic_rgb(hr_trace: np.ndarray, fps: float, noise: float = 0.3) -> np.ndarray:
    """Génère une série RGB dont le pouls suit une HR variable (BPM)."""
    n = len(hr_trace)
    rng = np.random.default_rng(0)
    phase = np.cumsum(2 * np.pi * hr_trace / 60.0 / fps)
    pulse = np.sin(phase)
    drift = 3 * np.sin(2 * np.pi * 0.05 * np.arange(n) / fps)  # dérive lumineuse lente
    r = 80 + 0.5 * pulse + drift + noise * rng.standard_normal(n)
    g = 100 + 2.0 * pulse + drift + noise * rng.standard_normal(n)
    b = 60 + 0.8 * pulse + drift + noise * rng.standard_normal(n)
    return np.stack([r, g, b], axis=1).astype(np.float32)


def run_self_test():
    print("Self-test (signal synthétique, sans dataset)\n")
    fps = TARGET_FPS
    duration = 40
    n = int(fps * duration)
    # HR qui monte de 60 à 96 BPM puis redescend
    t = np.linspace(0, 1, n)
    hr_trace = 60 + 30 * np.sin(np.pi * t) ** 2

    rgb = synthetic_rgb(hr_trace, fps)
    times_gt = np.arange(n) / fps

    for m in ["CHROM", "POS"]:
        centers, bpms = estimate_bpm_series(rgb, fps, m)
        hr_aligned = np.interp(centers, times_gt, hr_trace)
        mae, rmse, r = metrics(bpms, hr_aligned)
        print(f"  {m:<6}  MAE = {mae:.2f} BPM   RMSE = {rmse:.2f} BPM   r = {r:+.3f}")

    print("\nLa mécanique du benchmark fonctionne. Branche le dataset UBFC pour")
    print("des métriques réelles (--data data/UBFC).")


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Benchmark rPPG sur UBFC")
    parser.add_argument("--data", default="data/UBFC", help="dossier du dataset UBFC")
    parser.add_argument("--self-test", action="store_true", help="valide sans dataset")
    parser.add_argument(
        "--methods", default="CHROM,POS", help="méthodes à comparer (CHROM,POS)"
    )
    args = parser.parse_args()

    methods = [m.strip().upper() for m in args.methods.split(",")]

    if args.self_test or not os.path.isdir(args.data):
        if not args.self_test:
            print(f"Dataset introuvable ({args.data}) — bascule en self-test.\n")
        run_self_test()
    else:
        run_dataset(args.data, methods)


if __name__ == "__main__":
    main()
