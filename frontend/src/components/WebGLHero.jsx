import React, { useEffect, useRef } from 'react';

/* High-grade decorative WebGL (OpenGL ES) layer for the hero.

   Renders a real 3D wireframe MESH terrain — a perspective-projected grid
   whose vertices are displaced every frame by layered sine surfaces, drawn
   as additively-blended glowing lines + node points, tinted with the
   MediFleet brand palette (deep teal → cyan → emerald) and dissolved into
   the dark hero with distance fog. A gentle cursor parallax sways the camera.

   Why raw WebGL (no three.js / gl-matrix):
     • Zero added bundle weight / no package-lock churn.
     • The effect is one grid + two draw calls; the 4×4 matrix math fits in
       ~30 lines, so a 600 kB dependency would be pure overhead.

   Performance & safety
     • Honors prefers-reduced-motion: paints a single static frame, no rAF.
     • Graceful no-op when WebGL is unavailable (CSS hero background remains).
     • Grid density adapts to viewport; DPR capped at 2; resizes with parent.
     • Single rAF loop, no React re-renders. Full GL teardown on unmount,
       including WEBGL_lose_context.
     • aria-hidden + pointer-events-none — purely cosmetic.
*/

const VERT_SRC = `
attribute vec2 a_uv;
uniform mat4 u_proj;
uniform mat4 u_view;
uniform float u_time;
uniform float u_point;
varying float v_h;
varying float v_fog;

const float SPAN_X = 26.0;   // mesh width
const float Z_NEAR =  5.0;   // nearest row (below camera)
const float Z_FAR  = -30.0;  // farthest row (toward horizon)

// Layered sine surface — cheap, smooth, and continuously flowing.
float surface(vec2 w, float t) {
  float y = 0.0;
  y += sin(w.x * 0.45 + t)              * 0.90;
  y += sin(w.y * 0.40 + t * 0.80)       * 0.80;
  y += sin((w.x + w.y) * 0.30 - t * 0.6) * 0.55;
  y += sin(length(w) * 0.50 - t * 1.10) * 0.45;
  return y;
}

void main() {
  float x = (a_uv.x - 0.5) * SPAN_X;
  float z = mix(Z_NEAR, Z_FAR, a_uv.y);
  float y = surface(vec2(x, z), u_time) - 1.5;

  vec4 viewPos = u_view * vec4(x, y, z, 1.0);
  gl_Position = u_proj * viewPos;
  gl_PointSize = u_point;

  v_h   = y;
  v_fog = clamp((-viewPos.z) / 34.0, 0.0, 1.0);
}
`;

const FRAG_SRC = `
precision mediump float;
varying float v_h;
varying float v_fog;
uniform float u_alpha;

void main() {
  float h = clamp(v_h * 0.35 + 0.5, 0.0, 1.0);

  vec3 deep    = vec3(0.04, 0.26, 0.40);   // deep teal trough
  vec3 cyan    = vec3(0.22, 0.86, 0.96);   // brand cyan crest
  vec3 emerald = vec3(0.12, 0.88, 0.56);   // emerald peak

  vec3 col = mix(deep, cyan, smoothstep(0.25, 0.70, h));
  col = mix(col, emerald, smoothstep(0.65, 1.0, h));

  // Brighter where high, dissolved by distance fog.
  float a = u_alpha * (0.22 + 0.62 * h) * (1.0 - v_fog);

  // Additive blend (SRC_ALPHA, ONE): rgb is added * a, so output raw colour.
  gl_FragColor = vec4(col, a);
}
`;

function compile(gl, type, src) {
  const sh = gl.createShader(type);
  gl.shaderSource(sh, src);
  gl.compileShader(sh);
  if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
    gl.deleteShader(sh);
    return null;
  }
  return sh;
}

// ── Minimal column-major mat4 helpers (no gl-matrix dependency) ──
function perspective(fovy, aspect, near, far) {
  const f = 1 / Math.tan(fovy / 2);
  const nf = 1 / (near - far);
  return new Float32Array([
    f / aspect, 0, 0, 0,
    0, f, 0, 0,
    0, 0, (far + near) * nf, -1,
    0, 0, 2 * far * near * nf, 0,
  ]);
}
function lookAt(eye, center, up) {
  let z0 = eye[0] - center[0], z1 = eye[1] - center[1], z2 = eye[2] - center[2];
  const zl = 1 / Math.hypot(z0, z1, z2); z0 *= zl; z1 *= zl; z2 *= zl;
  let x0 = up[1] * z2 - up[2] * z1, x1 = up[2] * z0 - up[0] * z2, x2 = up[0] * z1 - up[1] * z0;
  let xl = Math.hypot(x0, x1, x2); if (xl) { xl = 1 / xl; x0 *= xl; x1 *= xl; x2 *= xl; }
  const y0 = z1 * x2 - z2 * x1, y1 = z2 * x0 - z0 * x2, y2 = z0 * x1 - z1 * x0;
  return new Float32Array([
    x0, y0, z0, 0,
    x1, y1, z1, 0,
    x2, y2, z2, 0,
    -(x0 * eye[0] + x1 * eye[1] + x2 * eye[2]),
    -(y0 * eye[0] + y1 * eye[1] + y2 * eye[2]),
    -(z0 * eye[0] + z1 * eye[1] + z2 * eye[2]),
    1,
  ]);
}

// Build a grid of N×N vertices (UVs in 0..1) plus the wireframe line indices.
function buildGrid(N) {
  const uvs = new Float32Array(N * N * 2);
  let p = 0;
  for (let r = 0; r < N; r++) {
    for (let c = 0; c < N; c++) {
      uvs[p++] = c / (N - 1);
      uvs[p++] = r / (N - 1);
    }
  }
  const idx = new Uint16Array(2 * 2 * N * (N - 1));
  let i = 0;
  for (let r = 0; r < N; r++) {
    for (let c = 0; c < N; c++) {
      const a = r * N + c;
      if (c < N - 1) { idx[i++] = a; idx[i++] = a + 1; }     // horizontal
      if (r < N - 1) { idx[i++] = a; idx[i++] = a + N; }     // vertical
    }
  }
  return { uvs, idx, count: i, verts: N * N };
}

export default function WebGLHero({ className = '' }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const canvas = canvasRef.current;
    if (!canvas) return;

    const gl =
      canvas.getContext('webgl', { alpha: true, premultipliedAlpha: false, antialias: true }) ||
      canvas.getContext('experimental-webgl', { alpha: true, premultipliedAlpha: false });
    if (!gl) return; // graceful no-op

    const vs = compile(gl, gl.VERTEX_SHADER, VERT_SRC);
    const fs = compile(gl, gl.FRAGMENT_SHADER, FRAG_SRC);
    if (!vs || !fs) return;

    const prog = gl.createProgram();
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return;
    gl.useProgram(prog);

    const N = window.innerWidth < 768 ? 80 : 120;
    const grid = buildGrid(N);

    const vbo = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
    gl.bufferData(gl.ARRAY_BUFFER, grid.uvs, gl.STATIC_DRAW);
    const aUV = gl.getAttribLocation(prog, 'a_uv');
    gl.enableVertexAttribArray(aUV);
    gl.vertexAttribPointer(aUV, 2, gl.FLOAT, false, 0, 0);

    const ibo = gl.createBuffer();
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, ibo);
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, grid.idx, gl.STATIC_DRAW);

    const uProj = gl.getUniformLocation(prog, 'u_proj');
    const uView = gl.getUniformLocation(prog, 'u_view');
    const uTime = gl.getUniformLocation(prog, 'u_time');
    const uAlpha = gl.getUniformLocation(prog, 'u_alpha');
    const uPoint = gl.getUniformLocation(prog, 'u_point');

    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE); // additive glow
    gl.clearColor(0, 0, 0, 0);

    let dprScale = 1;
    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      dprScale = dpr;
      const w = Math.max(1, Math.floor(canvas.clientWidth * dpr));
      const h = Math.max(1, Math.floor(canvas.clientHeight * dpr));
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.uniformMatrix4fv(uProj, false, perspective(0.9, w / h, 0.1, 100));
    };

    // Cursor parallax — lerp the camera's x toward the pointer.
    let tx = 0, mx = 0;
    const onMove = (e) => { tx = (e.clientX / window.innerWidth - 0.5) * 2; };

    const setView = () => {
      const eye = [mx * 2.4, 4.2, 9.0];
      gl.uniformMatrix4fv(uView, false, lookAt(eye, [0, -1.0, -8.0], [0, 1, 0]));
    };

    const draw = (timeMs) => {
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.uniform1f(uTime, timeMs * 0.001);
      setView();
      // Lines (wireframe mesh)
      gl.uniform1f(uAlpha, 0.55);
      gl.uniform1f(uPoint, 1.0);
      gl.drawElements(gl.LINES, grid.count, gl.UNSIGNED_SHORT, 0);
      // Node points (brighter — the "artifacts" on the lattice)
      gl.uniform1f(uAlpha, 0.9);
      gl.uniform1f(uPoint, 2.2 * dprScale);
      gl.drawArrays(gl.POINTS, 0, grid.verts);
    };

    resize();

    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let raf = 0;
    const onResize = () => resize();
    window.addEventListener('resize', onResize, { passive: true });

    if (reduce) {
      draw(0);
    } else {
      window.addEventListener('pointermove', onMove, { passive: true });
      const tick = (t) => {
        mx += (tx - mx) * 0.05;
        draw(t);
        raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    }

    return () => {
      window.removeEventListener('resize', onResize);
      window.removeEventListener('pointermove', onMove);
      if (raf) cancelAnimationFrame(raf);
      gl.deleteBuffer(vbo);
      gl.deleteBuffer(ibo);
      gl.deleteProgram(prog);
      gl.deleteShader(vs);
      gl.deleteShader(fs);
      const lose = gl.getExtension('WEBGL_lose_context');
      if (lose) lose.loseContext();
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className={`block size-full ${className}`}
    />
  );
}
