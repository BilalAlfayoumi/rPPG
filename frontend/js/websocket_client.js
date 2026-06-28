export class RPPGClient {
  /**
   * Client WebSocket : envoie les valeurs RGB extraites du visage (côté navigateur)
   * et reçoit les mises à jour de BPM. Reconnexion automatique (réveil à froid).
   *
   * @param {string} url
   * @param {function} onMessage - callback(message JSON reçu)
   * @param {function} onStatusChange - callback("connecting"|"open"|"reconnecting"|"closed"|"error")
   */
  constructor(url, onMessage, onStatusChange) {
    this._url = url;
    this._onMessage = onMessage;
    this._onStatusChange = onStatusChange;
    this._ws = null;
    this._intentionalClose = false;
    this._retries = 0;
    this._maxRetries = 6;
  }

  connect() {
    this._intentionalClose = false;
    this._onStatusChange("connecting");
    this._ws = new WebSocket(this._url);

    this._ws.addEventListener("open", () => {
      this._retries = 0;
      this._onStatusChange("open");
    });
    this._ws.addEventListener("close", () => {
      if (this._intentionalClose) this._onStatusChange("closed");
      else this._scheduleReconnect();
    });
    this._ws.addEventListener("error", () => {/* 'close' gère le retry */});
    this._ws.addEventListener("message", (e) => {
      try { this._onMessage(JSON.parse(e.data)); } catch (_) {}
    });
  }

  /** Envoie un échantillon RGB [r,g,b] au serveur (si la connexion est ouverte). */
  sendRgb(rgb) {
    if (this._ws?.readyState === WebSocket.OPEN) {
      this._ws.send(JSON.stringify({ type: "rgb", rgb }));
    }
  }

  disconnect() {
    this._intentionalClose = true;
    this._ws?.close();
  }

  get isOpen() {
    return this._ws?.readyState === WebSocket.OPEN;
  }

  _scheduleReconnect() {
    if (this._retries >= this._maxRetries) {
      this._onStatusChange("error");
      return;
    }
    this._retries += 1;
    const delay = Math.min(1000 * this._retries, 4000);
    this._onStatusChange("reconnecting");
    setTimeout(() => {
      if (!this._intentionalClose) this.connect();
    }, delay);
  }
}
