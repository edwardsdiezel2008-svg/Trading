/**
 * Procedural wood-grain rendering, canvas 2D only. No stock photography —
 * every board face and the hero log cross-section are drawn from a small
 * per-species color/streak recipe, seeded so each species looks the same
 * on every visit instead of reshuffling on reload.
 */
(function () {
  function mulberry32(seed) {
    return function () {
      seed |= 0;
      seed = (seed + 0x6d2b79f5) | 0;
      let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function hashSeed(str) {
    let h = 0;
    for (let i = 0; i < str.length; i++) {
      h = (Math.imul(31, h) + str.charCodeAt(i)) | 0;
    }
    return h >>> 0;
  }

  const SPECIES_GRAIN = {
    oak: { base: '#c9a06a', dark: '#8a6a3f', light: '#e6c896', streaks: 22, ampScale: 0.7, rays: true, knots: 0 },
    walnut: { base: '#4a3220', dark: '#2e1d10', light: '#7a5638', streaks: 26, ampScale: 1.0, rays: false, knots: 1 },
    cherry: { base: '#8a4a3a', dark: '#5e2f22', light: '#b56a52', streaks: 20, ampScale: 0.6, rays: false, knots: 0 },
    maple: { base: '#e8dcc3', dark: '#c9b98f', light: '#f5ecd8', streaks: 14, ampScale: 0.4, rays: false, knots: 0 },
    hickory: { base: '#a97c50', dark: '#6e4b2a', light: '#c9a06a', streaks: 30, ampScale: 1.1, rays: false, knots: 2 },
    ash: { base: '#d9c9a3', dark: '#a8895a', light: '#efe3c4', streaks: 16, ampScale: 0.3, rays: false, knots: 0 },
  };

  function drawSwatch(ctx, w, h, key, t) {
    const cfg = SPECIES_GRAIN[key];
    if (!cfg) return;
    const rand = mulberry32(hashSeed(key));
    const time = t || 0;

    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = cfg.base;
    ctx.fillRect(0, 0, w, h);

    for (let i = 0; i < cfg.streaks; i++) {
      const y0 = rand() * h;
      const amp = (4 + rand() * 10) * cfg.ampScale;
      const freq = 0.006 + rand() * 0.01;
      const phase = rand() * Math.PI * 2;
      const dark = rand() > 0.5;

      ctx.strokeStyle = dark ? cfg.dark : cfg.light;
      ctx.globalAlpha = 0.16 + rand() * 0.22;
      ctx.lineWidth = 1 + rand() * 2.2;
      ctx.beginPath();
      for (let x = 0; x <= w; x += 6) {
        const y = y0 + Math.sin(x * freq + phase + time * 0.12) * amp;
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
    ctx.globalAlpha = 1;

    if (cfg.rays) {
      for (let i = 0; i < 9; i++) {
        const x = rand() * w;
        const rw = 2 + rand() * 5;
        ctx.fillStyle = cfg.light;
        ctx.globalAlpha = 0.1 + rand() * 0.1;
        ctx.fillRect(x, 0, rw, h);
      }
      ctx.globalAlpha = 1;
    }

    for (let i = 0; i < cfg.knots; i++) {
      const kx = rand() * w;
      const ky = rand() * h;
      const kr = 7 + rand() * 10;
      const grad = ctx.createRadialGradient(kx, ky, 1, kx, ky, kr);
      grad.addColorStop(0, cfg.dark);
      grad.addColorStop(1, 'transparent');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.ellipse(kx, ky, kr, kr * 0.6, rand() * Math.PI, 0, Math.PI * 2);
      ctx.fill();
    }

    const sheen = ctx.createLinearGradient(0, 0, w, 0);
    sheen.addColorStop(0, 'rgba(255,255,255,0.06)');
    sheen.addColorStop(0.5, 'rgba(255,255,255,0)');
    sheen.addColorStop(1, 'rgba(0,0,0,0.12)');
    ctx.fillStyle = sheen;
    ctx.fillRect(0, 0, w, h);
  }

  function drawHeroRings(ctx, w, h, t, mouse) {
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = '#1b140d';
    ctx.fillRect(0, 0, w, h);

    const cx = w * 0.72 + mouse.x * 30;
    const cy = h * 0.5 + mouse.y * 20;
    const maxR = Math.max(w, h) * 0.95;
    const rand = mulberry32(42);

    let r = 24;
    while (r < maxR) {
      const wobble = 6 + rand() * 10;
      const ringWidth = 7 + rand() * 15;
      const isLate = rand() > 0.5;
      ctx.strokeStyle = isLate ? 'rgba(217, 154, 68, 0.14)' : 'rgba(138, 90, 45, 0.12)';
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      for (let a = 0; a <= Math.PI * 2 + 0.1; a += 0.06) {
        const rr = r + Math.sin(a * 3 + t * 0.05 + r * 0.02) * wobble * 0.3;
        const x = cx + Math.cos(a) * rr;
        const y = cy + Math.sin(a) * rr * 0.98;
        if (a === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
      r += ringWidth;
    }

    const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, maxR * 0.5);
    glow.addColorStop(0, 'rgba(217, 154, 68, 0.10)');
    glow.addColorStop(1, 'rgba(217, 154, 68, 0)');
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, w, h);
  }

  window.WoodGrain = { drawSwatch, drawHeroRings };
})();
