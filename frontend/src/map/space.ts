/**
 * Space around the globe: a starfield with a Milky Way band, the Sun (glow sprite and the
 * scene's light), the Moon, and the other planets far behind, to artistic rather than
 * physical scale. Everything is procedural (no textures to credit or download).
 *
 * Coordinates are in the globe's frame (Earth radius 1). The group turns with the globe,
 * so the Sun stays over today's real subsolar point and the night side is where it
 * really is.
 *
 * Budget: stars are one Points draw; planets are low-poly spheres; no post-processing.
 */
import * as THREE from 'three';

export const SPACE_FAR = 14; // furthest the camera may pull back
const STAR_RADIUS = 400; // well beyond the solar-system view's camera
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

const PLANETS = [
  { name: 'Mercury', r: 0.12, dist: 30, angle: 0.4, base: '#9c968f', spot: '#5e5954' },
  { name: 'Venus', r: 0.22, dist: 24, angle: 2.2, base: '#d9c28f', spot: '#b89a5e', banded: true },
  { name: 'Mars', r: 0.16, dist: 20, angle: 4.1, base: '#b5562f', spot: '#7a3218' },
  { name: 'Jupiter', r: 0.9, dist: 36, angle: 5.3, base: '#c9a77e', spot: '#8f6a48', banded: true },
  { name: 'Saturn', r: 0.75, dist: 40, angle: 3.2, base: '#d8c18f', spot: '#a68a5c', banded: true, ring: true },
  { name: 'Uranus', r: 0.4, dist: 44, angle: 1.3, base: '#9fd3da', spot: '#7cb4bd', banded: true },
  { name: 'Neptune', r: 0.38, dist: 47, angle: 6.0, base: '#4b6fd1', spot: '#2f4ba0', banded: true },
]; // prettier-ignore

export interface Space {
  group: THREE.Group;
  /** Advance twinkle and orbits by dt seconds (pass 0 under reduced motion). */
  tick: (dt: number) => void;
  /** 0–1 as the solar-system view takes over: the backdrop Sun, Moon and planets fade out. */
  setSystemMix: (mix: number) => void;
  dispose: () => void;
}

export function buildSpace(sunDir: THREE.Vector3): Space {
  const group = new THREE.Group();
  const disposables: { dispose: () => void }[] = [];
  const keep = <T extends { dispose: () => void }>(x: T) => (disposables.push(x), x);
  const r = rng(7);

  // ---- ecliptic plane (tilted 23.44° from the equator), shared by the Sun, Moon and planets
  const sun = sunDir.clone().normalize();
  const tilt = new THREE.Quaternion().setFromAxisAngle(
    new THREE.Vector3(1, 0, 0),
    THREE.MathUtils.degToRad(23.44),
  );
  const normal = new THREE.Vector3(0, 1, 0).applyQuaternion(tilt);
  const u = sun
    .clone()
    .sub(normal.clone().multiplyScalar(sun.dot(normal)))
    .normalize();
  const v = new THREE.Vector3().crossVectors(normal, u).normalize();
  const onEcliptic = (dist: number, angle: number, lift = 0) =>
    u.clone().multiplyScalar(Math.cos(angle) * dist)
      .add(v.clone().multiplyScalar(Math.sin(angle) * dist))
      .add(normal.clone().multiplyScalar(lift)); // prettier-ignore

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
        size: 60,
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

  // ---- the Sun: a glow sprite, and the light that sets Earth's day and night
  const sunPos = sun.clone().multiplyScalar(SUN_DISTANCE);
  const sunSprite = new THREE.Sprite(
    keep(
      new THREE.SpriteMaterial({
        map: keep(glowTexture('rgba(255,250,235,1)', 'rgba(255,190,90,0.35)')),
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      }),
    ),
  );
  sunSprite.position.copy(sunPos);
  sunSprite.scale.setScalar(16);
  group.add(sunSprite);
  const light = new THREE.DirectionalLight(0xfff4e6, 2.6);
  light.position.copy(sunPos);
  group.add(light);
  group.add(light.target); // target at the origin (Earth), in the same frame

  const lowPoly = keep(new THREE.SphereGeometry(1, 32, 20));

  // ---- the Moon
  const moonMat = keep(
    new THREE.MeshLambertMaterial({ map: keep(surfaceTexture('#b9b6b0', '#6f6c68', 3)) }),
  );
  const moon = new THREE.Mesh(lowPoly, moonMat);
  moon.scale.setScalar(0.27);
  group.add(moon);
  let moonAngle = 2.4;
  const placeMoon = () => moon.position.copy(onEcliptic(3.6, moonAngle, 0.35));
  placeMoon();

  // ---- planets on rough orbits in the far background
  const planets = PLANETS.map((p, i) => {
    const mat = keep(
      new THREE.MeshLambertMaterial({
        map: keep(surfaceTexture(p.base, p.spot, 11 + i, p.banded)),
      }),
    );
    const mesh = new THREE.Mesh(lowPoly, mat);
    mesh.scale.setScalar(p.r);
    mesh.position.copy(onEcliptic(p.dist, p.angle, (i % 3) - 1));
    if (p.ring) {
      const ring = new THREE.Mesh(
        keep(new THREE.RingGeometry(1.35, 2.2, 48)),
        keep(
          new THREE.MeshBasicMaterial({
            color: 0xcdb68a,
            transparent: true,
            opacity: 0.55,
            side: THREE.DoubleSide,
          }),
        ),
      );
      ring.rotation.x = Math.PI / 2.4;
      mesh.add(ring);
    }
    group.add(mesh);
    return { mesh, ...p, speed: 0.02 / Math.sqrt(p.dist / 20) };
  });

  let time = 0;
  return {
    group,
    tick: (dt) => {
      if (dt <= 0) return;
      time += dt;
      starMat.uniforms.time!.value = time;
      moonAngle += dt * 0.01;
      placeMoon();
      for (const p of planets) {
        p.angle += dt * p.speed * 0.05;
        p.mesh.position.copy(onEcliptic(p.dist, p.angle, p.mesh.position.dot(normal)));
        p.mesh.rotation.y += dt * 0.1;
      }
    },
    setSystemMix: (mix) => {
      (sunSprite.material as THREE.SpriteMaterial).opacity = 1 - mix;
      light.intensity = 2.6 * (1 - mix);
      moon.visible = mix < 0.5;
      for (const p of planets) p.mesh.visible = mix < 0.5;
    },
    dispose: () => disposables.forEach((d) => d.dispose()),
  };
}
