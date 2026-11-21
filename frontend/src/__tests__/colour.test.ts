import { describe, expect, it } from 'vitest';
import { oklchToRgb, RAMPS, relativeLuminance, sample } from '../lib/colour';

describe('OKLCH ramps', () => {
  it('converts OKLCH white and black', () => {
    expect(oklchToRgb([1, 0, 0])).toEqual([255, 255, 255]);
    expect(oklchToRgb([0, 0, 0])).toEqual([0, 0, 0]);
  });

  it.each(['suitability', 'thermal', 'height'] as const)(
    '%s ramp has monotonically increasing luminance (colour-blind safe ordering)',
    (id) => {
      const ramp = RAMPS[id];
      let prev = -1;
      for (let i = 0; i <= 20; i++) {
        const lum = relativeLuminance(sample(ramp, i / 20));
        expect(lum).toBeGreaterThanOrEqual(prev - 0.005);
        prev = lum;
      }
    },
  );

  it('clamps out-of-range samples', () => {
    expect(sample(RAMPS.suitability, -1)).toEqual(sample(RAMPS.suitability, 0));
    expect(sample(RAMPS.suitability, 2)).toEqual(sample(RAMPS.suitability, 1));
    expect(sample(RAMPS.suitability, Number.NaN)).toEqual(sample(RAMPS.suitability, 0));
  });
});
