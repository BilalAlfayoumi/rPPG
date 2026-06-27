export class RPPGClient {
  /**
   * @param {string} url - URL WebSocket (ex: "ws://localhost:8000/ws/rppg")
   * @param {function} onMessage - callback appelé à chaque message JSON reçu
   * @param {function} onStatusChange - callback(status: "connecting"|"open"|"closed"|"error")
   */
  constructor(url, onMessage, onStatusChange) {
    this._url = url;
    this._onMessage = onMessage;
    this._onStatusChange = onStatusChange;
    this._ws = null;
    this._streamInterval = null;
    this._intentionalClose = false;
    this._retries = 0;
    this._maxRetries = 6;       // ~couvre un réveil à froid de la machine Fly
    this._everOpened = false;
  }

  connect() {
    this._intentionalClose = false;
    this._onStatusChange(this._retries > 0 ? "connecting-retry" : "connecting");
    this._ws = new WebSocket(this._url);
    this._ws.binaryType = "arraybuffer";

    this._ws.addEventListener("open", () => {
      this._retries = 0;
      this._everOpened = true;
      this._onStatusChange("open");
    });

    this._ws.addEventListener("close", () => {
      this._stopInterval();
      if (this._intentionalClose) {
        this._onStatusChange("closed");
      } else {
        this._scheduleReconnect();
      }
    });

    this._ws.addEventListener("error", () => {
      // 'error' est suivi de 'close' : on laisse close gérer le retry
      this._stopInterval();
    });

    this._ws.addEventListener("message", (e) => {
      try {
        this._onMessage(JSON.parse(e.data));
      } catch (_) {}
    });
  }

  /** Reconnexion automatique avec backoff (gère le réveil à froid du serveur). */
  _scheduleReconnect() {
    if (this._retries >= this._maxRetries) {
      this._onStatusChange("error");
      return;
    }
    this._retries += 1;
    const delay = Math.min(1000 * this._retries, 4000);
    this._onStatusChange("reconnecting");
    setTimeout(() => {
      if (!this._intentionalClose) {
        this.connect();
        if (this._pendingWebcam) this.startStreaming(this._pendingWebcam, this._pendingFps);
      }
    }, delay);
  }

  /**
   * Lance l'envoi des frames à fps images/s.
   * @param {WebcamCapture} webcam
   * @param {number} fps - fréquence d'envoi (défaut 10)
   */
  startStreaming(webcam, fps = 10) {
    this._pendingWebcam = webcam;  // mémorisé pour reprendre après reconnexion
    this._pendingFps = fps;
    this._stopInterval();
    this._streamInterval = setInterval(async () => {
      if (!webcam.isRunning || this._ws?.readyState !== WebSocket.OPEN) return;
      const blob = await webcam.captureBlob(0.6);
      if (blob) this._ws.send(blob);
    }, 1000 / fps);
  }

  stopStreaming() {
    this._stopInterval();
  }

  disconnect() {
    this._intentionalClose = true;
    this._pendingWebcam = null;
    this._stopInterval();
    this._ws?.close();
  }

  _stopInterval() {
    if (this._streamInterval) {
      clearInterval(this._streamInterval);
      this._streamInterval = null;
    }
  }
}
