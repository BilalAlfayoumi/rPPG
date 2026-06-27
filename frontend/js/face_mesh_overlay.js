/**
 * Overlay du maillage facial 468 points via MediaPipe FaceLandmarker (WASM).
 * Tourne entièrement dans le navigateur, indépendamment du backend.
 *
 * Alignement : le canvas est dimensionné sur la taille AFFICHÉE de la vidéo
 * (getBoundingClientRect), pas sur son conteneur — évite tout décalage si la
 * grille CSS étire la carte vidéo.
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

export class FaceMeshOverlay {
  constructor(videoEl, canvasEl) {
    this.video = videoEl;
    this.canvas = canvasEl;
    this.ctx = canvasEl.getContext("2d");
    this._landmarker = null;
    this._drawer = null;
    this._raf = null;
    this._running = false;
    this._lastVideoTime = -1;
  }

  /** Charge le modèle (asynchrone). Tente le GPU, retombe sur le CPU si besoin. */
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
    this._drawer = new DrawingUtils(this.ctx);
  }

  start() {
    if (!this._landmarker) return;
    this._running = true;
    this._loop();
  }

  stop() {
    this._running = false;
    if (this._raf) cancelAnimationFrame(this._raf);
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
  }

  _syncSize() {
    // Taille RÉELLE affichée de la vidéo (pas du conteneur étiré par la grille)
    const rect = this.video.getBoundingClientRect();
    const w = Math.round(rect.width);
    const h = Math.round(rect.height);
    if (w && h && (this.canvas.width !== w || this.canvas.height !== h)) {
      this.canvas.width = w;
      this.canvas.height = h;
    }
  }

  _loop() {
    if (!this._running) return;

    if (this.video.videoWidth && this.video.videoHeight) {
      this._syncSize();
      const now = performance.now();
      if (this.video.currentTime !== this._lastVideoTime) {
        this._lastVideoTime = this.video.currentTime;
        const result = this._landmarker.detectForVideo(this.video, now);
        this._draw(result);
      }
    }

    this._raf = requestAnimationFrame(() => this._loop());
  }

  _draw(result) {
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    if (!result.faceLandmarks || result.faceLandmarks.length === 0) return;

    for (const landmarks of result.faceLandmarks) {
      this._drawer.drawConnectors(
        landmarks,
        FaceLandmarker.FACE_LANDMARKS_TESSELATION,
        { color: "rgba(79,142,247,0.4)", lineWidth: 0.6 }
      );
      const accent = { color: "rgba(34,197,94,0.9)", lineWidth: 1.3 };
      this._drawer.drawConnectors(landmarks, FaceLandmarker.FACE_LANDMARKS_FACE_OVAL, accent);
      this._drawer.drawConnectors(landmarks, FaceLandmarker.FACE_LANDMARKS_LEFT_EYE, accent);
      this._drawer.drawConnectors(landmarks, FaceLandmarker.FACE_LANDMARKS_RIGHT_EYE, accent);
      this._drawer.drawConnectors(landmarks, FaceLandmarker.FACE_LANDMARKS_LIPS, accent);
    }
  }
}
