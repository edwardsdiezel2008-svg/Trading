/**
 * Raw WebGL raymarched background. No Three.js, no build step —
 * a single fragment shader rendering a lit, morphing metaball scene.
 */
(function () {
  const canvas = document.getElementById('bg-canvas');
  if (!canvas) return;

  const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
  if (!gl) {
    document.body.classList.add('no-webgl');
    return;
  }

  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const VERT_SRC = `
    attribute vec2 aPosition;
    void main() {
      gl_Position = vec4(aPosition, 0.0, 1.0);
    }
  `;

  const FRAG_SRC = `
    #ifdef GL_FRAGMENT_PRECISION_HIGH
      precision highp float;
    #else
      precision mediump float;
    #endif

    uniform vec2 uResolution;
    uniform float uTime;
    uniform vec2 uMouse;

    mat2 rot(float a) {
      float c = cos(a), s = sin(a);
      return mat2(c, -s, s, c);
    }

    float sdSphere(vec3 p, float r) {
      return length(p) - r;
    }

    float smin(float a, float b, float k) {
      float h = clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0);
      return mix(b, a, h) - k * h * (1.0 - h);
    }

    float map(vec3 p) {
      float t = uTime * 0.45;
      vec3 p1 = p - vec3(sin(t) * 0.85, cos(t * 1.3) * 0.5, sin(t * 0.6) * 0.2);
      vec3 p2 = p - vec3(-sin(t * 0.7) * 0.95, sin(t * 0.9) * 0.6, cos(t * 0.5) * 0.35);
      vec3 p3 = p - vec3(cos(t * 0.55) * 0.6, -cos(t * 0.8) * 0.7, sin(t * 0.4) * 0.4);

      float d1 = sdSphere(p1, 0.85);
      float d2 = sdSphere(p2, 0.68);
      float d3 = sdSphere(p3, 0.55);

      float d = smin(d1, d2, 0.65);
      d = smin(d, d3, 0.65);
      return d;
    }

    vec3 calcNormal(vec3 p) {
      vec2 e = vec2(0.0015, 0.0);
      return normalize(vec3(
        map(p + e.xyy) - map(p - e.xyy),
        map(p + e.yxy) - map(p - e.yxy),
        map(p + e.yyx) - map(p - e.yyx)
      ));
    }

    float calcAO(vec3 p, vec3 n) {
      float occ = 0.0;
      float sca = 1.0;
      for (int i = 0; i < 5; i++) {
        float h = 0.01 + 0.12 * float(i) / 4.0;
        float d = map(p + n * h);
        occ += (h - d) * sca;
        sca *= 0.75;
      }
      return clamp(1.0 - 2.0 * occ, 0.0, 1.0);
    }

    float hash(vec2 p) {
      return fract(sin(dot(p, vec2(41.3, 289.1))) * 43758.5453);
    }

    void main() {
      vec2 uv = (gl_FragCoord.xy - 0.5 * uResolution.xy) / uResolution.y;

      float yaw = uMouse.x * 0.55 + uTime * 0.04;
      float pitch = uMouse.y * 0.28 + 0.18;

      vec3 ro = vec3(0.0, 0.0, 3.4);
      ro.yz *= rot(pitch);
      ro.xz *= rot(yaw);

      vec3 rd = normalize(vec3(uv, -1.45));
      rd.yz *= rot(pitch);
      rd.xz *= rot(yaw);

      float t = 0.0;
      float hit = -1.0;
      vec3 p = ro;

      for (int i = 0; i < 96; i++) {
        p = ro + rd * t;
        float d = map(p);
        if (d < 0.0015) { hit = t; break; }
        t += d;
        if (t > 12.0) break;
      }

      vec3 colorTop = vec3(0.04, 0.055, 0.1);
      vec3 colorBottom = vec3(0.02, 0.027, 0.05);
      vec3 col = mix(colorBottom, colorTop, clamp(uv.y * 0.5 + 0.5, 0.0, 1.0));

      float star = hash(floor(gl_FragCoord.xy * 0.6));
      if (star > 0.9975) {
        col += vec3(0.6, 0.7, 0.8) * (star - 0.9975) * 220.0 * 0.15;
      }

      if (hit > 0.0) {
        vec3 n = calcNormal(p);
        vec3 lightDir = normalize(vec3(0.6, 0.7, 0.5));
        float diff = clamp(dot(n, lightDir), 0.0, 1.0);
        float ao = calcAO(p, n);
        float fres = pow(1.0 - clamp(dot(n, -rd), 0.0, 1.0), 3.0);

        vec3 accentA = vec3(0.37, 0.92, 0.83);
        vec3 accentB = vec3(0.65, 0.55, 0.98);
        vec3 base = mix(accentA, accentB, 0.5 + 0.5 * sin(p.x * 1.4 + p.y * 1.1 + uTime * 0.3));

        vec3 lit = base * (0.12 + 0.88 * diff) * ao;
        lit += fres * vec3(0.65, 0.85, 1.0) * 0.9;

        col = mix(lit, col, smoothstep(4.0, 12.0, hit));
      }

      col *= 1.0 - 0.35 * dot(uv, uv);

      gl_FragColor = vec4(col, 1.0);
    }
  `;

  function compileShader(type, src) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, src);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      console.error('Shader compile error:', gl.getShaderInfoLog(shader));
      gl.deleteShader(shader);
      return null;
    }
    return shader;
  }

  const vertShader = compileShader(gl.VERTEX_SHADER, VERT_SRC);
  const fragShader = compileShader(gl.FRAGMENT_SHADER, FRAG_SRC);

  if (!vertShader || !fragShader) {
    document.body.classList.add('no-webgl');
    return;
  }

  const program = gl.createProgram();
  gl.attachShader(program, vertShader);
  gl.attachShader(program, fragShader);
  gl.linkProgram(program);

  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    console.error('Program link error:', gl.getProgramInfoLog(program));
    document.body.classList.add('no-webgl');
    return;
  }

  gl.useProgram(program);

  const positionBuffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
  // Single fullscreen triangle, avoids seam issues of a two-triangle quad.
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([
    -1, -1,
     3, -1,
    -1,  3,
  ]), gl.STATIC_DRAW);

  const aPosition = gl.getAttribLocation(program, 'aPosition');
  gl.enableVertexAttribArray(aPosition);
  gl.vertexAttribPointer(aPosition, 2, gl.FLOAT, false, 0, 0);

  const uResolution = gl.getUniformLocation(program, 'uResolution');
  const uTime = gl.getUniformLocation(program, 'uTime');
  const uMouse = gl.getUniformLocation(program, 'uMouse');

  let dpr = Math.min(window.devicePixelRatio || 1, 1.75);
  let mouse = { x: 0, y: 0 };
  let mouseTarget = { x: 0, y: 0 };

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 1.75);
    const w = Math.floor(window.innerWidth * dpr);
    const h = Math.floor(window.innerHeight * dpr);
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
      gl.viewport(0, 0, w, h);
    }
  }

  window.addEventListener('resize', resize);
  resize();

  window.addEventListener('mousemove', (e) => {
    mouseTarget.x = (e.clientX / window.innerWidth) * 2 - 1;
    mouseTarget.y = -((e.clientY / window.innerHeight) * 2 - 1);
  });

  let running = true;
  document.addEventListener('visibilitychange', () => {
    running = !document.hidden;
    if (running) requestAnimationFrame(render);
  });

  const start = performance.now();
  const staticTime = 6.0;

  function render(now) {
    if (!running) return;

    mouse.x += (mouseTarget.x - mouse.x) * 0.06;
    mouse.y += (mouseTarget.y - mouse.y) * 0.06;

    const elapsed = prefersReducedMotion ? staticTime : (now - start) / 1000;

    gl.uniform2f(uResolution, canvas.width, canvas.height);
    gl.uniform1f(uTime, elapsed);
    gl.uniform2f(uMouse, mouse.x, mouse.y);

    gl.drawArrays(gl.TRIANGLES, 0, 3);

    if (!prefersReducedMotion) {
      requestAnimationFrame(render);
    }
  }

  requestAnimationFrame(render);
})();
