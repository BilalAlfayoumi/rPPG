export class WebcamCapture {
  constructor(videoEl, canvasEl, width = 320, height = 240) {
    this.video = videoEl;
    this.canvas = canvasEl;
    this.ctx = canvasEl.getContext("2d");
    this.width = width;
    this.height = height;
    this.canvas.width = width;
    this.canvas.height = height;
    this._stream = null;
  }

  async start() {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error(
        "getUserMedia indisponible — ouvre la page via http://localhost:8000 (pas 127.0.0.1)"
      );
    }
    this._stream = await navigator.mediaDevices.getUserMedia({
      video: {
        facingMode: "user",           // caméra frontale (selfie)
        width:  { ideal: 640 },       // ratio paysage : évite une vidéo trop
        height: { ideal: 480 },       // haute en portrait mobile (le masque reste aligné)
      },
      audio: false,
    });
    this.video.srcObject = this._stream;
    // video.play() peut échouer si l'autoplay est déjà en cours — on l'ignore
    try { await this.video.play(); } catch (_) {}
  }

  stop() {
    if (this._stream) {
      this._stream.getTracks().forEach((t) => t.stop());
      this._stream = null;
      this.video.srcObject = null;
    }
  }

  /** Capture la frame courante et retourne un Blob JPEG. */
  captureBlob(quality = 0.6) {
    this.ctx.drawImage(this.video, 0, 0, this.width, this.height);
    return new Promise((resolve) =>
      this.canvas.toBlob(resolve, "image/jpeg", quality)
    );
  }

  get isRunning() {
    return this._stream !== null;
  }
}
