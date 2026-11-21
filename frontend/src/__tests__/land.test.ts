import { cellToChildren, cellToParent, latLngToCell } from 'h3-js';
import { describe, expect, it } from 'vitest';
import type { Region } from '../api/types';
import { buildLandMask, onLand } from '../lib/land';

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
