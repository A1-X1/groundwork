/**
 * Minimal POI icons: one Lucide glyph, white, on a dark disc with an accent ring. Rendered to
 * SVG data URLs once and handed to deck.gl's IconLayer.
 */
import { renderToStaticMarkup } from 'react-dom/server';
import { Network, Server, TrainFront, Waves, Zap, type LucideIcon } from 'lucide-react';
import type { Poi } from '../api/types';

const GLYPH: Record<Poi['kind'], LucideIcon> = {
  substation: Zap,
  ixp: Network,
  data_centre: Server,
  station: TrainFront,
  water: Waves,
};

export const POI_LABEL: Record<Poi['kind'], string> = {
  substation: 'Substation',
  ixp: 'Internet exchange',
  data_centre: 'Data centre',
  station: 'Station',
  water: 'Water',
};

const cache = new Map<string, string>();

export function poiIconUrl(kind: Poi['kind']): string {
  const hit = cache.get(kind);
  if (hit) return hit;
  const Glyph = GLYPH[kind];
  const glyph = renderToStaticMarkup(<Glyph color="#ffffff" size={30} strokeWidth={2} />);
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">` +
    `<circle cx="32" cy="32" r="29" fill="#15191f" stroke="#76acff" stroke-width="3"/>` +
    `<g transform="translate(17 17)">${glyph}</g></svg>`;
  const url = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  cache.set(kind, url);
  return url;
}
