/**
 * Space around the globe: a starfield with a Milky Way band, Earth's Moon, and the Sun as an
 * off-screen light (no sprite, no planets). It's decoration you can't fly to: the camera stops
 * at a comfortable whole-Earth view (MAX_DISTANCE). Everything is procedural (no textures to
 * credit or download).
 *
 * Stars and the light are in the globe's frame (Earth radius 1) and turn with it, so the Sun
 * stays over today's real subsolar point and the night side is where it really is. The Moon
 * sits in view space, above and to the right of Earth, so it peeks out as you zoom out.
 *
 * Budget: stars are one Points draw, the Moon one low-poly sphere; no post-processing.
 */
import * as THREE from 'three';

/** Furthest the camera may pull back: the whole Earth with room around it. */
export const MAX_DISTANCE = 7;
const STAR_RADIUS = 60;
const SUN_DISTANCE = 42;

/** Sub-solar point (where the Sun is overhead) for a date: [lat, lon] in degrees. */
export function subsolarPoint(d: Date): [number, number] {
  const start = Date.UTC(d.getUTCFullYear(), 0, 0);
  const day = (d.getTime() - start) / 86_400_000;
  const lat = 23.44 * Math.sin(((2 * Math.PI) / 365) * (day - 81));
  const hours = d.getUTCHours() + d.getUTCMinutes() / 60;
  let lon = -(hours - 12) * 15;
  if (lon < -180) lon += 360;
  return [lat, lon];
}

function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

function glowTexture(inner: string, outer: string): THREE.CanvasTexture {
  const c = document.createElement('canvas');
  c.width = c.height = 128;
  const g = c.getContext('2d')!;
  const grad = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  grad.addColorStop(0, inner);
  grad.addColorStop(0.18, inner);
  grad.addColorStop(0.35, outer);
  grad.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = grad;
  g.fillRect(0, 0, 128, 128);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

/** A small procedural surface: base colour with soft blotches (craters, storms, bands). */
function surfaceTexture(base: string, spots: string, seed: number, banded = false) {
  const c = document.createElement('canvas');
  c.width = 128;
  c.height = 64;
  const g = c.getContext('2d')!;
  g.fillStyle = base;
  g.fillRect(0, 0, 128, 64);
  const r = rng(seed);
  if (banded) {
    for (let y = 0; y < 64; y += 3 + Math.floor(r() * 5)) {
      g.globalAlpha = 0.15 + r() * 0.25;
      g.fillStyle = spots;
      g.fillRect(0, y, 128, 1 + r() * 3);
    }
  } else {
    for (let i = 0; i < 70; i++) {
      g.globalAlpha = 0.08 + r() * 0.22;
      g.fillStyle = spots;
      g.beginPath();
      g.arc(r() * 128, r() * 64, 1 + r() * 7, 0, Math.PI * 2);
      g.fill();
    }
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

export interface Space {
  /** Stars and the Sun's light: add to the globe so they turn with it. */
  group: THREE.Group;
  /** Earth's Moon: add to the scene (view space). */
  moon: THREE.Mesh;
  /** Advance twinkle by dt seconds (pass 0 under reduced motion). */
  tick: (dt: number) => void;
  dispose: () => void;
}

export function buildSpace(sunDir: THREE.Vector3): Space {
  const group = new THREE.Group();
  const disposables: { dispose: () => void }[] = [];
  const keep = <T extends { dispose: () => void }>(x: T) => (disposables.push(x), x);
  const r = rng(7);

  // ---- stars: one Points draw, denser along a Milky Way band
  const N = 7000;
  const pos = new Float32Array(N * 3);
  const col = new Float32Array(N * 3);
  const size = new Float32Array(N);
  const phase = new Float32Array(N);
  const band = new THREE.Vector3(0.3, 0.85, 0.42).normalize(); // galactic pole, artistic
  const tmp = new THREE.Vector3();
  for (let i = 0; i < N; i++) {
    const inBand = i < N * 0.45;
    for (;;) {
      tmp.set(r() * 2 - 1, r() * 2 - 1, r() * 2 - 1);
      const l = tmp.length();
      if (l < 0.05 || l > 1) continue;
      tmp.divideScalar(l);
      if (inBand) {
        // squash toward the galactic plane
        tmp.sub(band.clone().multiplyScalar(tmp.dot(band) * (0.82 + r() * 0.17))).normalize();
      }
      break;
    }
    tmp.multiplyScalar(STAR_RADIUS);
    pos.set([tmp.x, tmp.y, tmp.z], i * 3);
    const t = r();
    const c = t < 0.12 ? [0.7, 0.8, 1] : t > 0.9 ? [1, 0.85, 0.7] : [1, 1, 1];
    const b = inBand ? 0.35 + r() * 0.4 : 0.5 + r() * 0.5;
    col.set([c[0]! * b, c[1]! * b, c[2]! * b], i * 3);
    size[i] = inBand ? 0.8 + r() * 1.2 : 1 + r() ** 3 * 2.6;
    phase[i] = r() * Math.PI * 2;
  }
  const starGeo = keep(new THREE.BufferGeometry());
  starGeo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  starGeo.setAttribute('color', new THREE.BufferAttribute(col, 3));
  starGeo.setAttribute('size', new THREE.BufferAttribute(size, 1));
  starGeo.setAttribute('phase', new THREE.BufferAttribute(phase, 1));
  const starMat = keep(
    new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      uniforms: { time: { value: 0 }, pixelRatio: { value: Math.min(window.devicePixelRatio, 2) } },
      vertexShader: `attribute float size; attribute float phase; attribute vec3 color;
        uniform float time; uniform float pixelRatio; varying vec3 vC; varying float vA;
        void main(){ vC = color; vA = 0.75 + 0.25 * sin(time * (0.6 + fract(phase) * 1.4) + phase * 7.0);
          vec4 mv = modelViewMatrix * vec4(position, 1.0); gl_Position = projectionMatrix * mv;
          gl_PointSize = size * pixelRatio; }`,
      fragmentShader: `varying vec3 vC; varying float vA; void main(){
        float d = length(gl_PointCoord - 0.5); if (d > 0.5) discard;
        gl_FragColor = vec4(vC, vA * smoothstep(0.5, 0.0, d)); }`,
    }),
  );
  const stars = new THREE.Points(starGeo, starMat);
  stars.frustumCulled = false;
  group.add(stars);

  // ---- Milky Way haze: a faint band of large soft points (still cheap)
  const H = 500;
  const hpos = new Float32Array(H * 3);
  for (let i = 0; i < H; i++) {
    tmp.set(r() * 2 - 1, r() * 2 - 1, r() * 2 - 1).normalize();
    tmp.sub(band.clone().multiplyScalar(tmp.dot(band) * 0.96)).normalize().multiplyScalar(STAR_RADIUS * 1.02);
    hpos.set([tmp.x, tmp.y, tmp.z], i * 3);
  } // prettier-ignore
  const hazeGeo = keep(new THREE.BufferGeometry());
  hazeGeo.setAttribute('position', new THREE.BufferAttribute(hpos, 3));
  const hazeTex = keep(glowTexture('rgba(170,180,255,0.5)', 'rgba(120,130,200,0.12)'));
  const haze = new THREE.Points(
    hazeGeo,
    keep(
      new THREE.PointsMaterial({
        size: 9,
        map: hazeTex,
        transparent: true,
        opacity: 0.1,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    ),
  );
  haze.frustumCulled = false;
  group.add(haze);

  // ---- the Sun: an off-screen light that sets Earth's day and night
  const light = new THREE.DirectionalLight(0xfff4e6, 2.6);
  light.position.copy(sunDir.clone().normalize().multiplyScalar(SUN_DISTANCE));
  group.add(light);
  group.add(light.target); // target at the origin (Earth), in the same frame

  // ---- Earth's Moon, up and to the right; gently self-lit so it never goes fully dark
  const moon = new THREE.Mesh(
    keep(new THREE.SphereGeometry(1, 32, 20)),
    keep(
      new THREE.MeshLambertMaterial({
        map: keep(surfaceTexture('#b9b6b0', '#6f6c68', 3)),
        emissive: new THREE.Color(0x26282c),
      }),
    ),
  );
  // In the clear area above and right of the globe, between the floating cards.
  moon.scale.setScalar(0.2);
  moon.position.set(1.12, 1.46, -1.0);

  let time = 0;
  return {
    group,
    moon,
    tick: (dt) => {
      if (dt <= 0) return;
      time += dt;
      starMat.uniforms.time!.value = time;
      moon.rotation.y += dt * 0.02;
    },
    dispose: () => disposables.forEach((d) => d.dispose()),
  };
}
