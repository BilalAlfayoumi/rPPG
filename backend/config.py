TARGET_FPS = 10
BUFFER_SECONDS = 10
BUFFER_SIZE = TARGET_FPS * BUFFER_SECONDS  # 100 frames

BPM_REFRESH_FRAMES = 15   # recalcul toutes les ~1.5s
MIN_FRAMES_FOR_BPM = 50   # ~5s de buffer minimum avant premier calcul

MIN_HZ = 0.65             # 39 BPM
MAX_HZ = 4.0              # 240 BPM
BUTTERWORTH_ORDER = 6

# Méthode rPPG : "POS" (Wang 2017, plus robuste) ou "CHROM" (de Haan 2013)
RPPG_METHOD = "POS"
NFFT = 2048               # zero-padding FFT pour densité fréquentielle fine
BPM_HISTORY_SIZE = 7      # nombre de BPM lissés par médiane (rejette les sauts harmoniques)
MIN_SNR_FOR_UPDATE = 0.15 # SNR minimum pour intégrer un BPM dans l'historique

FRAME_WIDTH = 320
FRAME_HEIGHT = 240
JPEG_QUALITY = 0.6        # qualité blob client→serveur
