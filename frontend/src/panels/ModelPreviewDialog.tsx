/** SHOW_MODEL: a dialog with a slowly turning three.js preview of a profile's 3D building. */
import { Dialog, DialogHeader } from '@astryxdesign/core/Dialog';
import { Text } from '@astryxdesign/core/Text';
import { VStack } from '@astryxdesign/core/VStack';
import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { api } from '../api/client';
import { buildModel, kindForProfile, type ModelSpec } from '../map/buildings';

const W = 480;
const H = 300;

export function ModelPreviewDialog({
  profile,
  label,
  onClose,
}: {
  profile: string | null;
  label: string;
  onClose: () => void;
}) {
  const hostRef = useRef<HTMLElement | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  useEffect(() => {
    if (!profile) return;
    let alive = true;
    let raf = 0;
    let renderer: THREE.WebGLRenderer | null = null;
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
    void api
      .model3d(profile)
      .then((s) => s as ModelSpec)
      .catch(() => undefined)
      .then((spec) => {
        const host = hostRef.current;
        if (!alive || !host) return;
        setInfo(
          spec
            ? `${spec.parts.length} parts · ${spec.footprint_m[0]} × ${spec.footprint_m[1]} m footprint`
            : 'Built-in model',
        );
        renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        renderer.setSize(W, H);
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        renderer.domElement.style.width = '100%';
        renderer.domElement.style.height = 'auto';
        host.prepend(renderer.domElement);
        const scene = new THREE.Scene();
        scene.add(new THREE.AmbientLight(0xffffff, 1.5));
        const sun = new THREE.DirectionalLight(0xffffff, 2.2);
        sun.position.set(-1, 1.6, 1.2);
        scene.add(sun);
        const model = buildModel(kindForProfile(profile), spec);
        const box = new THREE.Box3().setFromObject(model);
        const size = box.getSize(new THREE.Vector3());
        const centre = box.getCenter(new THREE.Vector3());
        model.position.sub(new THREE.Vector3(centre.x, box.min.y, centre.z));
        const pivot = new THREE.Group();
        pivot.add(model);
        scene.add(pivot);
        const camera = new THREE.PerspectiveCamera(30, W / H, 1, 50000);
        const r = Math.max(size.x, size.y, size.z) * 0.6;
        const d = (r / Math.sin(THREE.MathUtils.degToRad(15))) * 0.9;
        camera.position.set(d * 0.7, d * 0.5, d * 0.7);
        camera.lookAt(0, size.y * 0.3, 0);
        const tick = () => {
          if (!reduced) pivot.rotation.y += 0.006;
          renderer?.render(scene, camera);
          raf = requestAnimationFrame(tick);
        };
        tick();
      });
    return () => {
      alive = false;
      cancelAnimationFrame(raf);
      renderer?.dispose();
      renderer?.domElement.remove();
    };
  }, [profile]);

  return (
    <Dialog isOpen={!!profile} onOpenChange={(o) => !o && onClose()} width={540}>
      <DialogHeader title={label} onOpenChange={(o) => !o && onClose()} />
      <VStack gap={2} padding={4} ref={hostRef}>
        {info && (
          <Text type="supporting" color="secondary">
            {info}
          </Text>
        )}
      </VStack>
    </Dialog>
  );
}
