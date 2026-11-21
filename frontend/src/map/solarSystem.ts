/**
 * The solar-system view, shown when the globe is zoomed far out (user request).
 *
 *   distance ≲ 6     Earth in space (the backdrop in space.ts)
 *   6 → 30           the planets grow in, lined up in a row: Sun, Mercury … Neptune, with
 *                    Earth (the real globe, at the origin) in its place
 *   60 → 110         they swing onto orbits around the Sun and the camera tilts to look down
 *
 * Earth never moves: its orbit is drawn through the origin. Scales and distances are
 * artistic, not physical. Turned off with "remove solar system" (TOGGLE_SOLAR_SYSTEM).
 * Lives in scene space (not the globe's frame), so the row stays level on screen.
 */
import * as THREE from 'three';

export const SYSTEM_FAR = 140;
const LINE = [6, 30] as const; // distance range over which the row appears
const ORBIT = [60, 110] as const; // distance range over which the row becomes orbits
const ORBIT_TILT = THREE.MathUtils.degToRad(62);

const SUN_X = -16;
const BODIES = [
  { name: 'Mercury', r: 0.38, x: -9.5, color: '#9c968f', speed: 0.21, start: 2.1 },
  { name: 'Venus', r: 0.9, x: -6.5, color: '#d9c28f', speed: 0.12, start: 4.4 },
  { name: 'Earth', r: 1, x: 0, color: '', speed: 0, start: 0 },
  { name: 'Mars', r: 0.55, x: 3.2, color: '#b5562f', speed: 0.06, start: 1.2 },
  { name: 'Jupiter', r: 2.4, x: 8.5, color: '#c9a77e', speed: 0.03, start: 3.6 },
  { name: 'Saturn', r: 2.0, x: 15, color: '#d8c18f', speed: 0.02, start: 5.4, ring: true },
  { name: 'Uranus', r: 1.3, x: 21, color: '#9fd3da', speed: 0.014, start: 0.8 },
  { name: 'Neptune', r: 1.25, x: 26, color: '#4b6fd1', speed: 0.011, start: 2.9 },
]; // prettier-ignore

const smooth = (a: number, b: number, x: number) => {
  const t = THREE.MathUtils.clamp((x - a) / (b - a), 0, 1);
  return t * t * (3 - 2 * t);
};

function label(text: string): THREE.Sprite {
  const c = document.createElement('canvas');
  c.width = 256;
  c.height = 64;
  const g = c.getContext('2d')!;
  g.font = '500 30px Inter, system-ui, sans-serif';
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.fillStyle = 'rgba(230,236,245,0.92)';
  g.fillText(text, 128, 32);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const s = new THREE.Sprite(
    new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false, sizeAttenuation: false }),
  ); // prettier-ignore
  s.scale.set(0.1, 0.025, 1);
  s.center.set(0.5, 0);
  return s;
}

export interface SolarView {
  /** 0 → 1 as the row appears. */
  line: number;
  /** 0 → 1 as the row becomes orbits. */
  orbit: number;
}

export interface SolarSystem {
  group: THREE.Group;
  /** Lay out bodies and place the camera for a distance; returns the mix used. */
  update: (distance: number, camera: THREE.PerspectiveCamera, dt: number) => SolarView;
  dispose: () => void;
}

export function buildSolarSystem(): SolarSystem {
  const group = new THREE.Group();
  const disposables: { dispose: () => void }[] = [];
  const keep = <T extends { dispose: () => void }>(x: T) => (disposables.push(x), x);
  const sunPos = new THREE.Vector3(SUN_X, 0, 0);

  // ---- the Sun: a bright sphere with a soft glow, and the light for the planets (and Earth)
  const sun = new THREE.Mesh(
    keep(new THREE.SphereGeometry(4.2, 40, 28)),
    keep(new THREE.MeshBasicMaterial({ color: 0xffd58a })),
  );
  sun.position.copy(sunPos);
  group.add(sun);
  const glowCanvas = document.createElement('canvas');
  glowCanvas.width = glowCanvas.height = 128;
  const gg = glowCanvas.getContext('2d')!;
  const grad = gg.createRadialGradient(64, 64, 20, 64, 64, 64);
  grad.addColorStop(0, 'rgba(255,214,140,0.65)');
  grad.addColorStop(1, 'rgba(255,170,80,0)');
  gg.fillStyle = grad;
  gg.fillRect(0, 0, 128, 128);
  const glowTex = keep(new THREE.CanvasTexture(glowCanvas));
  const glowMat = keep(
    new THREE.SpriteMaterial({
      map: glowTex,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    }),
  );
  const glow = new THREE.Sprite(glowMat);
  glow.scale.setScalar(16);
  sun.add(glow);
  const light = new THREE.PointLight(0xfff1dd, 0, 0, 0);
  light.position.copy(sunPos);
  group.add(light);
  const sunLabel = label('Sun');
  sunLabel.center.set(0.5, 1); // below the Sun, clear of Mercury's label
  sunLabel.position.set(0, -4.9, 0);
  sun.add(sunLabel);

  // ---- planets (Earth is the real globe at the origin: only its label and orbit are here)
  const geo = keep(new THREE.SphereGeometry(1, 32, 20));
  const bodies = BODIES.map((b) => {
    let mesh: THREE.Object3D;
    if (b.name === 'Earth') {
      mesh = new THREE.Object3D();
    } else {
      const m = new THREE.Mesh(geo, keep(new THREE.MeshLambertMaterial({ color: b.color })));
      if (b.ring) {
        const ring = new THREE.Mesh(
          keep(new THREE.RingGeometry(1.35, 2.25, 56)),
          keep(new THREE.MeshBasicMaterial({ color: 0xcdb68a, transparent: true, opacity: 0.6, side: THREE.DoubleSide })),
        ); // prettier-ignore
        ring.rotation.x = Math.PI / 2.3;
        m.add(ring);
      }
      mesh = m;
    }
    const tag = label(b.name);
    group.add(mesh);
    group.add(tag);
    const orbitR = b.x - SUN_X;
    const pts = Array.from({ length: 129 }, (_, i) => {
      const a = (i / 128) * Math.PI * 2;
      return new THREE.Vector3(SUN_X + Math.cos(a) * orbitR, 0, -Math.sin(a) * orbitR);
    });
    const orbitMat = keep(
      new THREE.LineBasicMaterial({ color: 0x9fb6d8, transparent: true, opacity: 0 }),
    );
    const orbit = new THREE.Line(keep(new THREE.BufferGeometry().setFromPoints(pts)), orbitMat);
    group.add(orbit);
    return { ...b, mesh, tag, orbitR, orbitMat, angle: b.start };
  });

  const target = new THREE.Vector3();
  // a little left of the row's middle, so the Sun clears the Controls panel
  const lineCentre = new THREE.Vector3((SUN_X + 26) / 2 - 3, 0, 0);
  const pos = new THREE.Vector3();
  const linePos = new THREE.Vector3();
  const orbitPos = new THREE.Vector3();

  return {
    group,
    update: (distance, camera, dt) => {
      const line = smooth(LINE[0], LINE[1], distance);
      const orbit = smooth(ORBIT[0], ORBIT[1], distance);
      group.visible = line > 0.001;

      // camera: from Earth, to the middle of the row, to above the Sun
      target.set(0, 0, 0).lerp(lineCentre, line).lerp(sunPos, orbit);
      const tilt = ORBIT_TILT * orbit;
      camera.position.set(
        target.x,
        target.y + Math.sin(tilt) * distance,
        target.z + Math.cos(tilt) * distance,
      );
      camera.lookAt(target); // prettier-ignore
      if (!group.visible) return { line, orbit };

      sun.scale.setScalar(Math.max(0.001, line));
      light.intensity = 2.8 * line;
      for (const b of bodies) {
        b.angle += dt * b.speed * orbit;
        linePos.set(b.x, 0, 0);
        orbitPos.set(SUN_X + Math.cos(b.angle) * b.orbitR, 0, -Math.sin(b.angle) * b.orbitR);
        pos.copy(linePos).lerp(orbitPos, orbit);
        b.mesh.position.copy(pos);
        b.mesh.scale.setScalar(Math.max(0.001, b.r * line));
        b.mesh.rotation.y += dt * 0.2;
        b.tag.position.set(pos.x, pos.y + b.r * line + 0.4, pos.z);
        (b.tag.material as THREE.SpriteMaterial).opacity = line;
        b.orbitMat.opacity = 0.35 * orbit;
      }
      (sunLabel.material as THREE.SpriteMaterial).opacity = line;
      return { line, orbit };
    },
    dispose: () => {
      disposables.forEach((d) => d.dispose());
      group.traverse((o) => {
        if (o instanceof THREE.Sprite) {
          o.material.map?.dispose();
          o.material.dispose();
        }
      });
    },
  };
}
