import { describe, expect, it } from 'vitest';
import type { Region } from '../api/types';
import { formatRaw } from '../lib/format';
import { contains, GLOBE_ZOOM, minZoomFor, padAndSnap, viewFor } from '../lib/viewport';

const london: Region = {
  id: 'london',
  name: 'Greater London',
  bbox: [-0.52, 51.28, 0.34, 51.7],
  resolution: 8,
  cells: 2654,
};
const usa: Region = {
  id: 'usa',
  name: 'USA',
  bbox: [-125, 24, -66, 50],
  resolution: 6,
  cells: 258000,
};
const regions = [london, usa];
// prettier-ignore

describe('viewport data view', () => {
  it('fetches everything when the API lists no regions (stub)', () => {
    expect(viewFor({ bbox: [-1, 51, 1, 52], zoom: 9 }, [], null).view).toEqual({ key: 'all', bbox: null });
  }); // prettier-ignore

  it('fetches nothing on the globe or zoomed out past it', () => {
    expect(viewFor(null, regions, null).reason).toBe('globe');
    expect(viewFor({ bbox: [-1, 51, 1, 52], zoom: GLOBE_ZOOM - 0.1 }, regions, null).view).toBeNull();
  }); // prettier-ignore

  it('fetches nothing outside every region', () => {
    expect(viewFor({ bbox: [10, 40, 12, 42], zoom: 9 }, regions, null).reason).toBe('no_data');
  });

  it('asks to zoom in over a big region, then fetches only the padded viewport', () => {
    expect(viewFor({ bbox: [-110, 30, -90, 45], zoom: 5 }, regions, null).reason).toBe('zoom_in');
    const { view, reason } = viewFor({ bbox: [-100, 38, -97, 40], zoom: minZoomFor(6) }, regions, null);
    expect(reason).toBe('ok');
    expect(view?.bbox && contains(view.bbox, [-100, 38, -97, 40])).toBe(true);
  }); // prettier-ignore

  it('shows a small region whole even when zoomed out', () => {
    expect(viewFor({ bbox: [-3, 50.5, 2, 52.5], zoom: 6.5 }, regions, null).reason).toBe('ok');
  });

  it('reuses the fetched box for small pans (no refetch)', () => {
    const first = viewFor({ bbox: [-100, 38, -97, 40], zoom: 7.5 }, regions, null).view;
    const next = viewFor({ bbox: [-99.8, 38.1, -96.9, 40.1], zoom: 7.5 }, regions, first).view;
    expect(next?.key).toBe(first?.key);
  });

  it('snaps padded boxes outward', () => {
    const b = padAndSnap([-0.13, 51.49, -0.1, 51.52], 11);
    expect(contains(b, [-0.13, 51.49, -0.1, 51.52])).toBe(true);
  });

  it('labels missing layer data', () => {
    expect(formatRaw(null, 'm')).toBe('no data here');
    expect(formatRaw(undefined, 'm')).toBe('—');
  });
});
