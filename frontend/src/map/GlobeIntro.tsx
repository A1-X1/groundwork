/**
 * three.js globe intro: a dotted Earth turns to London and the camera dives in,
 * handing over to the hex map. Light: one Points cloud (~9k dots), one sphere,
 * pixel ratio capped at 2. Skipped under prefers-reduced-motion.
 */
import { Button } from '@astryxdesign/core/Button';
import { VStack } from '@astryxdesign/core/VStack';
import { geoContains } from 'd3-geo';
import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { feature } from 'topojson-client';
import type { GeometryCollection, Topology } from 'topojson-specification';
import land110 from 'world-atlas/land-110m.json';

const LONDON = { lat: 51.5, lon: -0.11 };
const DOTS = 16000;
const SPIN_MS = 1600;
const DIVE_MS = 1700;
const FADE_MS = 450;
const ACCENT = 0x76acff;

function toVec(lat: number, lon: number, r = 1): THREE.Vector3 {
  const phi = THREE.MathUtils.degToRad(90 - lat);
  const theta = THREE.MathUtils.degToRad(lon + 180);
  return new THREE.Vector3(
    -r * Math.sin(phi) * Math.cos(theta),
    r * Math.cos(phi),
    r * Math.sin(phi) * Math.sin(theta),
  );
}

let landDots: Float32Array | null = null;
function buildLandDots(): Float32Array {
  if (landDots) return landDots;
  const topo = land110 as unknown as Topology<{ land: GeometryCollection }>;
  const land = feature(topo, topo.objects.land);
  const pts: number[] = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < DOTS; i++) {
    const y = 1 - (i / (DOTS - 1)) * 2;
    const lon = THREE.MathUtils.radToDeg((golden * i) % (2 * Math.PI)) - 180;
    const lat = THREE.MathUtils.radToDeg(Math.asin(y));
    if (geoContains(land, [lon, lat])) {
      const v = toVec(lat, lon, 1.002);
      pts.push(v.x, v.y, v.z);
    }
  }
  landDots = new Float32Array(pts);
  return landDots;
}

const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);

export function GlobeIntro({ onDone }: { onDone: () => void }) {
  const hostRef = useRef<HTMLElement | null>(null);
  const [fading, setFading] = useState(false);
  const doneRef = useRef(false);

  const finish = () => {
    if (doneRef.current) return;
    doneRef.current = true;
    setFading(true);
    window.setTimeout(onDone, FADE_MS);
  };

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      onDone();
      return;
    }
    const width = host.clientWidth || 800;
    const height = host.clientHeight || 600;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height);
    host.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(35, width / height, 0.001, 100);

    const globe = new THREE.Group();
    scene.add(globe);
    globe.add(
      new THREE.Mesh(
        new THREE.SphereGeometry(1, 64, 48),
        new THREE.MeshBasicMaterial({ color: 0x0d1117 }),
      ),
    );
    const dots = new THREE.BufferGeometry();
    dots.setAttribute('position', new THREE.BufferAttribute(buildLandDots(), 3));
    globe.add(
      new THREE.Points(
        dots,
        new THREE.PointsMaterial({ color: 0x8a94a3, size: 0.009, sizeAttenuation: true }),
      ),
    );
    // Atmosphere rim: a slightly larger back-face sphere, very faint.
    globe.add(
      new THREE.Mesh(
        new THREE.SphereGeometry(1.035, 48, 32),
        new THREE.MeshBasicMaterial({
          color: ACCENT,
          transparent: true,
          opacity: 0.07,
          side: THREE.BackSide,
        }),
      ),
    );
    // London: a small hex of accent dots, echoing the grid it opens onto.
    const london = toVec(LONDON.lat, LONDON.lon, 1.004);
    const marker = new THREE.Mesh(
      new THREE.CircleGeometry(0.018, 6),
      new THREE.MeshBasicMaterial({ color: ACCENT }),
    );
    marker.position.copy(london);
    marker.lookAt(london.clone().multiplyScalar(2));
    globe.add(marker);
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(0.03, 0.034, 6),
      new THREE.MeshBasicMaterial({ color: ACCENT, transparent: true, opacity: 0.8 }),
    );
    ring.position.copy(london);
    ring.lookAt(london.clone().multiplyScalar(2));
    globe.add(ring);

    // Start turned away from London; spin so London faces the camera (+z).
    const target = new THREE.Quaternion().setFromUnitVectors(
      london.clone().normalize(),
      new THREE.Vector3(0, 0, 1),
    );
    const start = new THREE.Quaternion()
      .setFromAxisAngle(new THREE.Vector3(0, 1, 0), -1.6)
      .multiply(target);
    const camFar = new THREE.Vector3(0, 0, 4.2);
    const camNear = new THREE.Vector3(0, 0, 1.06);

    const t0 = performance.now();
    let raf = 0;
    const tick = () => {
      const t = performance.now() - t0;
      const spin = Math.min(1, t / SPIN_MS);
      globe.quaternion.slerpQuaternions(start, target, ease(spin));
      const dive = Math.min(1, Math.max(0, (t - SPIN_MS * 0.7) / DIVE_MS));
      camera.position.lerpVectors(camFar, camNear, ease(dive));
      camera.lookAt(0, 0, 0);
      const pulse = 1 + 0.25 * Math.sin(t / 180);
      ring.scale.setScalar(pulse);
      renderer.render(scene, camera);
      if (dive >= 1) finish();
      else raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    const onResize = () => {
      const w = host.clientWidth;
      const h = host.clientHeight;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    window.addEventListener('resize', onResize);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', onResize);
      renderer.dispose();
      dots.dispose();
      renderer.domElement.remove();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <VStack
      ref={hostRef}
      style={{
        position: 'absolute',
        inset: 0,
        zIndex: 2,
        background: 'var(--color-background-body)',
        opacity: fading ? 0 : 1,
        transition: `opacity ${FADE_MS}ms ease`,
        pointerEvents: fading ? 'none' : 'auto',
      }}
      aria-label="Globe turning to London"
      role="img"
    >
      <VStack
        padding={4}
        style={{ position: 'absolute', insetBlockEnd: 0, insetInlineEnd: 0, zIndex: 3 }}
      >
        <Button label="Skip intro" variant="ghost" size="sm" onClick={finish} />
      </VStack>
    </VStack>
  );
}
