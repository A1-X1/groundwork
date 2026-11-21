/**
 * Low-poly, parametric three.js building models rendered through a MapLibre custom
 * layer so they share the map camera. One model per profile type, each well under
 * 5k triangles, Lambert shading, one directional + one ambient light, no shadows.
 */
import * as maplibregl from 'maplibre-gl';
import type { CustomLayerInterface, Map as MLMap } from 'maplibre-gl';
import * as THREE from 'three';

export type BuildingKind = 'data_centre' | 'house' | 'school' | 'mine' | 'generic';

/** Parametric building spec from the planning agent (backend/agent/models3d.py). Metres, y up,
 *  origin at the hex centre on the ground. */
export interface ModelSpec {
  id: string;
  label: string;
  footprint_m: [number, number];
  parts: SpecPart[];
  palette: Record<string, string>;
  segments?: number;
}

type SpecPart = {
  position?: [number, number, number];
  rotation_y?: number;
  color?: string;
} & (
  | { shape: 'box'; size: [number, number, number] }
  | { shape: 'cylinder'; radius: number; height: number }
  | { shape: 'cone'; radius: number; height: number }
  | { shape: 'dome'; radius: number }
  | {
      shape: 'hyperboloid';
      radius_bottom: number;
      radius_waist: number;
      radius_top: number;
      height: number;
      waist_at?: number;
    }
);

const specMaterials = new Map<string, THREE.MeshLambertMaterial>();
function specMaterial(hex: string): THREE.MeshLambertMaterial {
  let m = specMaterials.get(hex);
  if (!m) {
    m = new THREE.MeshLambertMaterial({ color: new THREE.Color(hex), side: THREE.DoubleSide });
    specMaterials.set(hex, m);
  }
  return m;
}

/** Build a three.js group from a spec. Each primitive's base sits at its `position`. */
export function buildFromSpec(spec: ModelSpec): THREE.Group {
  const g = new THREE.Group();
  const seg = Math.max(8, Math.min(48, spec.segments ?? 24));
  for (const part of spec.parts) {
    let geo: THREE.BufferGeometry;
    switch (part.shape) {
      case 'box':
        geo = new THREE.BoxGeometry(...part.size).translate(0, part.size[1] / 2, 0);
        break;
      case 'cylinder':
        geo = new THREE.CylinderGeometry(part.radius, part.radius, part.height, seg).translate(
          0,
          part.height / 2,
          0,
        );
        break;
      case 'cone':
        geo = new THREE.ConeGeometry(part.radius, part.height, seg).translate(
          0,
          part.height / 2,
          0,
        );
        break;
      case 'dome':
        geo = new THREE.SphereGeometry(
          part.radius,
          seg,
          Math.max(4, seg / 2),
          0,
          Math.PI * 2,
          0,
          Math.PI / 2,
        );
        break;
      case 'hyperboloid': {
        // Cooling-tower shell: radius eases bottom → waist → top with a smooth (cosine) profile.
        const w = part.waist_at ?? 0.75;
        const pts: THREE.Vector2[] = [];
        const rows = 12;
        for (let i = 0; i <= rows; i++) {
          const t = i / rows;
          const r =
            t <= w
              ? part.radius_waist +
                (part.radius_bottom - part.radius_waist) * Math.cos((t / w) * (Math.PI / 2))
              : part.radius_waist +
                (part.radius_top - part.radius_waist) *
                  Math.sin(((t - w) / (1 - w)) * (Math.PI / 2));
          pts.push(new THREE.Vector2(r, t * part.height));
        }
        geo = new THREE.LatheGeometry(pts, seg);
        break;
      }
    }
    const hex = spec.palette[part.color ?? 'concrete'] ?? part.color ?? '#b8bcc2';
    const mesh = new THREE.Mesh(geo, specMaterial(hex.startsWith('#') ? hex : '#b8bcc2'));
    const [x, y, z] = part.position ?? [0, 0, 0];
    mesh.position.set(x, y, z);
    mesh.rotation.y = THREE.MathUtils.degToRad(part.rotation_y ?? 0);
    g.add(mesh);
  }
  return g;
}

export interface SiteRender {
  id: string;
  kind: BuildingKind;
  lat: number;
  lon: number;
  /** Height in metres of the hex column the building sits on. */
  baseHeight: number;
  isSelected: boolean;
  /** Agent-designed model; overrides `kind` when present. */
  spec?: ModelSpec;
}

const GROW_MS = 700;
/** Models are exaggerated so they read at city zoom. */
const MODEL_SCALE = 2.4;

const palette = {
  wall: new THREE.MeshLambertMaterial({ color: 0xd9dde3 }),
  wallDark: new THREE.MeshLambertMaterial({ color: 0x8c96a0 }),
  roof: new THREE.MeshLambertMaterial({ color: 0x5b6670 }),
  roofWarm: new THREE.MeshLambertMaterial({ color: 0xb0553a }),
  metal: new THREE.MeshLambertMaterial({ color: 0x46505a }),
  accent: new THREE.MeshLambertMaterial({ color: 0x76acff }),
  spoil: new THREE.MeshLambertMaterial({ color: 0x6d5a45 }),
};

function box(w: number, h: number, d: number, mat: THREE.Material, x = 0, y = 0, z = 0) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
  m.position.set(x, y + h / 2, z);
  return m;
}

function dataCentre(): THREE.Group {
  const g = new THREE.Group();
  g.add(box(240, 70, 150, palette.wall));
  g.add(box(90, 45, 70, palette.wallDark, -150, 0, 30));
  // Roof cooling units: one instanced mesh.
  const unit = new THREE.BoxGeometry(22, 12, 22);
  const units = new THREE.InstancedMesh(unit, palette.metal, 18);
  const m = new THREE.Matrix4();
  let i = 0;
  for (let ix = 0; ix < 6; ix++) {
    for (let iz = 0; iz < 3; iz++) {
      m.makeTranslation(-90 + ix * 36, 76, -40 + iz * 40);
      units.setMatrixAt(i++, m);
    }
  }
  g.add(units);
  g.add(box(240, 4, 6, palette.accent, 0, 66, 76));
  return g;
}

function house(): THREE.Group {
  const g = new THREE.Group();
  g.add(box(130, 70, 100, palette.wall));
  const roof = new THREE.Mesh(new THREE.ConeGeometry(105, 60, 4, 1), palette.roofWarm);
  roof.rotation.y = Math.PI / 4;
  roof.scale.set(1, 1, 0.78);
  roof.position.y = 100;
  g.add(roof);
  g.add(box(14, 40, 14, palette.wallDark, 35, 85, 10));
  g.add(box(26, 40, 4, palette.accent, 0, 0, 51));
  return g;
}

function school(): THREE.Group {
  const g = new THREE.Group();
  g.add(box(220, 60, 70, palette.wall, 0, 0, -40));
  g.add(box(70, 60, 140, palette.wall, -75, 0, 40));
  g.add(box(222, 6, 72, palette.roof, 0, 60, -40));
  g.add(box(72, 6, 142, palette.roof, -75, 60, 40));
  g.add(box(36, 110, 36, palette.wallDark, 70, 0, -40));
  const spire = new THREE.Mesh(new THREE.ConeGeometry(28, 40, 4), palette.accent);
  spire.rotation.y = Math.PI / 4;
  spire.position.set(70, 130, -40);
  g.add(spire);
  return g;
}

function mine(): THREE.Group {
  const g = new THREE.Group();
  // Headframe: two A-frame legs and a back stay.
  const leg = (x: number, z: number, lean: number) => {
    const l = box(8, 190, 8, palette.metal);
    l.position.set(x, 95, z);
    l.rotation.z = lean;
    return l;
  };
  g.add(leg(-28, -24, 0.16), leg(28, -24, -0.16), leg(-28, 24, 0.16), leg(28, 24, -0.16));
  const stay = box(8, 220, 8, palette.metal);
  stay.position.set(0, 100, 70);
  stay.rotation.x = -0.45;
  g.add(stay);
  g.add(box(70, 10, 60, palette.metal, 0, 178, 0));
  const wheel = new THREE.Mesh(new THREE.TorusGeometry(26, 4, 6, 18), palette.accent);
  wheel.position.set(0, 210, 0);
  g.add(wheel);
  g.add(box(110, 45, 80, palette.wallDark, 0, 0, 120));
  const heap = new THREE.Mesh(new THREE.ConeGeometry(90, 70, 9), palette.spoil);
  heap.position.set(-150, 35, 40);
  g.add(heap);
  return g;
}

function generic(): THREE.Group {
  const g = new THREE.Group();
  g.add(box(150, 90, 120, palette.wall));
  g.add(box(152, 6, 122, palette.roof, 0, 90, 0));
  return g;
}

const builders: Record<BuildingKind, () => THREE.Group> = {
  data_centre: dataCentre,
  house,
  school,
  mine,
  generic,
};

export function kindForProfile(profileId: string): BuildingKind {
  return profileId in builders ? (profileId as BuildingKind) : 'generic';
}

interface Entry {
  site: SiteRender;
  group: THREE.Group;
  bornAt: number;
}

function easeOutBack(t: number): number {
  const c1 = 1.4;
  const c3 = c1 + 1;
  return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2;
}

export class BuildingsLayer implements CustomLayerInterface {
  readonly id = 'groundwork-buildings';
  readonly type = 'custom' as const;
  readonly renderingMode = '3d' as const;

  private map: MLMap | null = null;
  private renderer: THREE.WebGLRenderer | null = null;
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.Camera();
  private readonly entries = new Map<string, Entry>();
  private readonly ring: THREE.Mesh;
  private readonly reducedMotion: boolean;

  constructor() {
    this.scene.add(new THREE.AmbientLight(0xffffff, 1.6));
    const sun = new THREE.DirectionalLight(0xffffff, 1.8);
    sun.position.set(-0.6, 1, -0.4).normalize();
    this.scene.add(sun);
    this.ring = new THREE.Mesh(
      new THREE.RingGeometry(190, 215, 6).rotateX(-Math.PI / 2),
      new THREE.MeshBasicMaterial({ color: 0x76acff, side: THREE.DoubleSide }),
    );
    this.ring.position.y = 2;
    this.reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
  }

  onAdd(map: MLMap, gl: WebGLRenderingContext | WebGL2RenderingContext): void {
    this.map = map;
    this.renderer = new THREE.WebGLRenderer({
      canvas: map.getCanvas(),
      context: gl as WebGL2RenderingContext,
      antialias: false,
    });
    this.renderer.autoClear = false;
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  }

  onRemove(): void {
    this.renderer?.dispose();
    this.renderer = null;
    this.map = null;
  }

  setSites(sites: SiteRender[]): void {
    const keep = new Set(sites.map((s) => s.id));
    for (const [id, e] of this.entries) {
      if (!keep.has(id)) {
        this.scene.remove(e.group);
        this.entries.delete(id);
      }
    }
    for (const site of sites) {
      const existing = this.entries.get(site.id);
      if (
        existing &&
        existing.site.kind === site.kind &&
        existing.site.spec?.id === site.spec?.id
      ) {
        existing.site = site;
        continue;
      }
      if (existing) this.scene.remove(existing.group);
      const group = site.spec ? buildFromSpec(site.spec) : builders[site.kind]();
      group.visible = false;
      this.scene.add(group);
      this.entries.set(site.id, {
        site,
        group,
        bornAt: existing?.bornAt ?? performance.now(),
      });
    }
    this.map?.triggerRepaint();
  }

  render(_gl: WebGL2RenderingContext | WebGLRenderingContext, options: unknown): void {
    if (!this.renderer || !this.map) return;
    const mainMatrix = (options as { defaultProjectionData: { mainMatrix: ArrayLike<number> } })
      .defaultProjectionData.mainMatrix;
    const proj = new THREE.Matrix4().fromArray(Array.from(mainMatrix));
    const now = performance.now();
    let animating = false;

    for (const e of this.entries.values()) e.group.visible = false;
    for (const e of this.entries.values()) {
      const { site, group } = e;
      const mc = maplibregl.MercatorCoordinate.fromLngLat([site.lon, site.lat], 0);
      const s = mc.meterInMercatorCoordinateUnits();
      const model = new THREE.Matrix4()
        .makeTranslation(mc.x, mc.y, s * site.baseHeight)
        .scale(new THREE.Vector3(s * MODEL_SCALE, -s * MODEL_SCALE, s * MODEL_SCALE))
        .multiply(new THREE.Matrix4().makeRotationX(Math.PI / 2));

      const t = this.reducedMotion ? 1 : Math.min(1, (now - e.bornAt) / GROW_MS);
      if (t < 1) animating = true;
      group.scale.set(1, Math.max(0.001, easeOutBack(t)), 1);
      group.visible = true;
      if (site.isSelected) group.add(this.ring);
      else group.remove(this.ring);

      this.camera.projectionMatrix = proj.clone().multiply(model);
      this.renderer.resetState();
      this.renderer.render(this.scene, this.camera);
      group.visible = false;
    }
    if (animating) this.map.triggerRepaint();
  }
}
