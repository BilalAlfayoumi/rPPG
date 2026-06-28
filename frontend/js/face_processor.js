/**
 * Traitement facial 100% navigateur via MediaPipe FaceLandmarker (WASM).
 *
 * Une seule boucle qui, sur chaque frame vidéo :
 *   1. détecte les 468 landmarks,
 *   2. dessine le maillage (overlay visuel),
 *   3. extrait la moyenne RGB de la peau (front + 2 joues),
 *   4. appelle onRgb([r,g,b]) — ou onRgb(null) si pas de visage.
 *
 * Le serveur ne reçoit donc que 3 valeurs RGB par frame (pas d'image) :
 * détection robuste (MediaPipe marche partout), bande passante minime,
 * backend léger (plus de dlib).
 */
import {
  FaceLandmarker,
  FilesetResolver,
  DrawingUtils,
} from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";

const WASM_PATH =
  "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm";
const MODEL_PATH =
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";

// Indices de landmarks MediaPipe Face Mesh utilisés pour la ROI
const FRONT_TOP = 10;   // haut du front (centre)
const FRONT_MID = 151;  // bas du front / glabelle
const CHEEK_L = 50;     // joue gauche
const CHEEK_R = 280;    // joue droite
const FACE_L = 234;     // bord gauche du visage
const FACE_R = 454;     // bord droit du visage

// Espace d'échantillonnage RGB (taille fixe, indépendante de l'affichage)
const SAMPLE_W = 320;
const SAMPLE_H = 240;

export class FaceProcessor {
  constructor(videoEl, overlayCanvas) {
    this.video = videoEl;
    this.overlay = overlayCanvas;
    this.octx = overlayCanvas.getContext("2d");

    // canvas offscreen pour lire les pixels (RGB)
    this._sample = document.createElement("canvas");
    this._sample.width = SAMPLE_W;
    this._sample.height = SAMPLE_H;
    this._sctx = this._sample.getContext("2d", { willReadFrequently: true });

    this._landmarker = null;
    this._drawer = null;
    this._raf = null;
    this._running = false;
    this._meshVisible = true;
    this._lastVideoTime = -1;

    this.onRgb = null; // callback([r,g,b] | null)
  }

  async load() {
    const fileset = await FilesetResolver.forVisionTasks(WASM_PATH);
    const opts = (delegate) => ({
      baseOptions: { modelAssetPath: MODEL_PATH, delegate },
      runningMode: "VIDEO",
      numFaces: 1,
    });
    try {
      this._landmarker = await FaceLandmarker.createFromOptions(fileset, opts("GPU"));
    } catch (_) {
      this._landmarker = await FaceLandmarker.createFromOptions(fileset, opts("CPU"));
    }
    this._drawer = new DrawingUtils(this.octx);
  }

  start() {
    if (!this._landmarker) return;
    this._running = true;
    this._loop();
  }

  stop() {
    this._running = false;
    if (this._raf) cancelAnimationFrame(this._raf);
    this.octx.clearRect(0, 0, this.overlay.width, this.overlay.height);
  }

  setMeshVisible(visible) {
    this._meshVisible = visible;
    if (!visible) this.octx.clearRect(0, 0, this.overlay.width, this.overlay.height);
  }

  _loop() {
    if (!this._running) return;

    if (this.video.videoWidth && this.video.videoHeight) {
      if (this.video.currentTime !== this._lastVideoTime) {
        this._lastVideoTime = this.video.currentTime;
        const result = this._landmarker.detectForVideo(this.video, performance.now());

        const has = result.faceLandmarks && result.faceLandmarks.length > 0;
        if (this._meshVisible) this._drawMesh(result);

        if (has) {
          const rgb = this._extractRgb(result.faceLandmarks[0]);
          this.onRgb?.(rgb);
        } else {
          this.onRgb?.(null);
        }
      }
    }

    this._raf = requestAnimationFrame(() => this._loop());
  }

  // ── Masque visuel ────────────────────────────────────────────────────────
  // Le canvas a la résolution NATIVE de la vidéo et le même object-fit:cover
  // (CSS) → il est croppé exactement comme la vidéo, donc le masque est aligné.
  _drawMesh(result) {
    const w = this.video.videoWidth, h = this.video.videoHeight;
    if (w && h && (this.overlay.width !== w || this.overlay.height !== h)) {
      this.overlay.width = w;
      this.overlay.height = h;
    }
    this.octx.clearRect(0, 0, this.overlay.width, this.overlay.height);
    if (!result.faceLandmarks || result.faceLandmarks.length === 0) return;

    for (const lm of result.faceLandmarks) {
      // Maillage fin cyan (style du design handoff)
      this._drawer.drawConnectors(lm, FaceLandmarker.FACE_LANDMARKS_TESSELATION,
        { color: "rgba(0,204,239,0.18)", lineWidth: 0.5 });
      const accent = { color: "rgba(0,204,239,0.7)", lineWidth: 1 };
      this._drawer.drawConnectors(lm, FaceLandmarker.FACE_LANDMARKS_FACE_OVAL, accent);
      this._drawer.drawConnectors(lm, FaceLandmarker.FACE_LANDMARKS_LEFT_EYE, accent);
      this._drawer.drawConnectors(lm, FaceLandmarker.FACE_LANDMARKS_RIGHT_EYE, accent);
      this._drawer.drawConnectors(lm, FaceLandmarker.FACE_LANDMARKS_LIPS, accent);
    }
  }

  // ── Extraction RGB de la peau (front + joues) ─────────────────────────────
  _extractRgb(lm) {
    this._sctx.drawImage(this.video, 0, 0, SAMPLE_W, SAMPLE_H);

    const faceW = Math.hypot(
      (lm[FACE_R].x - lm[FACE_L].x) * SAMPLE_W,
      (lm[FACE_R].y - lm[FACE_L].y) * SAMPLE_H
    );
    const half = Math.max(4, Math.round(faceW * 0.05));

    const centers = [
      { x: (lm[FRONT_TOP].x + lm[FRONT_MID].x) / 2, y: (lm[FRONT_TOP].y + lm[FRONT_MID].y) / 2 },
      { x: lm[CHEEK_L].x, y: lm[CHEEK_L].y },
      { x: lm[CHEEK_R].x, y: lm[CHEEK_R].y },
    ];

    let r = 0, g = 0, b = 0, n = 0;
    for (const c of centers) {
      const cx = Math.round(c.x * SAMPLE_W);
      const cy = Math.round(c.y * SAMPLE_H);
      const x = Math.max(0, cx - half);
      const y = Math.max(0, cy - half);
      const w = Math.min(half * 2, SAMPLE_W - x);
      const h = Math.min(half * 2, SAMPLE_H - y);
      if (w <= 0 || h <= 0) continue;

      const data = this._sctx.getImageData(x, y, w, h).data;
      for (let i = 0; i < data.length; i += 4) {
        r += data[i]; g += data[i + 1]; b += data[i + 2]; n++;
      }
    }
    if (n === 0) return null;
    return [r / n, g / n, b / n];
  }
}
