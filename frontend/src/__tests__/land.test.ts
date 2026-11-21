import { cellToChildren, cellToParent, latLngToCell } from 'h3-js';
import { describe, expect, it } from 'vitest';
import type { Region } from '../api/types';
import { buildLandMask, onLand, regionsAt } from '../lib/land';

const london = latLngToCell(51.5, -0.12, 4);
const region: Region = { id: 'uk', name: 'UK', bbox: [-8, 50, 2, 60], resolution: 7, cells: 1, marker_cells: [london], marker_resolution: 4 }; // prettier-ignore

describe('land mask', () => {
  it('is null without marker cells (nothing clipped)', () => {
    expect(buildLandMask([{ ...region, marker_cells: [] }])).toBeNull();
  });

  it('keeps finer cells inside a marker and drops cells over the sea', () => {
    const mask = buildLandMask([region])!;
    expect(onLand(latLngToCell(51.5, -0.12, 7), mask)).toBe(true);
    expect(onLand(latLngToCell(56.0, 1.5, 7), mask)).toBe(false); // North Sea
  });

  it('keeps coarser cells that contain a marker', () => {
    const mask = buildLandMask([region])!;
    expect(onLand(cellToParent(london, 3), mask)).toBe(true);
    expect(onLand(cellToChildren(london, 5)[0]!, mask)).toBe(true);
  });
});

describe('regionsAt', () => {
  const usa: Region = { id: 'usa', name: 'USA', bbox: [-179.1, 18.9, 179.7, 71.3], resolution: 6, cells: 9, marker_cells: [latLngToCell(36.17, -115.14, 4)], marker_resolution: 4 }; // prettier-ignore
  const noMarkers: Region = { id: 'w', name: 'Wrapped', bbox: [-179, 0, 179, 60], resolution: 6, cells: 9 }; // prettier-ignore

  it('uses marker cells, so a world-wrapping bbox does not claim Europe', () => {
    expect(regionsAt(36.17, -115.14, [usa]).map((r) => r.id)).toEqual(['usa']);
    expect(regionsAt(48.85, 2.35, [usa])).toEqual([]);
    expect(regionsAt(48.85, 2.35, [noMarkers])).toEqual([]);
  });

  it('puts the smallest region first', () => {
    const uk = { ...region, cells: 53100 };
    const ldn = { ...region, id: 'london', cells: 2654 };
    expect(regionsAt(51.5, -0.12, [uk, ldn])[0]!.id).toBe('london');
  });
});
