import { describe, expect, it } from 'vitest';
import { CATEGORIES, categoryOf } from '../map/poiIcons';
import { keyRows } from '../panels/MapKey';

const lab = ([l, c, h]: [number, number, number]) => {
  const r = (h * Math.PI) / 180;
  return [l, c * Math.cos(r), c * Math.sin(r)];
};
const dist = (a: number[], b: number[]) => Math.hypot(...a.map((v, i) => v - b[i]!));

describe('POI categories', () => {
  it('maps the requested kinds to their colour families', () => {
    expect(categoryOf('station').id).toBe('transport');
    expect(categoryOf('water').id).toBe('water');
    expect(categoryOf('substation').id).toBe('power');
    expect(categoryOf('ixp').id).toBe('network');
    expect(categoryOf('data_centre').id).toBe('network');
    expect(categoryOf('school').id).toBe('education');
    expect(categoryOf('hospital').id).toBe('health');
    expect(categoryOf('airport').id).toBe('air');
  });

  it('keeps every pair of colours clearly apart (OKLab ΔE ≥ 0.1)', () => {
    for (const a of CATEGORIES)
      for (const b of CATEGORIES)
        if (a !== b) expect(dist(lab(a.oklch), lab(b.oklch))).toBeGreaterThanOrEqual(0.1);
  });

  it('separates red and green by lightness too (red–green colour blindness)', () => {
    const red = CATEGORIES.find((c) => c.id === 'transport')!;
    const green = CATEGORIES.find((c) => c.id === 'education')!;
    expect(Math.abs(red.oklch[0] - green.oklch[0])).toBeGreaterThanOrEqual(0.15);
  });

  it('gives unknown agent kinds the next free colour, stably', () => {
    const a = categoryOf('wind_turbine');
    expect(categoryOf('wind_turbine')).toBe(a);
    expect(CATEGORIES.some((c) => c.oklch === a.oklch)).toBe(false);
  });

  it('lists one key row per category in view, in a fixed order', () => {
    const rows = keyRows(['ixp', 'station', 'data_centre', 'station']);
    expect(rows.map((r) => r.category.id)).toEqual(['transport', 'network']);
  });
});
