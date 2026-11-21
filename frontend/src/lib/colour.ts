/**
 * Colour ramps built in OKLCH so equal steps look equally different.
 * Every sequential ramp has monotonic lightness, which keeps it readable
 * for colour-blind viewers and in greyscale.
 */

export type RGB = [number, number, number];
export type OKLCH = [l: number, c: number, h: number];

function linearToSrgb(x: number): number {
  const v = x <= 0.0031308 ? 12.92 * x : 1.055 * Math.pow(x, 1 / 2.4) - 0.055;
  return Math.round(Math.min(1, Math.max(0, v)) * 255);
}

export function oklchToRgb([l, c, h]: OKLCH): RGB {
  const hr = (h * Math.PI) / 180;
  const a = c * Math.cos(hr);
  const b = c * Math.sin(hr);
  const l_ = l + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = l - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = l - 0.0894841775 * a - 1.291485548 * b;
  const L = l_ ** 3;
  const M = m_ ** 3;
  const S = s_ ** 3;
  return [
    linearToSrgb(4.0767416621 * L - 3.3077115913 * M + 0.2309699292 * S),
    linearToSrgb(-1.2684380046 * L + 2.6097574011 * M - 0.3413193965 * S),
    linearToSrgb(-0.0041960863 * L - 0.7034186147 * M + 1.707614701 * S),
  ];
}

function lerpHue(a: number, b: number, t: number): number {
  const d = ((b - a + 540) % 360) - 180;
  return (a + d * t + 360) % 360;
}

export interface Ramp {
  id: string;
  stops: OKLCH[];
  /** Precomputed 256-entry lookup table. */
  lut: RGB[];
}

function makeRamp(id: string, stops: OKLCH[]): Ramp {
  const lut: RGB[] = [];
  for (let i = 0; i < 256; i++) {
    const t = (i / 255) * (stops.length - 1);
    const k = Math.min(stops.length - 2, Math.floor(t));
    const f = t - k;
    const a = stops[k]!;
    const b = stops[k + 1]!;
    lut.push(
      oklchToRgb([a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, lerpHue(a[2], b[2], f)]),
    );
  }
  return { id, stops, lut };
}

export const RAMPS = {
  /** Suitability: deep indigo → teal → lime. Viridis-like. */
  suitability: makeRamp('suitability', [
    [0.3, 0.11, 290],
    [0.45, 0.1, 255],
    [0.6, 0.1, 195],
    [0.74, 0.15, 150],
    [0.91, 0.18, 110],
  ]),
  /** Thermal: near-black violet → crimson → amber → pale yellow. Inferno-like. */
  thermal: makeRamp('thermal', [
    [0.24, 0.08, 290],
    [0.42, 0.17, 345],
    [0.62, 0.2, 30],
    [0.8, 0.16, 70],
    [0.95, 0.12, 100],
  ]),
  /** Height: dark olive lowland → sand → near-white high ground. */
  height: makeRamp('height', [
    [0.35, 0.05, 150],
    [0.6, 0.07, 110],
    [0.8, 0.06, 80],
    [0.96, 0.01, 80],
  ]),
  /** Water: pale → deep blue. */
  water: makeRamp('water', [
    [0.96, 0.03, 220],
    [0.7, 0.11, 235],
    [0.38, 0.13, 260],
  ]),
  /** Generic hazard: pale → deep red-purple. */
  hazard: makeRamp('hazard', [
    [0.96, 0.03, 80],
    [0.72, 0.14, 40],
    [0.45, 0.17, 10],
    [0.3, 0.12, 330],
  ]),
} satisfies Record<string, Ramp>;

export type RampId = keyof typeof RAMPS;

export function sample(ramp: Ramp, t: number): RGB {
  const i = Math.round(Math.min(1, Math.max(0, Number.isFinite(t) ? t : 0)) * 255);
  return ramp.lut[i]!;
}

export function cssGradient(ramp: Ramp, steps = 8): string {
  const parts: string[] = [];
  for (let i = 0; i <= steps; i++) {
    const [l, c, h] = interpolateStops(ramp.stops, i / steps);
    parts.push(`oklch(${(l * 100).toFixed(1)}% ${c.toFixed(3)} ${h.toFixed(1)})`);
  }
  return `linear-gradient(to right, ${parts.join(', ')})`;
}

function interpolateStops(stops: OKLCH[], t: number): OKLCH {
  const x = t * (stops.length - 1);
  const k = Math.min(stops.length - 2, Math.floor(x));
  const f = x - k;
  const a = stops[k]!;
  const b = stops[k + 1]!;
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, lerpHue(a[2], b[2], f)];
}

/** Diverging colours for signed breakdown bars: blue helps, orange hurts. */
export const DIVERGING = {
  positive: 'oklch(56% 0.14 250)',
  negative: 'oklch(64% 0.16 50)',
} as const;

export const MASKED_RGB: RGB = [150, 150, 150];

/** WCAG relative luminance of an sRGB colour, for contrast checks in tests. */
export function relativeLuminance([r, g, b]: RGB): number {
  const lin = (v: number) => {
    const s = v / 255;
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}
