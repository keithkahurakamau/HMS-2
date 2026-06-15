import React, { useEffect, useRef } from 'react';

/* Decorative WebGL (OpenGL ES via the browser) layer for the hero.

   A single full-screen quad runs a fragment shader that animates a slow,
   flowing field of domain-warped value noise tinted with the MediFleet
   brand palette (cyan → teal → emerald). It's a quiet, continuously-alive
   wash that sits *behind* the hero content and complements the CSS-driven
   PremiumBackground — no new dependencies, just raw WebGL.

   Why raw WebGL instead of three.js:
     • Zero added bundle weight / no package-lock churn.
     • One quad + one shader is all this effect needs.

   Performance & safety
     • Honors prefers-reduced-motion: the rAF loop never starts and the
       canvas paints a single static frame (or nothing if WebGL is absent).
     • aria-hidden + pointer-events-none — purely cosmetic.
     • Single rAF loop, no React re-renders. Full GL teardown on unmount.
     • Caps the drawing-buffer at devicePixelRatio≤2 so it stays cheap on
       hi-dpi screens; resizes with the container.
*/

const VERT_SRC = `
attribute vec2 a_pos;
void main() {
  gl_Position = vec4(a_pos, 0.0, 1.0);
}
`;

// Domain-warped value noise, tinted with the brand gradient. Kept compact
// and dependency-free; runs comfortably on integrated GPUs at this size.
const FRAG_SRC = `
precision mediump float;
uniform vec2  u_res;
uniform float u_time;

// hash + value noise
float hash(vec2 p) {
  p = fract(p * vec2(123.34, 345.45));
  p += dot(p, p + 34.345);
  return fract(p.x * p.y);
}
float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  float a = hash(i);
  float b = hash(i + vec2(1.0, 0.0));
  float c = hash(i + vec2(0.0, 1.0));
  float d = hash(i + vec2(1.0, 1.0));
  return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}
float fbm(vec2 p) {
  float v = 0.0;
  float amp = 0.5;
  for (int i = 0; i < 5; i++) {
    v += amp * noise(p);
    p *= 2.0;
    amp *= 0.5;
  }
  return v;
}

void main() {
  vec2 uv = gl_FragCoord.xy / u_res.xy;
  vec2 p  = uv * 3.0;
  p.x *= u_res.x / u_res.y;          // keep noise isotropic

  float t = u_time * 0.05;
  // domain warp for the slow "flowing" feel
  vec2 q = vec2(fbm(p + t), fbm(p + vec2(5.2, 1.3) - t));
  float f = fbm(p + 1.8 * q + t * 0.5);

  // brand palette: cyan -> teal -> emerald
  vec3 cyan    = vec3(0.133, 0.827, 0.933);
  vec3 teal    = vec3(0.078, 0.722, 0.651);
  vec3 emerald = vec3(0.063, 0.725, 0.506);

  vec3 col = mix(cyan, teal, smoothstep(0.2, 0.6, f));
  col = mix(col, emerald, smoothstep(0.5, 0.9, f));

  // soft vignette + gentle overall transparency so the wash stays subtle
  float vign = smoothstep(1.15, 0.25, length(uv - 0.5));
  float alpha = (0.18 + 0.32 * f) * vign;

  gl_FragColor = vec4(col, alpha);
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

export default function WebGLHero({ className = '' }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const canvas = canvasRef.current;
    if (!canvas) return;

    const gl =
      canvas.getContext('webgl', { alpha: true, premultipliedAlpha: false, antialias: false }) ||
      canvas.getContext('experimental-webgl', { alpha: true, premultipliedAlpha: false });
    if (!gl) return; // graceful no-op when WebGL is unavailable

    const vs = compile(gl, gl.VERTEX_SHADER, VERT_SRC);
    const fs = compile(gl, gl.FRAGMENT_SHADER, FRAG_SRC);
    if (!vs || !fs) return;

    const prog = gl.createProgram();
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return;
    gl.useProgram(prog);

    // Full-screen quad (two triangles).
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]),
      gl.STATIC_DRAW,
    );
    const aPos = gl.getAttribLocation(prog, 'a_pos');
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

    const uRes = gl.getUniformLocation(prog, 'u_res');
    const uTime = gl.getUniformLocation(prog, 'u_time');

    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = Math.max(1, Math.floor(canvas.clientWidth * dpr));
      const h = Math.max(1, Math.floor(canvas.clientHeight * dpr));
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.uniform2f(uRes, canvas.width, canvas.height);
    };

    const draw = (timeMs) => {
      gl.uniform1f(uTime, timeMs * 0.001);
      gl.drawArrays(gl.TRIANGLES, 0, 6);
    };

    resize();

    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let raf = 0;
    const onResize = () => resize();
    window.addEventListener('resize', onResize, { passive: true });

    if (reduce) {
      draw(0); // single static frame
    } else {
      const tick = (t) => {
        draw(t);
        raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    }

    return () => {
      window.removeEventListener('resize', onResize);
      if (raf) cancelAnimationFrame(raf);
      gl.deleteBuffer(buf);
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
