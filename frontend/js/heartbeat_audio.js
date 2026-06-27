/**
 * Son de battement cardiaque ("lub-dub") synthétisé via Web Audio API,
 * cadencé en temps réel sur le BPM détecté.
 */
export class HeartbeatAudio {
  constructor() {
    this._ctx = null;
    this._bpm = 0;
    this._timer = null;
    this._enabled = false;
  }

  /** Doit être appelé suite à une interaction utilisateur (politique autoplay). */
  enable() {
    if (!this._ctx) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      this._ctx = new AudioCtx();
    }
    if (this._ctx.state === "suspended") this._ctx.resume();
    this._enabled = true;
    this._scheduleNext();
  }

  disable() {
    this._enabled = false;
    if (this._timer) {
      clearTimeout(this._timer);
      this._timer = null;
    }
  }

  setBpm(bpm) {
    this._bpm = bpm;
  }

  get isEnabled() {
    return this._enabled;
  }

  /** Un "thump" : oscillateur basse fréquence avec enveloppe percussive. */
  _thump(at, freq, duration, peakGain) {
    const osc = this._ctx.createOscillator();
    const gain = this._ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(freq, at);
    osc.frequency.exponentialRampToValueAtTime(freq * 0.6, at + duration);

    gain.gain.setValueAtTime(0.0001, at);
    gain.gain.exponentialRampToValueAtTime(peakGain, at + 0.012);
    gain.gain.exponentialRampToValueAtTime(0.0001, at + duration);

    osc.connect(gain).connect(this._ctx.destination);
    osc.start(at);
    osc.stop(at + duration);
  }

  /** Joue un cycle "lub-dub". */
  _beat() {
    const t = this._ctx.currentTime;
    this._thump(t, 60, 0.14, 0.55);          // lub (S1, grave)
    this._thump(t + 0.16, 48, 0.13, 0.38);   // dub (S2, plus grave et faible)
  }

  /** Reprogramme le prochain battement selon le BPM courant. */
  _scheduleNext() {
    if (!this._enabled) return;

    if (this._bpm > 0) {
      this._beat();
    }

    // Intervalle = 60/BPM ; si pas de BPM, on revérifie dans 1s
    const interval = this._bpm > 0 ? (60 / this._bpm) * 1000 : 1000;
    this._timer = setTimeout(() => this._scheduleNext(), interval);
  }
}
