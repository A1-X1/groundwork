/**
 * Voice assistant orb: one shader-displaced icosphere, accent-coloured on the dark theme.
 * Idle: slow breathing. Listening: ripples and grows with mic level. Thinking: swirls.
 * Speaking: pulses with the speech envelope. Tap to talk, press-and-hold for push-to-talk,
 * drag to spin it a little. No post-processing; under reduced motion it barely moves.
 */
import { Text } from '@astryxdesign/core/Text';
import { VStack } from '@astryxdesign/core/VStack';
import { useEffect, useRef, useState, type MutableRefObject } from 'react';
import * as THREE from 'three';
import type { VoiceState } from '../state/useVoice';

/** Canvas size; the sphere fills the middle ~55 %, leaving room for ripples. */
const SIZE = 168;
const HOLD_MS = 320;

const NOISE = /* glsl */ `
vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
float snoise(vec3 v){
  const vec2 C=vec2(1.0/6.0,1.0/3.0); const vec4 D=vec4(0.0,0.5,1.0,2.0);
  vec3 i=floor(v+dot(v,C.yyy)); vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz); vec3 l=1.0-g; vec3 i1=min(g.xyz,l.zxy); vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx; vec3 x2=x0-i2+C.yyy; vec3 x3=x0-D.yyy; i=mod289(i);
  vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
  float n_=0.142857142857; vec3 ns=n_*D.wyz-D.xzx; vec4 j=p-49.0*floor(p*ns.z*ns.z);
  vec4 x_=floor(j*ns.z); vec4 y_=floor(j-7.0*x_); vec4 x=x_*ns.x+ns.yyyy; vec4 y=y_*ns.x+ns.yyyy;
  vec4 h=1.0-abs(x)-abs(y); vec4 b0=vec4(x.xy,y.xy); vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.0+1.0; vec4 s1=floor(b1)*2.0+1.0; vec4 sh=-step(h,vec4(0.0));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy; vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x); vec3 p1=vec3(a0.zw,h.y); vec3 p2=vec3(a1.xy,h.z); vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x; p1*=norm.y; p2*=norm.z; p3*=norm.w;
  vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0); m=m*m;
  return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}`;

/* Ribbon field shared by both shaders: two families of bands that twist around the sphere in
   opposite directions, warped by slow noise, so they read as folded petals converging. */
const RIBBONS = /* glsl */ `
uniform float uTime; uniform float uFlow; uniform float uAmp;
const float TAU = 6.2831853;
float band(vec3 p, float k, float twist, float speed, float seed){
  float a = atan(p.z, p.x) + twist * p.y + uTime * uFlow * speed
          + 0.55 * snoise(p * 1.3 + vec3(seed, uTime * 0.15, 0.0));
  return a * k / TAU;
}`;

const VERT = /* glsl */ `
uniform float uFreq;
varying vec3 vNormal; varying vec3 vPos; varying vec3 vView;
${NOISE}
${RIBBONS}
void main(){
  vec3 p = position;
  // Folds: each band bulges at its middle and tucks in at its edges; mic level opens them up.
  float b1 = fract(band(p, 7.0, 2.2, 0.35, 1.7));
  float b2 = fract(band(p, 5.0, -2.8, -0.25, 4.3));
  float fold = sin(b1 * 3.14159) * 0.6 + sin(b2 * 3.14159) * 0.4;
  float ripple = snoise(p * uFreq + vec3(0.0, uTime * 0.5, 0.0));
  vec3 displaced = p + normal * (fold * uAmp * 1.6 + ripple * uAmp * 0.6);
  vPos = p;
  vNormal = normalize(normalMatrix * normal);
  vec4 mv = modelViewMatrix * vec4(displaced, 1.0);
  vView = normalize(-mv.xyz);
  gl_Position = projectionMatrix * mv;
}`;

const FRAG = /* glsl */ `
uniform float uGlow;
uniform vec3 cA; uniform vec3 cB; uniform vec3 cC; uniform vec3 cD;
varying vec3 vNormal; varying vec3 vPos; varying vec3 vView;
${NOISE}
${RIBBONS}
vec3 palette(float t){
  t = fract(t);
  vec3 c = mix(cA, cB, smoothstep(0.0, 0.35, t));
  c = mix(c, cC, smoothstep(0.35, 0.7, t));
  return mix(c, cD, smoothstep(0.7, 1.0, t));
}
void main(){
  float f1 = band(vPos, 7.0, 2.2, 0.35, 1.7);
  float f2 = band(vPos, 5.0, -2.8, -0.25, 4.3);
  float b1 = fract(f1); float b2 = fract(f2);
  // Front ribbons (family 1) over back ribbons (family 2): crisp edges, dark creases.
  float edge1 = smoothstep(0.0, 0.035, b1) * smoothstep(1.0, 0.965, b1);
  float crease = 1.0 - 0.45 * (1.0 - smoothstep(0.0, 0.12, min(b1, 1.0 - b1)));
  vec3 back = palette(floor(f2) * 0.37 + b2 * 0.25 + 0.5) * (0.55 + 0.45 * sin(b2 * 3.14159));
  vec3 front = palette(floor(f1) * 0.23 + b1 * 0.3) * crease;
  float overlap = 0.62 + 0.25 * sin(b1 * 3.14159);
  vec3 col = mix(back, front, overlap * edge1);
  // Sharp specular on the ribbon surface, tilted by the fold so highlights run along each band.
  vec3 n = normalize(vNormal + 0.35 * vec3(cos(b1 * 6.28318), 0.0, sin(b1 * 6.28318)));
  vec3 l = normalize(vec3(-0.45, 0.7, 0.6));
  float spec = pow(max(dot(reflect(-l, n), normalize(vView)), 0.0), 48.0);
  float diff = 0.7 + 0.3 * max(dot(n, l), 0.0);
  col = col * diff + vec3(1.0) * spec * 0.55;
  float rim = pow(1.0 - max(dot(normalize(vNormal), normalize(vView)), 0.0), 3.5);
  col += mix(cB, vec3(1.0), 0.4) * rim * (0.35 + uGlow * 0.5);
  gl_FragColor = vec4(col, 1.0);
  #include <colorspace_fragment>
}`;

/** Target shader parameters per state; `level` (0–1) adds on top. */
const TARGETS: Record<VoiceState, { amp: number; freq: number; swirl: number; scale: number }> = {
  // swirl = speed of the gradient flow; amp = surface ripple
  idle: { amp: 0.02, freq: 1.6, swirl: 0.25, scale: 0.92 },
  listening: { amp: 0.05, freq: 2.4, swirl: 0.5, scale: 1.0 },
  thinking: { amp: 0.035, freq: 2.0, swirl: 1.6, scale: 0.95 },
  speaking: { amp: 0.045, freq: 1.8, swirl: 0.7, scale: 0.98 },
};

const LABEL: Record<VoiceState, string> = {
  idle: 'Tap to turn the mic on',
  listening: 'Listening… just speak; I send when you pause. Tap to turn off.',
  thinking: 'Thinking…',
  speaking: 'Speaking',
};

interface Props {
  state: VoiceState;
  level: MutableRefObject<number>;
  message: string | null;
  isAvailable: boolean;
  onStart: () => void;
  onStop: () => void;
}

export function VoiceOrb({ state, level, message, isAvailable, onStart, onStop }: Props) {
  const hostRef = useRef<HTMLElement | null>(null);
  const stateRef = useRef(state);
  stateRef.current = state;
  const hoverRef = useRef(false);
  const [hover, setHover] = useState(false);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(SIZE, SIZE);
    renderer.domElement.style.display = 'block';
    host.prepend(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 10);
    camera.position.z = 7.2;
    const uniforms = {
      uTime: { value: 0 },
      uAmp: { value: 0.012 },
      uFreq: { value: 1.6 },
      uFlow: { value: 0.35 },
      uGlow: { value: 0 },
      cA: { value: new THREE.Color(0x4f7dff) }, // accent blue
      cB: { value: new THREE.Color(0xb7a8ff) }, // lavender
      cC: { value: new THREE.Color(0x8fe3ff) }, // ice cyan
      cD: { value: new THREE.Color(0xffc9b0) }, // warm peach highlight
    };
    const geo = new THREE.IcosahedronGeometry(1, 40);
    const mesh = new THREE.Mesh(
      geo,
      new THREE.ShaderMaterial({ uniforms, vertexShader: VERT, fragmentShader: FRAG }),
    );
    scene.add(mesh);

    // Audio ripples: rings that expand from the orb and fade, driven by the live level.
    const RINGS = 3;
    const ringGeo = new THREE.RingGeometry(1, 1.06, 96);
    const rings = Array.from({ length: RINGS }, (_, i) => {
      const m = new THREE.Mesh(
        ringGeo,
        new THREE.MeshBasicMaterial({
          color: i % 2 ? 0xb7a8ff : 0x8fb8ff,
          transparent: true,
          opacity: 0,
          depthWrite: false,
        }),
      );
      m.position.z = -0.6;
      scene.add(m);
      return { mesh: m, t: i / RINGS };
    });

    let raf = 0;
    let last = performance.now();
    let time = 0;
    let scale = 0.9;
    let spinX = 0;
    let spinY = 0;
    const frame = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const s = stateRef.current;
      const tgt = TARGETS[s];
      const lv = s === 'listening' || s === 'speaking' ? level.current : 0;
      const k = 1 - Math.exp(-dt * 8); // critically damped-ish easing, interruptible
      const motion = reduced ? 0.15 : 1;
      time += dt * motion;
      uniforms.uTime.value = time;
      uniforms.uAmp.value += (tgt.amp * motion + lv * 0.1 * motion - uniforms.uAmp.value) * k;
      uniforms.uFreq.value += (tgt.freq - uniforms.uFreq.value) * k;
      uniforms.uFlow.value += (tgt.swirl + lv * 1.2 - uniforms.uFlow.value) * k;
      uniforms.uGlow.value += ((hoverRef.current ? 0.35 : 0) + lv * 0.6 - uniforms.uGlow.value) * k;
      const breathe = s === 'idle' && !reduced ? Math.sin(time * 1.3) * 0.025 : 0;
      scale += (tgt.scale + lv * 0.12 + breathe - scale) * k;
      mesh.scale.setScalar(scale);
      const audible = s === 'listening' || s === 'speaking';
      for (const r of rings) {
        r.t += dt * (0.35 + lv * 1.6) * motion;
        if (r.t > 1) r.t -= 1;
        const mat = r.mesh.material as THREE.MeshBasicMaterial;
        const target = audible ? (1 - r.t) ** 1.4 * (0.28 + lv * 0.9) : 0;
        mat.opacity += (target - mat.opacity) * k;
        r.mesh.scale.setScalar(scale * (1.02 + r.t * (0.55 + lv * 0.35)));
      }
      spinX *= 0.92;
      spinY *= 0.92;
      mesh.rotation.x += spinX;
      mesh.rotation.y += spinY + 0.002 * motion;
      renderer.render(scene, camera);
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);

    // ---- interaction: tap = toggle, hold = push-to-talk, drag = spin
    const el = renderer.domElement;
    let downAt = 0;
    let moved = 0;
    let lastP = { x: 0, y: 0 };
    let holding = false;
    let holdTimer = 0;
    const onDown = (e: PointerEvent) => {
      el.setPointerCapture(e.pointerId);
      downAt = performance.now();
      moved = 0;
      lastP = { x: e.clientX, y: e.clientY };
      holding = false;
      holdTimer = window.setTimeout(() => {
        if (moved < 6 && stateRef.current === 'idle') {
          holding = true;
          onStartRef.current();
        }
      }, HOLD_MS);
    };
    const onMove = (e: PointerEvent) => {
      if (!downAt) return;
      const dx = e.clientX - lastP.x;
      const dy = e.clientY - lastP.y;
      moved += Math.abs(dx) + Math.abs(dy);
      lastP = { x: e.clientX, y: e.clientY };
      spinY += dx * 0.004;
      spinX += dy * 0.004;
    };
    const onUp = () => {
      window.clearTimeout(holdTimer);
      const quick = performance.now() - downAt < HOLD_MS;
      downAt = 0;
      if (holding) {
        // The mic stays on after a hold: the utterance sends itself when you pause.
        return;
      }
      if (quick && moved < 6) {
        if (stateRef.current === 'listening') onStopRef.current();
        else onStartRef.current();
      }
    };
    el.addEventListener('pointerdown', onDown);
    el.addEventListener('pointermove', onMove);
    el.addEventListener('pointerup', onUp);
    el.addEventListener('pointercancel', onUp);
    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(holdTimer);
      el.removeEventListener('pointerdown', onDown);
      el.removeEventListener('pointermove', onMove);
      el.removeEventListener('pointerup', onUp);
      el.removeEventListener('pointercancel', onUp);
      geo.dispose();
      ringGeo.dispose();
      renderer.dispose();
      el.remove();
    };
  }, [level]);

  const onStartRef = useRef(onStart);
  onStartRef.current = onStart;
  const onStopRef = useRef(onStop);
  onStopRef.current = onStop;

  return (
    <VStack gap={1} align="center" style={{ pointerEvents: 'auto' }}>
      <VStack
        ref={hostRef}
        role="button"
        tabIndex={0}
        aria-label={
          isAvailable ? `Voice assistant: ${LABEL[state]}` : 'Voice assistant unavailable'
        }
        aria-pressed={state === 'listening'}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            if (state === 'listening') onStop();
            else onStart();
          }
        }}
        onPointerEnter={() => {
          hoverRef.current = true;
          setHover(true);
        }}
        onPointerLeave={() => {
          hoverRef.current = false;
          setHover(false);
        }}
        width={SIZE}
        height={SIZE}
        style={{
          cursor: isAvailable ? 'pointer' : 'not-allowed',
          borderRadius: '50%',
          touchAction: 'none',
          opacity: isAvailable ? 1 : 0.5,
          outlineOffset: 4,
        }}
      />
      <Text type="supporting" color="secondary" justify="center" maxLines={2}>
        {state === 'idle' && message ? message : hover || state !== 'idle' ? LABEL[state] : ''}
      </Text>
    </VStack>
  );
}
