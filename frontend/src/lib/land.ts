/**
 * Where land with data is, from each region's coarse `marker_cells` (they trace the coastline,
 * so nothing is drawn over the sea). Used for the globe's region markers and to clip the map's
 * surrounding grid to land. Without markers (stub API, fixtures) nothing is clipped.
 */
import { cellToParent, getResolution } from 'h3-js';
import type { Region } from '../api/types';

export interface LandMask {
  /** marker resolution → marker cells */
  byRes: Map<number, Set<string>>;
  /** cache: `${markerRes}:${coarserRes}` → parents of the markers at the coarser resolution */
  parents: Map<string, Set<string>>;
}

export function buildLandMask(regions: Region[]): LandMask | null {
  const byRes = new Map<number, Set<string>>();
  for (const r of regions) {
    if (!r.marker_cells?.length || r.marker_resolution == null) continue;
    const set = byRes.get(r.marker_resolution) ?? new Set<string>();
    for (const c of r.marker_cells) set.add(c);
    byRes.set(r.marker_resolution, set);
  }
  return byRes.size ? { byRes, parents: new Map() } : null;
}

/** True when the cell lies on (or covers) land with data. */
export function onLand(cell: string, mask: LandMask): boolean {
  const res = getResolution(cell);
  for (const [mr, set] of mask.byRes) {
    if (res >= mr) {
      if (set.has(res === mr ? cell : cellToParent(cell, mr))) return true;
      continue;
    }
    const key = `${mr}:${res}`;
    let up = mask.parents.get(key);
    if (!up) {
      up = new Set([...set].map((c) => cellToParent(c, res)));
      mask.parents.set(key, up);
    }
    if (up.has(cell)) return true;
  }
  return false;
}
