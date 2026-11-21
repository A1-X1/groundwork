/**
 * POI icons, colour-coded by category: a Lucide glyph in white on a dark disc, with a ring
 * in the category's colour (one consistent outline style). Rendered to SVG data URLs once
 * and handed to deck.gl's IconLayer.
 *
 * Colours are picked in OKLCH with clearly different lightness as well as hue, so the
 * categories stay apart for red–green colour blindness (checked in __tests__/poi.test.ts).
 */
import { renderToStaticMarkup } from 'react-dom/server';
import {
  Factory,
  Hospital,
  MapPin,
  Network,
  Plane,
  School,
  Server,
  TrainFront,
  Waves,
  Zap,
  type LucideIcon,
} from 'lucide-react';
import { oklchToRgb } from '../lib/colour';

export interface PoiCategory {
  id: string;
  label: string;
  /** OKLCH [lightness 0–1, chroma, hue°]. */
  oklch: [number, number, number];
}

export const CATEGORIES: PoiCategory[] = [
  { id: 'transport', label: 'Stations', oklch: [0.6, 0.21, 27] }, // red
  { id: 'water', label: 'Water and reservoirs', oklch: [0.64, 0.16, 245] }, // blue
  { id: 'power', label: 'Electricity (substations, power plants, HV lines)', oklch: [0.87, 0.17, 95] }, // yellow
  { id: 'network', label: 'Internet exchanges and data centres', oklch: [0.6, 0.2, 305] }, // purple
  { id: 'education', label: 'Schools', oklch: [0.8, 0.18, 150] }, // green
  { id: 'health', label: 'Hospitals and health', oklch: [0.74, 0.16, 350] }, // pink
  { id: 'air', label: 'Airports', oklch: [0.92, 0.01, 260] }, // grey/white
]; // prettier-ignore

/** Colours handed out, in order, to categories nobody planned for (new agent layers). */
const SPARE: [number, number, number][] = [
  [0.75, 0.16, 60], // orange
  [0.78, 0.12, 195], // teal
  [0.58, 0.09, 60], // brown
  [0.7, 0.2, 330], // magenta
];

const KIND_CATEGORY: Record<string, string> = {
  station: 'transport', rail: 'transport', subway: 'transport',
  water: 'water', reservoir: 'water',
  substation: 'power', power_plant: 'power', hv_line: 'power', power: 'power',
  ixp: 'network', data_centre: 'network',
  school: 'education',
  hospital: 'health', clinic: 'health', health: 'health',
  airport: 'air',
}; // prettier-ignore

const GLYPH: Record<string, LucideIcon> = {
  station: TrainFront, rail: TrainFront, subway: TrainFront,
  water: Waves, reservoir: Waves,
  substation: Zap, hv_line: Zap, power: Zap, power_plant: Factory,
  ixp: Network, data_centre: Server,
  school: School,
  hospital: Hospital, clinic: Hospital, health: Hospital,
  airport: Plane,
}; // prettier-ignore

export const POI_LABEL: Record<string, string> = {
  substation: 'Substation',
  power_plant: 'Power plant',
  hv_line: 'HV line',
  ixp: 'Internet exchange',
  data_centre: 'Data centre',
  station: 'Station',
  water: 'Water',
  reservoir: 'Reservoir',
  school: 'School',
  hospital: 'Hospital',
  airport: 'Airport',
};

const extra = new Map<string, PoiCategory>();

/** The category for a POI kind; unknown kinds get the next free colour. */
export function categoryOf(kind: string): PoiCategory {
  const known = CATEGORIES.find((c) => c.id === KIND_CATEGORY[kind]);
  if (known) return known;
  let c = extra.get(kind);
  if (!c) {
    const label = kind.replace(/_/g, ' ').replace(/^\w/, (m) => m.toUpperCase());
    c = { id: kind, label, oklch: SPARE[extra.size % SPARE.length]! };
    extra.set(kind, c);
  }
  return c;
}

export function categoryCss(c: PoiCategory): string {
  const [l, ch, h] = c.oklch;
  return `oklch(${l} ${ch} ${h})`;
}

function hex([r, g, b]: [number, number, number]): string {
  return `#${[r, g, b].map((v) => v.toString(16).padStart(2, '0')).join('')}`;
}

const cache = new Map<string, string>();

export function poiIconUrl(kind: string): string {
  const hit = cache.get(kind);
  if (hit) return hit;
  const Glyph = GLYPH[kind] ?? MapPin;
  const ring = hex(oklchToRgb(categoryOf(kind).oklch));
  const glyph = renderToStaticMarkup(<Glyph color="#ffffff" size={30} strokeWidth={2} />);
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">` +
    `<circle cx="32" cy="32" r="28.5" fill="#15191f" stroke="${ring}" stroke-width="4"/>` +
    `<g transform="translate(17 17)">${glyph}</g></svg>`;
  const url = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  cache.set(kind, url);
  return url;
}

export function poiGlyph(kind: string): LucideIcon {
  return GLYPH[kind] ?? MapPin;
}
