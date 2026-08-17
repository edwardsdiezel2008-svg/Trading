/**
 * Small, self-contained canvas-2D demos shown inside each project's case
 * study modal. Each function draws one frame given elapsed time and a
 * normalized (-1..1) mouse position, plus a per-open state bag for demos
 * that need persistent particles/circles between frames.
 */
window.PORTFOLIO_DEMOS = {

  nebula(ctx, w, h, t, mouse) {
    ctx.fillStyle = '#05070d';
    ctx.fillRect(0, 0, w, h);

    const cx = w / 2 + mouse.x * 40;
    const cy = h / 2 + mouse.y * 24;
    const hue = 165 + Math.sin(t * 0.4) * 35;
    const r = Math.min(w, h) * 0.32 + Math.sin(t * 0.6) * 14;

    const grad = ctx.createRadialGradient(cx, cy, 4, cx, cy, r);
    grad.addColorStop(0, `hsla(${hue}, 85%, 72%, 0.95)`);
    grad.addColorStop(0.55, `hsla(${hue + 45}, 80%, 60%, 0.45)`);
    grad.addColorStop(1, 'rgba(5, 7, 13, 0)');

    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fill();
  },

  signal(ctx, w, h, t, mouse, state) {
    if (!state.particles) {
      state.particles = Array.from({ length: 160 }, () => ({
        x: Math.random() * w,
        y: Math.random() * h,
      }));
    }

    ctx.fillStyle = 'rgba(5, 7, 13, 0.16)';
    ctx.fillRect(0, 0, w, h);

    state.particles.forEach((p) => {
      const angle =
        Math.sin(p.x * 0.012 + t * 0.5 + mouse.x) +
        Math.cos(p.y * 0.012 - t * 0.35 + mouse.y);
      p.x += Math.cos(angle) * 1.7;
      p.y += Math.sin(angle) * 1.7;
      if (p.x < 0) p.x = w;
      if (p.x > w) p.x = 0;
      if (p.y < 0) p.y = h;
      if (p.y > h) p.y = 0;

      ctx.fillStyle = 'rgba(167, 139, 250, 0.85)';
      ctx.fillRect(p.x, p.y, 2, 2);
    });
  },

  aperture(ctx, w, h, t, mouse, state) {
    if (!state.circles) {
      state.circles = Array.from({ length: 16 }, () => ({
        x: Math.random() * w,
        y: Math.random() * h,
        r: 24 + Math.random() * 70,
        depth: Math.random(),
        hue: 170 + Math.random() * 80,
        vx: (Math.random() - 0.5) * 0.18,
        vy: (Math.random() - 0.5) * 0.18,
      }));
    }

    ctx.fillStyle = '#05070d';
    ctx.fillRect(0, 0, w, h);

    const sorted = [...state.circles].sort((a, b) => a.depth - b.depth);
    sorted.forEach((c) => {
      c.x += c.vx;
      c.y += c.vy;
      if (c.x < -c.r) c.x = w + c.r;
      if (c.x > w + c.r) c.x = -c.r;
      if (c.y < -c.r) c.y = h + c.r;
      if (c.y > h + c.r) c.y = -c.r;

      const blur = (1 - c.depth) * 16;
      ctx.filter = blur > 0.5 ? `blur(${blur}px)` : 'none';
      ctx.globalAlpha = 0.32 + c.depth * 0.4;
      ctx.fillStyle = `hsl(${c.hue}, 70%, 65%)`;
      ctx.beginPath();
      ctx.arc(
        c.x + mouse.x * 12 * (1 - c.depth),
        c.y + mouse.y * 12 * (1 - c.depth),
        c.r * (0.4 + c.depth * 0.6),
        0,
        Math.PI * 2
      );
      ctx.fill();
    });

    ctx.filter = 'none';
    ctx.globalAlpha = 1;
  },

  foundry(ctx, w, h, t, mouse) {
    ctx.fillStyle = '#05070d';
    ctx.fillRect(0, 0, w, h);

    const cols = 22;
    const rows = 13;
    const originX = w / 2 + mouse.x * 16;
    const originY = h * 0.22 + mouse.y * 10;
    const tileW = w / cols;
    const tileH = tileW * 0.5;

    function elevation(gx, gy) {
      return Math.sin(gx * 0.5 + t * 0.6) * 12 + Math.cos(gy * 0.4 - t * 0.4) * 12;
    }

    function project(gx, gy) {
      const e = elevation(gx, gy);
      return [
        originX + (gx - gy) * (tileW / 2),
        originY + (gx + gy) * (tileH / 2) - e,
      ];
    }

    ctx.strokeStyle = 'rgba(94, 234, 212, 0.4)';
    ctx.lineWidth = 1;

    for (let gy = 0; gy < rows; gy++) {
      ctx.beginPath();
      for (let gx = 0; gx < cols; gx++) {
        const [x, y] = project(gx, gy);
        if (gx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }

    for (let gx = 0; gx < cols; gx++) {
      ctx.beginPath();
      for (let gy = 0; gy < rows; gy++) {
        const [x, y] = project(gx, gy);
        if (gy === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
  },

};
