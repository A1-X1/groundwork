/**
 * What can be built, and how a structure's requirements become scoring weights.
 *
 * Numbers here are planning estimates, not engineering figures: GPU specs are approximate
 * vendor peak dense FP16/BF16 tensor throughput and board power.
 */

export interface StructureType {
  id: string;
  label: string;
  /** Profile id that scores it, or null when no profile exists yet. */
  profile: string | null;
  blurb: string;
}

/** Fallback blurbs; the list itself comes from the API's profiles (defaults first). */
export const STRUCTURE_TYPES: StructureType[] = [
  { id: 'data_centre', label: 'Data centre', profile: 'data_centre', blurb: 'Power, cooling and fibre' },
  { id: 'house', label: 'Home', profile: 'house', blurb: 'Safe, connected, affordable' },
  { id: 'school', label: 'School', profile: 'school', blurb: 'Near families, clean air' },
  { id: 'mine', label: 'Mine', profile: 'mine', blurb: 'Water, roads, away from people' },
  { id: 'hospital', label: 'Hospital', profile: null, blurb: 'Reachable, quiet, out of flood risk' },
  { id: 'warehouse', label: 'Warehouse', profile: null, blurb: 'Roads, flat land, low cost' },
  { id: 'office', label: 'Office', profile: null, blurb: 'Transit, amenities' },
  { id: 'solar_farm', label: 'Solar farm', profile: 'solar_farm', blurb: 'Irradiance, grid connection' },
  { id: 'wind_farm', label: 'Wind farm', profile: 'wind_farm', blurb: 'Wind, space, grid connection' },
]; // prettier-ignore

// ---------------------------------------------------------------- data centres

export interface GpuModel {
  id: string;
  label: string;
  /** Approximate peak dense FP16/BF16 tensor TFLOPS per accelerator. */
  tflops: number;
  /** Approximate board power per accelerator, in watts. */
  watts: number;
  memoryGb: number;
}

export const GPUS: GpuModel[] = [
  { id: 'gb200', label: 'NVIDIA GB200 (per GPU)', tflops: 2500, watts: 1200, memoryGb: 192 },
  { id: 'b200', label: 'NVIDIA B200', tflops: 2250, watts: 1000, memoryGb: 192 },
  { id: 'h200', label: 'NVIDIA H200 SXM', tflops: 989, watts: 700, memoryGb: 141 },
  { id: 'h100', label: 'NVIDIA H100 SXM', tflops: 989, watts: 700, memoryGb: 80 },
  { id: 'a100', label: 'NVIDIA A100 SXM', tflops: 312, watts: 400, memoryGb: 80 },
  { id: 'l40s', label: 'NVIDIA L40S', tflops: 362, watts: 350, memoryGb: 48 },
  { id: 'mi325x', label: 'AMD Instinct MI325X', tflops: 1307, watts: 1000, memoryGb: 256 },
  { id: 'mi300x', label: 'AMD Instinct MI300X', tflops: 1307, watts: 750, memoryGb: 192 },
  { id: 'gaudi3', label: 'Intel Gaudi 3', tflops: 1835, watts: 900, memoryGb: 128 },
];

export type Cooling = 'air' | 'liquid' | 'immersion';
export type Workload = 'training' | 'inference' | 'mixed';

export const COOLING: Record<Cooling, { label: string; pue: number; rackKw: number }> = {
  air: { label: 'Air', pue: 1.4, rackKw: 40 },
  liquid: { label: 'Direct-to-chip liquid', pue: 1.2, rackKw: 120 },
  immersion: { label: 'Immersion', pue: 1.08, rackKw: 200 },
};

export interface DataCentreSpec {
  gpu: string;
  gpuCount: number;
  cooling: Cooling;
  pue: number;
  /** Share of the year at full load, for energy estimates. */
  utilisation: number;
  workload: Workload;
  tier: 'II' | 'III' | 'IV';
  lowCarbon: boolean;
}

export const DEFAULT_DC_SPEC: DataCentreSpec = {
  gpu: 'h100',
  gpuCount: 4096,
  cooling: 'liquid',
  pue: 1.2,
  utilisation: 0.7,
  workload: 'training',
  tier: 'III',
  lowCarbon: true,
};

/** Server power per GPU relative to the GPU's board power (CPUs, memory, NICs, storage, fans).
 *  An 8-GPU H100 server draws about 10.2 kW, about 1.8 × 8 × 700 W. */
export const SERVER_FACTOR = 1.8;

export interface DataCentreEstimate {
  peakPflops: number;
  itMw: number;
  facilityMw: number;
  annualGwh: number;
  racks: number;
  whiteSpaceM2: number;
  memoryTb: number;
}

export function estimate(spec: DataCentreSpec): DataCentreEstimate {
  const gpu = GPUS.find((g) => g.id === spec.gpu) ?? GPUS[3]!;
  const n = Math.max(0, spec.gpuCount);
  const itKw = (n * gpu.watts * SERVER_FACTOR) / 1000;
  const facilityKw = itKw * spec.pue;
  const racks = Math.ceil(itKw / COOLING[spec.cooling].rackKw);
  return {
    peakPflops: (n * gpu.tflops) / 1000,
    itMw: itKw / 1000,
    facilityMw: facilityKw / 1000,
    annualGwh: (facilityKw * 8760 * spec.utilisation) / 1e6,
    racks,
    // ~2.5 m² per rack including aisles, white space ≈ 40 % of the building
    whiteSpaceM2: racks * 2.5,
    memoryTb: (n * gpu.memoryGb) / 1000,
  };
}

/** Requirements → slider weights (0–100) for the data_centre profile's layers. */
export function dataCentreWeights(spec: DataCentreSpec): Record<string, number> {
  const e = estimate(spec);
  const power = e.facilityMw >= 50 ? 32 : e.facilityMw >= 10 ? 22 : 14;
  const cooling = { air: [26, 20], liquid: [12, 10], immersion: [6, 6] }[spec.cooling];
  return {
    dist_substation: power,
    dist_hv_line: power,
    free_cooling_hours: cooling[0]!,
    wet_bulb_p99: cooling[1]!,
    dist_fibre_ix: spec.workload === 'inference' ? 28 : spec.workload === 'mixed' ? 18 : 10,
    grid_carbon_intensity: spec.lowCarbon ? 26 : 10,
    slope: 10,
    population_density: 10,
  };
}

// ---------------------------------------------------------------- projects

export interface Project {
  id: string;
  name: string;
  type: string;
  profile: string;
  createdAt: number;
  spec?: DataCentreSpec;
  /** Layers the user said matter most (other structure types). */
  priorities?: string[];
}

const KEY = 'groundwork.projects.v1';

export function loadProjects(): Project[] {
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Project[]) : [];
  } catch {
    return [];
  }
}

export function saveProjects(ps: Project[]): void {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(ps));
  } catch {
    // storage unavailable (private mode): projects last for this session only
  }
}

/** Weights for a project, limited to the layers its profile actually has. */
export function projectWeights(
  p: Project,
  profileLayers: { id: string; weight: number }[],
): Record<string, number> {
  const base = Object.fromEntries(profileLayers.map((l) => [l.id, Math.round(l.weight * 100)]));
  const wanted =
    p.spec && p.type === 'data_centre'
      ? dataCentreWeights(p.spec)
      : Object.fromEntries((p.priorities ?? []).map((id) => [id, 35]));
  for (const [k, v] of Object.entries(wanted)) if (k in base) base[k] = v;
  return base;
}

/** Structure types for the home screen: one per profile, main use cases first. */
export function structureTypesFrom(
  profiles: { id: string; label: string; description: string; is_default?: boolean }[],
): { main: StructureType[]; more: StructureType[] } {
  const types = profiles.map((p) => ({
    id: p.id,
    label: p.label,
    profile: p.id,
    blurb: STRUCTURE_TYPES.find((t) => t.id === p.id)?.blurb ?? p.description,
  }));
  const anyDefault = profiles.some((p) => p.is_default);
  const isMain = (id: string) =>
    anyDefault ? !!profiles.find((p) => p.id === id)?.is_default : true;
  return { main: types.filter((t) => isMain(t.id)), more: types.filter((t) => !isMain(t.id)) };
}
