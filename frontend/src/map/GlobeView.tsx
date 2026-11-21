/**
 * The world as a textured three.js globe. It starts zoomed out and spinning slowly; drag to turn
 * it. A global H3 grid (res 2) is drawn faintly, and regions with detailed data show coarse
 * (res 5) hexes coloured by score. `flyTo` turns the globe to a place and dives in; where
 * detailed hexes exist it hands over to the map.
 *
 * Kept light: one 2k texture, one sphere, two line/mesh batches, pixel ratio capped at 2.
 */
import { Button } from '@astryxdesign/core/Button';
import { Text } from '@astryxdesign/core/Text';
import { VStack } from '@astryxdesign/core/VStack';
import { cellToBoundary, cellToChildren, getRes0Cells } from 'h3-js';
import { buildSpace, MAX_DISTANCE, subsolarPoint } from './space';
import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { RAMPS, sample } from '../lib/colour';

export interface GlobeTarget {
  lat: number;
  lon: number;
  /** How close to end up: the whole Earth, a country, or city level (then hand over). */
  level: 'world' | 'country' | 'city';
  /** 'near': start close in over the target and pull back (hand-back from the map). */
  from?: 'near';
  nonce: number;
}

export interface RegionHex {
  h3: string;
  t: number;
}

interface Props {
  isVisible: boolean;
  isSpinning: boolean;
  target: GlobeTarget | null;
  zoom: { dir: 'in' | 'out'; nonce: number } | null;
  regionHexes: RegionHex[];
  notice: string | null;
  onArrive: (target: GlobeTarget) => void;
  /** Click on a data region (with the clicked point), or the enter button (no point). */
  onEnterRegion: (at?: [number, number]) => void;
  /** Wheel-zoomed all the way in: the point facing the camera, for the map hand-over. */
  onZoomIn?: (lat: number, lon: number) => void;
  enterLabel?: string;
  onUserInteract: () => void;
}

const FAR = 3.3;
const COUNTRY = 1.9;
const NEAR = 1.18;
const FLY_MS = 1600;
const FADE_MS = 450;
const ACCENT = new THREE.Color(0x76acff);

function toVec(lat: number, lon: number, r = 1): THREE.Vector3 {
  const phi = THREE.MathUtils.degToRad(90 - lat);
  const theta = THREE.MathUtils.degToRad(lon + 180);
  return new THREE.Vector3(
    -r * Math.sin(phi) * Math.cos(theta),
    r * Math.cos(phi),
    r * Math.sin(phi) * Math.sin(theta),
  );
}

/** Inverse of toVec: latitude and longitude of a direction in globe space. */
function toLatLon(v: THREE.Vector3): [number, number] {
  const u = v.clone().normalize();
  const lat = 90 - THREE.MathUtils.radToDeg(Math.acos(THREE.MathUtils.clamp(u.y, -1, 1)));
  let lon = THREE.MathUtils.radToDeg(Math.atan2(u.z, -u.x)) - 180;
  if (lon < -180) lon += 360;
  return [lat, lon];
}

/** Rotation that brings (lat, lon) to face the camera (+z) with north up. */
function facing(lat: number, lon: number): THREE.Quaternion {
  const yaw = Math.PI / 2 - THREE.MathUtils.degToRad(lon + 180);
  const qy = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), yaw);
  const qx = new THREE.Quaternion().setFromAxisAngle(
    new THREE.Vector3(1, 0, 0),
    THREE.MathUtils.degToRad(lat),
  );
  return qx.multiply(qy);
}

let globalGrid: Float32Array | null = null;
function buildGlobalGrid(): Float32Array {
  if (globalGrid) return globalGrid;
  const pts: number[] = [];
  for (const r0 of getRes0Cells()) {
    for (const c of cellToChildren(r0, 2)) {
      const ring = cellToBoundary(c);
      for (let i = 0; i < ring.length; i++) {
        const [a1, o1] = ring[i]!;
        const [a2, o2] = ring[(i + 1) % ring.length]!;
        const v1 = toVec(a1, o1, 1.002);
        const v2 = toVec(a2, o2, 1.002);
        pts.push(v1.x, v1.y, v1.z, v2.x, v2.y, v2.z);
      }
    }
  }
  globalGrid = new Float32Array(pts);
  return globalGrid;
}

function buildRegionMesh(hexes: RegionHex[]): THREE.BufferGeometry {
  const pos: number[] = [];
  const col: number[] = [];
  const ramp = RAMPS.suitability;
  for (const h of hexes) {
    const ring = cellToBoundary(h.h3);
    const [lat, lon] = ring.reduce(
      ([a, b], [x, y]) => [a + x / ring.length, b + y / ring.length],
      [0, 0],
    );
    const c = toVec(lat, lon, 1.004);
    const [r, g, b] = sample(ramp, h.t).map((v) => v / 255) as [number, number, number];
    for (let i = 0; i < ring.length; i++) {
      const [a1, o1] = ring[i]!;
      const [a2, o2] = ring[(i + 1) % ring.length]!;
      // shrink slightly towards the centre so hexes read as separate tiles
      const v1 = toVec(a1, o1, 1.004).lerp(c, 0.08);
      const v2 = toVec(a2, o2, 1.004).lerp(c, 0.08);
      pos.push(c.x, c.y, c.z, v1.x, v1.y, v1.z, v2.x, v2.y, v2.z);
      for (let k = 0; k < 3; k++) col.push(r, g, b);
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
  return geo;
}

const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);

interface Anim {
  fromQ: THREE.Quaternion;
  toQ: THREE.Quaternion;
  fromD: number;
  toD: number;
  t0: number;
  ms: number;
  done?: () => void;
}

export function GlobeView(props: Props) {
  const hostRef = useRef<HTMLElement | null>(null);
  const propsRef = useRef(props);
  propsRef.current = props;
  const api = useRef<{
    fly: (q: THREE.Quaternion, d: number, ms: number, done?: () => void) => void;
    zoomTo: (d: number) => void;
    jump: (q: THREE.Quaternion, d: number) => void;
    setRegion: (hexes: RegionHex[]) => void;
    distance: () => number;
    redraw: () => void;
  } | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(host.clientWidth || 800, host.clientHeight || 600);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.domElement.style.display = 'block';
    renderer.domElement.style.touchAction = 'none';
    host.prepend(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(
      35,
      (host.clientWidth || 800) / (host.clientHeight || 600),
      0.01,
      1200,
    );
    let distance = FAR;
    camera.position.set(0, 0, distance);

    scene.background = new THREE.Color(0x02030a);
    // Low ambient so the night side reads as night but stays legible; the Sun does the rest.
    scene.add(new THREE.AmbientLight(0xc8d4ff, 0.42));

    const globe = new THREE.Group();
    scene.add(globe);
    // Space turns with the globe, so the Sun stays over today's real subsolar point.
    const space = buildSpace(toVec(...subsolarPoint(new Date())));
    globe.add(space.group);
    // The Moon sits in view space (decoration you can't fly to), up and to the right of Earth.
    scene.add(space.moon);
    let lastFrame = performance.now();
    const loader = new THREE.TextureLoader();
    const day = loader.load('/textures/earth-blue-marble-2k.jpg', () => renderOnce());
    day.colorSpace = THREE.SRGBColorSpace;
    day.anisotropy = Math.min(4, renderer.capabilities.getMaxAnisotropy());
    const bump = loader.load('/textures/earth-bump-1k.png', () => renderOnce());
    const earthGeo = new THREE.SphereGeometry(1, 96, 64);
    const earthMat = new THREE.MeshPhongMaterial({
      map: day,
      bumpMap: bump,
      bumpScale: 0.6,
      shininess: 6,
      specular: new THREE.Color(0x111418),
      color: 0x9aa3ad, // dim the imagery so the UI and hexes stay the focus
    });
    globe.add(new THREE.Mesh(earthGeo, earthMat));

    // Subtle atmosphere rim (fresnel on a back-facing shell).
    const rimMat = new THREE.ShaderMaterial({
      transparent: true,
      side: THREE.BackSide,
      depthWrite: false,
      uniforms: { color: { value: ACCENT } },
      vertexShader: `varying vec3 vN; void main(){ vN = normalize(normalMatrix * normal);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
      fragmentShader: `uniform vec3 color; varying vec3 vN; void main(){
        float i = pow(0.62 - dot(vN, vec3(0.0,0.0,1.0)), 3.0);
        gl_FragColor = vec4(color, clamp(i, 0.0, 1.0) * 0.55); }`,
    });
    scene.add(new THREE.Mesh(new THREE.SphereGeometry(1.06, 64, 48), rimMat));

    const gridGeo = new THREE.BufferGeometry();
    gridGeo.setAttribute('position', new THREE.BufferAttribute(buildGlobalGrid(), 3));
    const grid = new THREE.LineSegments(
      gridGeo,
      new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.07 }),
    );
    globe.add(grid);

    let region: THREE.Mesh | null = null;
    const setRegion = (hexes: RegionHex[]) => {
      if (region) {
        globe.remove(region);
        region.geometry.dispose();
      }
      if (!hexes.length) return;
      region = new THREE.Mesh(
        buildRegionMesh(hexes),
        new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide }),
      );
      globe.add(region);
      renderOnce();
    };

    // ---- interaction: drag to turn, wheel to zoom, click region to enter
    let dragging = false;
    let moved = 0;
    let last = { x: 0, y: 0 };
    const raycaster = new THREE.Raycaster();
    const onDown = (e: PointerEvent) => {
      dragging = true;
      moved = 0;
      last = { x: e.clientX, y: e.clientY };
      renderer.domElement.setPointerCapture(e.pointerId);
      anim = null;
      propsRef.current.onUserInteract();
    };
    const onMove = (e: PointerEvent) => {
      if (!dragging) return;
      const dx = e.clientX - last.x;
      const dy = e.clientY - last.y;
      moved += Math.abs(dx) + Math.abs(dy);
      last = { x: e.clientX, y: e.clientY };
      const k = 0.005 * Math.min(distance - 0.9, 2.6);
      const qy = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), dx * k);
      const qx = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), dy * k);
      globe.quaternion.premultiply(qy).premultiply(qx);
      renderOnce();
    };
    const onUp = (e: PointerEvent) => {
      dragging = false;
      if (moved > 6 || !region) return;
      const rect = renderer.domElement.getBoundingClientRect();
      const ndc = new THREE.Vector2(
        ((e.clientX - rect.left) / rect.width) * 2 - 1,
        -((e.clientY - rect.top) / rect.height) * 2 + 1,
      );
      raycaster.setFromCamera(ndc, camera);
      const hit = raycaster.intersectObject(region)[0];
      if (hit) propsRef.current.onEnterRegion(toLatLon(globe.worldToLocal(hit.point.clone())));
    };
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      anim = null;
      const before = distance;
      distance = THREE.MathUtils.clamp(distance * (1 + e.deltaY * 0.001), NEAR, MAX_DISTANCE);
      propsRef.current.onUserInteract();
      // Reaching the closest distance hands over to the flat map at the point facing us.
      if (
        e.deltaY < 0 &&
        distance <= NEAR + 1e-6 &&
        before > NEAR + 1e-6 &&
        propsRef.current.isVisible
      ) {
        const front = new THREE.Vector3(0, 0, 1).applyQuaternion(globe.quaternion.clone().invert());
        const [lat, lon] = toLatLon(front);
        propsRef.current.onZoomIn?.(lat, lon);
      }
      renderOnce();
    };
    const el = renderer.domElement;
    el.addEventListener('pointerdown', onDown);
    el.addEventListener('pointermove', onMove);
    el.addEventListener('pointerup', onUp);
    el.addEventListener('wheel', onWheel, { passive: false });

    // ---- animation loop (only runs while something moves)
    let anim: Anim | null = null;
    let raf = 0;
    let running = false;
    const frame = () => {
      raf = 0;
      const p = propsRef.current;
      let again = false;
      if (anim) {
        const t = Math.min(1, (performance.now() - anim.t0) / anim.ms);
        globe.quaternion.slerpQuaternions(anim.fromQ, anim.toQ, ease(t));
        distance = THREE.MathUtils.lerp(anim.fromD, anim.toD, ease(t));
        if (t >= 1) {
          const done = anim.done;
          anim = null;
          done?.();
        } else again = true;
      } else if (p.isSpinning && p.isVisible && !dragging && !reduced) {
        globe.rotateOnWorldAxis(new THREE.Vector3(0, 1, 0), 0.0012);
        again = true;
      }
      // Twinkle and orbits advance only while frames run continuously (no jumps when idle).
      const now = performance.now();
      const dt = reduced ? 0 : Math.min((now - lastFrame) / 1000, 1 / 30);
      space.tick(dt);
      lastFrame = now;
      camera.position.set(0, 0, distance);
      camera.lookAt(0, 0, 0);
      maybeLoadHiRes();
      renderer.render(scene, camera);
      running = again;
      if (again) raf = requestAnimationFrame(frame);
    };
    // Level of detail: swap in the 4K texture once the camera gets close.
    let hiResRequested = false;
    const maybeLoadHiRes = () => {
      if (hiResRequested || distance > 2.2) return;
      hiResRequested = true;
      loader.load('/textures/earth-blue-marble-4k.jpg', (hi) => {
        hi.colorSpace = THREE.SRGBColorSpace;
        hi.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
        earthMat.map = hi;
        earthMat.needsUpdate = true;
        day.dispose();
        renderOnce();
      });
    };
    const renderOnce = () => {
      if (!raf) raf = requestAnimationFrame(frame);
    };
    const kick = () => {
      if (!running) renderOnce();
    };

    api.current = {
      fly: (q, d, ms, done) => {
        anim = {
          fromQ: globe.quaternion.clone(),
          toQ: q,
          fromD: distance,
          toD: d,
          t0: performance.now(),
          ms: reduced ? 1 : ms,
          done,
        };
        kick();
      },
      zoomTo: (d) => {
        const q = globe.quaternion.clone();
        anim = { fromQ: q, toQ: q, fromD: distance, toD: d, t0: performance.now(), ms: 450 };
        kick();
      },
      jump: (q, d) => {
        anim = null;
        globe.quaternion.copy(q);
        distance = d;
        renderOnce();
      },
      setRegion,
      distance: () => distance,
      redraw: kick,
    };
    // Start with Europe/Africa in view, slightly tilted.
    globe.quaternion.copy(facing(25, 10));
    renderOnce();
    const spinTimer = window.setInterval(kick, 500);

    const onResize = () => {
      const w = host.clientWidth;
      const h = host.clientHeight;
      if (!w || !h) return;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderOnce();
    };
    const ro = new ResizeObserver(onResize);
    ro.observe(host);
    return () => {
      window.clearInterval(spinTimer);
      if (raf) cancelAnimationFrame(raf);
      ro.disconnect();
      el.removeEventListener('pointerdown', onDown);
      el.removeEventListener('pointermove', onMove);
      el.removeEventListener('pointerup', onUp);
      el.removeEventListener('wheel', onWheel);
      earthGeo.dispose();
      space.dispose();
      gridGeo.dispose();
      day.dispose();
      bump.dispose();
      renderer.dispose();
      el.remove();
      api.current = null;
    };
  }, []);

  useEffect(() => {
    api.current?.setRegion(props.regionHexes);
  }, [props.regionHexes]);

  useEffect(() => {
    const t = props.target;
    if (!t || !api.current) return;
    const d = { world: FAR, country: COUNTRY, city: NEAR }[t.level];
    if (t.from === 'near') api.current.jump(facing(t.lat, t.lon), NEAR * 1.08);
    api.current.fly(facing(t.lat, t.lon), d, FLY_MS, () => propsRef.current.onArrive(t));
  }, [props.target]);

  useEffect(() => {
    const z = props.zoom;
    if (!z || !api.current) return;
    const d = api.current.distance();
    const next = THREE.MathUtils.clamp(z.dir === 'in' ? d * 0.7 : d / 0.7, NEAR, MAX_DISTANCE);
    api.current.zoomTo(next);
  }, [props.zoom]);

  return (
    <VStack
      ref={hostRef}
      style={{
        position: 'absolute',
        inset: 0,
        zIndex: 2,
        background: 'var(--color-background-body)',
        opacity: props.isVisible ? 1 : 0,
        transition: `opacity ${FADE_MS}ms ease`,
        pointerEvents: props.isVisible ? 'auto' : 'none',
        cursor: 'grab',
      }}
      aria-label="3D globe. Drag to turn, scroll to zoom, click London's hexes to open the map."
      role="application"
    >
      <VStack
        gap={2}
        padding={4}
        align="end"
        style={{ position: 'absolute', insetBlockEnd: 0, insetInlineEnd: 0 }}
      >
        {props.notice && (
          <Text color="secondary" display="block" textWrap="pretty">
            {props.notice}
          </Text>
        )}
        <Button
          label={props.enterLabel ?? 'Open London map'}
          variant="secondary"
          size="sm"
          onClick={() => props.onEnterRegion()}
        />
      </VStack>
    </VStack>
  );
}
