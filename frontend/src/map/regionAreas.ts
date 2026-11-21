/**
 * Region areas as one flat fill (user request): each top-level region's dissolved GeoJSON
 * outline is painted into a transparent equirectangular texture that wraps a sphere just above
 * the Earth. No hexagons, so nothing can overlap; one draw call; and picking a pixel tells which
 * region was clicked. Rings that cross the antimeridian are unwrapped and drawn twice.
 */
import * as THREE from 'three';

export interface RegionArea {
  id: string;
  name: string;
  /** GeoJSON Polygon or MultiPolygon in lon/lat. */
  outline: { type: string; coordinates: unknown };
}

const W = 4096;
const H = 2048;

type Ring = [number, number][];

function polygons(g: RegionArea['outline']): Ring[][] {
  if (g.type === 'Polygon') return [g.coordinates as Ring[]];
  if (g.type === 'MultiPolygon') return g.coordinates as Ring[][];
  return [];
}

/** Make longitudes continuous along a ring (179 → -179 becomes 179 → 181). */
function unwrap(ring: Ring): Ring {
  const out: Ring = [];
  let prev: number | null = null;
  for (const [lon0, lat] of ring) {
    let lon = lon0;
    if (prev !== null) {
      while (lon - prev > 180) lon -= 360;
      while (lon - prev < -180) lon += 360;
    }
    out.push([lon, lat]);
    prev = lon;
  }
  return out;
}

const x = (lon: number) => ((lon + 180) / 360) * W;
const y = (lat: number) => ((90 - lat) / 180) * H;

export interface PaintedAreas {
  texture: THREE.CanvasTexture;
  /** Region index (into the areas array) at a lat/lon, or -1. */
  regionAt: (lat: number, lon: number) => number;
}

export function paintAreas(areas: RegionArea[], rgb: [number, number, number]): PaintedAreas {
  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const g = canvas.getContext('2d', { willReadFrequently: true })!;
  // Picking map: region i painted with red = i + 1 on a hidden canvas of the same size.
  const pick = document.createElement('canvas');
  pick.width = W / 4;
  pick.height = H / 4;
  const pg = pick.getContext('2d', { willReadFrequently: true })!;

  areas.forEach((area, i) => {
    for (const poly of polygons(area.outline)) {
      const rings = poly.map(unwrap);
      for (const shift of [-360, 0, 360]) {
        const xs = rings.flat().map(([lon]) => x(lon + shift));
        if (Math.max(...xs) < 0 || Math.min(...xs) > W) continue;
        for (const [ctx, scale, fill] of [
          [g, 1, `rgb(${rgb.join(',')})`],
          [pg, 0.25, `rgb(${i + 1},0,0)`],
        ] as const) {
          ctx.beginPath();
          for (const ring of rings) {
            ring.forEach(([lon, lat], k) => {
              const px = x(lon + shift) * scale;
              const py = y(lat) * scale;
              if (k === 0) ctx.moveTo(px, py);
              else ctx.lineTo(px, py);
            });
            ctx.closePath();
          }
          ctx.fillStyle = fill;
          ctx.fill('evenodd');
        }
      }
    }
  });

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  return {
    texture,
    regionAt: (lat, lon) => {
      const px = Math.floor((((x(lon) % W) + W) % W) / 4);
      const py = Math.floor(y(lat) / 4);
      const r = pg.getImageData(px, py, 1, 1).data[0] ?? 0;
      return r > 0 ? r - 1 : -1;
    },
  };
}
