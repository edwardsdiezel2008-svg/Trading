/**
 * Framed canvas hero scene: a dusk pine forest with drifting campfire
 * embers. Contained to its own panel (not full-bleed behind text) so
 * body copy always sits on a solid, high-contrast background. Motion is
 * slow and autonomous — no dependency on mouse movement — and freezes
 * on a single frame under prefers-reduced-motion.
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

  function buildTreeLayer(seed, count) {
    const rand = mulberry32(seed);
    const trees = [];
    for (let i = 0; i < count; i++) {
      trees.push({
        x: rand(),
        h: 0.35 + rand() * 0.5,
        w: 0.06 + rand() * 0.05,
      });
    }
    return trees;
  }

  function drawTreeLayer(ctx, w, h, baseY, trees, color, offsetX) {
    ctx.fillStyle = color;
    trees.forEach((t) => {
      const tx = (((t.x + offsetX) % 1) + 1) % 1;
      const cx = tx * (w + 120) - 60;
      const treeH = t.h * h * 0.7;
      const treeW = t.w * w;
      ctx.beginPath();
      ctx.moveTo(cx, baseY);
      ctx.lineTo(cx - treeW / 2, baseY);
      ctx.lineTo(cx, baseY - treeH);
      ctx.lineTo(cx + treeW / 2, baseY);
      ctx.closePath();
      ctx.fill();
      ctx.beginPath();
      ctx.moveTo(cx, baseY - treeH * 0.4);
      ctx.lineTo(cx - treeW * 0.4, baseY - treeH * 0.4);
      ctx.lineTo(cx, baseY - treeH * 1.25);
      ctx.lineTo(cx + treeW * 0.4, baseY - treeH * 0.4);
      ctx.closePath();
      ctx.fill();
    });
  }

  function buildEmbers(seed, count) {
    const rand = mulberry32(seed);
    const embers = [];
    for (let i = 0; i < count; i++) {
      embers.push({
        x: rand(),
        speed: 0.02 + rand() * 0.03,
        drift: (rand() - 0.5) * 0.015,
        size: 1 + rand() * 2,
        phase: rand(),
      });
    }
    return embers;
  }

  const layer1 = buildTreeLayer(7, 9);
  const layer2 = buildTreeLayer(19, 12);
  const layer3 = buildTreeLayer(31, 16);
  const embers = buildEmbers(88, 26);

  function drawScene(ctx, w, h, t) {
    const sky = ctx.createLinearGradient(0, 0, 0, h);
    sky.addColorStop(0, '#2b3a55');
    sky.addColorStop(0.45, '#5b5a6e');
    sky.addColorStop(0.72, '#c98a52');
    sky.addColorStop(1, '#e7b06a');
    ctx.fillStyle = sky;
    ctx.fillRect(0, 0, w, h);

    const glow = ctx.createRadialGradient(w * 0.68, h * 0.78, 0, w * 0.68, h * 0.78, w * 0.5);
    glow.addColorStop(0, 'rgba(255, 200, 120, 0.35)');
    glow.addColorStop(1, 'rgba(255, 200, 120, 0)');
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, w, h);

    const driftSlow = Math.sin(t * 0.03) * 0.01;
    drawTreeLayer(ctx, w, h, h * 0.86, layer3, 'rgba(31, 46, 34, 0.55)', t * 0.004 + driftSlow);
    drawTreeLayer(ctx, w, h, h * 0.92, layer2, 'rgba(24, 36, 27, 0.75)', -t * 0.006 + driftSlow * 1.5);
    drawTreeLayer(ctx, w, h, h * 0.98, layer1, '#16211a', t * 0.008 + driftSlow * 2);

    embers.forEach((e) => {
      const life = ((e.phase + t * e.speed) % 1 + 1) % 1;
      const ex = (e.x + Math.sin(t * 0.2 + e.phase * 10) * 0.02 + e.drift * t) % 1;
      const exWrapped = ((ex % 1) + 1) % 1;
      const ey = h * (1 - life * 0.85);
      const alpha = Math.sin(life * Math.PI);
      ctx.fillStyle = `rgba(255, 190, 110, ${alpha * 0.85})`;
      ctx.beginPath();
      ctx.arc(exWrapped * w, ey, e.size, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  window.RHKScene = { drawScene };
})();
