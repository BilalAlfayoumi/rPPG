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
  }

  connect() {
    this._onStatusChange("connecting");
    this._ws = new WebSocket(this._url);
    this._ws.binaryType = "arraybuffer";

    this._ws.addEventListener("open", () => this._onStatusChange("open"));
    this._ws.addEventListener("close", () => {
      this._stopInterval();
      this._onStatusChange("closed");
    });
    this._ws.addEventListener("error", () => {
      this._stopInterval();
      this._onStatusChange("error");
    });
    this._ws.addEventListener("message", (e) => {
      try {
        this._onMessage(JSON.parse(e.data));
      } catch (_) {}
    });
  }

  /**
   * Lance l'envoi des frames à fps images/s.
   * @param {WebcamCapture} webcam
   * @param {number} fps - fréquence d'envoi (défaut 10)
   */
  startStreaming(webcam, fps = 10) {
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
