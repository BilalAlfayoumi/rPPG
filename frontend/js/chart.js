export class BvpChart {
  /**
   * Courbe BVP en temps réel dessinée sur un <canvas> natif (pas de lib externe).
   * @param {HTMLCanvasElement} canvasEl
   * @param {number} maxPoints - nombre de points affichés (défaut 64)
   */
  constructor(canvasEl, maxPoints = 64) {
    this.canvas = canvasEl;
    this.ctx = canvasEl.getContext("2d");
    this.maxPoints = maxPoints;
    this._data = [];
    this._raf = null;
    this._dirty = false;
    this._color = "0,204,239";   // cyan par défaut (design)
    this._startLoop();
  }

  /** Couleur de la courbe en "r,g,b" (ex. "255,31,78" pour le rouge). */
  setColor(rgb) { this._color = rgb; this._dirty = true; }

  update(points) {
    if (!Array.isArray(points) || points.length === 0) return;
    this._data = points.slice(-this.maxPoints);
    this._dirty = true;
  }

  clear() {
    this._data = [];
    this._dirty = true;
  }

  _startLoop() {
    const draw = () => {
      if (this._dirty) {
        this._draw();
        this._dirty = false;
      }
      this._raf = requestAnimationFrame(draw);
    };
    this._raf = requestAnimationFrame(draw);
  }

  _draw() {
    const { canvas, ctx } = this;
    const W = canvas.offsetWidth;
    const H = canvas.offsetHeight;
    if (canvas.width !== W || canvas.height !== H) {
      canvas.width = W;
      canvas.height = H;
    }

    ctx.clearRect(0, 0, W, H);

    const data = this._data;
    if (data.length < 2) {
      this._drawEmpty(W, H);
      return;
    }

    // Normaliser entre 0 et 1
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    const norm = data.map((v) => (v - min) / range);

    const pad = 8;
    const w = W - pad * 2;
    const h = H - pad * 2;

    // Grille horizontale légère
    ctx.strokeStyle = "rgba(255,255,255,0.04)";
    ctx.lineWidth = 1;
    for (let y of [0.25, 0.5, 0.75]) {
      ctx.beginPath();
      ctx.moveTo(pad, pad + y * h);
      ctx.lineTo(pad + w, pad + y * h);
      ctx.stroke();
    }

    // Courbe avec dégradé
    const gradient = ctx.createLinearGradient(0, 0, W, 0);
    gradient.addColorStop(0, `rgba(${this._color},0.3)`);
    gradient.addColorStop(1, `rgba(${this._color},1)`);

    ctx.beginPath();
    ctx.strokeStyle = gradient;
    ctx.lineWidth = 2;
    ctx.lineJoin = "round";
    norm.forEach((v, i) => {
      const x = pad + (i / (norm.length - 1)) * w;
      const y = pad + (1 - v) * h;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();
  }

  _drawEmpty(W, H) {
    const { ctx } = this;
    ctx.strokeStyle = "rgba(255,255,255,0.06)";
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(0, H / 2);
    ctx.lineTo(W, H / 2);
    ctx.stroke();
    ctx.setLineDash([]);
  }
}
