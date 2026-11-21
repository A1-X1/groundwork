/**
 * Which part of the data to fetch for the current map view.
 *
 * With multi-region data (London res 8, UK res 7, USA res 6, Canada res 5, Mexico res 6),
 * hexagons are fetched only for the visible area, and only once the map is zoomed in far
 * enough for the region's resolution. The fetched box is padded and snapped to a grid, so
 * small pans reuse it (and the API's score cache) instead of fetching again.
 */
import type { Region } from '../api/types';

export type BBox = [number, number, number, number];

export interface Viewport {
  bbox: BBox;
  zoom: number;
}

/** What to fetch: `bbox` null means "everything" (no region list, e.g. the stub API). */
export interface DataView {
  key: string;
  bbox: BBox | null;
}

/** Below this map zoom the flat map hands back to the globe. */
export const GLOBE_ZOOM = 3.6;

/** Map zoom from which a region's hexagons are drawn, by H3 resolution. */
export function minZoomFor(resolution: number): number {
  if (resolution <= 5) return 6;
  if (resolution <= 7) return 7;
  return 9;
}

/** Never ask for more than this many cells in one request. */
export const MAX_VIEW_CELLS = 40000;

const area = ([w, s, e, n]: BBox) => Math.max(0, e - w) * Math.max(0, n - s);

function intersect(a: BBox, b: BBox): BBox | null {
  const r: BBox = [Math.max(a[0], b[0]), Math.max(a[1], b[1]), Math.min(a[2], b[2]), Math.min(a[3], b[3])];
  return r[0] < r[2] && r[1] < r[3] ? r : null;
} // prettier-ignore

export function contains(outer: BBox, inner: BBox): boolean {
  return outer[0] <= inner[0] && outer[1] <= inner[1] && outer[2] >= inner[2] && outer[3] >= inner[3];
} // prettier-ignore

/** Rough number of a region's cells inside a box (cells are spread evenly over its bbox). */
export function cellsIn(region: Region, box: BBox): number {
  const hit = intersect(region.bbox, box);
  if (!hit) return 0;
  return region.cells * (area(hit) / Math.max(1e-9, area(region.bbox)));
}

/** Pad a box by `pad` of its size and snap it outward to a grid that suits the zoom. */
export function padAndSnap(box: BBox, zoom: number, pad = 0.3): BBox {
  const step = zoom >= 10 ? 0.02 : zoom >= 8 ? 0.1 : zoom >= 6 ? 0.5 : 1;
  const dx = (box[2] - box[0]) * pad;
  const dy = (box[3] - box[1]) * pad;
  const down = (v: number) => Math.floor(v / step) * step;
  const up = (v: number) => Math.ceil(v / step) * step;
  const r = (v: number) => Math.round(v * 1000) / 1000;
  return [
    r(Math.max(-180, down(box[0] - dx))),
    r(Math.max(-90, down(box[1] - dy))),
    r(Math.min(180, up(box[2] + dx))),
    r(Math.min(90, up(box[3] + dy))),
  ];
}

export type ViewReason = 'ok' | 'zoom_in' | 'no_data' | 'globe';

/**
 * The data view for a map viewport, or why there is none.
 * `prev` is reused while the viewport stays inside it (no refetch on small pans).
 */
export function viewFor(
  vp: Viewport | null,
  regions: Region[],
  prev: DataView | null,
): { view: DataView | null; reason: ViewReason } {
  if (!vp) return { view: null, reason: 'globe' };
  if (regions.length === 0) return { view: { key: 'all', bbox: null }, reason: 'ok' };
  if (vp.zoom < GLOBE_ZOOM) return { view: null, reason: 'globe' };
  const hits = regions.filter((r) => intersect(r.bbox, vp.bbox));
  if (hits.length === 0) return { view: null, reason: 'no_data' };
  const box = padAndSnap(vp.bbox, vp.zoom);
  const estimate = hits.reduce((n, r) => n + cellsIn(r, box), 0);
  // Any region in view that's zoomed in enough is reason to fetch: the response mixes
  // resolutions (e.g. res-7 rural UK with res-8 towns), and the cell cap still applies.
  const zoomedIn = hits.some((r) => vp.zoom >= minZoomFor(r.resolution));
  // Hexes only past the zoom threshold (user request): until then the region shows as one
  // flat area, so coarse outlines and data hexes never overlap.
  if (!(zoomedIn && estimate <= MAX_VIEW_CELLS)) return { view: null, reason: 'zoom_in' };
  if (prev?.bbox && contains(prev.bbox, vp.bbox) && area(prev.bbox) <= area(box) * 4)
    return { view: prev, reason: 'ok' };
  return { view: { key: box.join(','), bbox: box }, reason: 'ok' };
}
