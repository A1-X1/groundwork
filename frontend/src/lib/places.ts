/**
 * Place lookup for assistant commands: countries from Natural Earth (bundled via world-atlas,
 * public domain), a short list of major cities, then Nominatim (OpenStreetMap) as a fallback.
 */
import { geoBounds, geoCentroid } from 'd3-geo';
import { feature } from 'topojson-client';
import type { GeometryCollection, Topology } from 'topojson-specification';

export interface Place {
  name: string;
  lat: number;
  lon: number;
  /** [min_lon, min_lat, max_lon, max_lat] when known. */
  bbox?: [number, number, number, number];
  kind: 'country' | 'city' | 'point';
}

const CITIES: [string, number, number][] = [
  ['London', 51.507, -0.128], ['Paris', 48.857, 2.352], ['Berlin', 52.52, 13.405],
  ['Madrid', 40.417, -3.704], ['Rome', 41.903, 12.496], ['Amsterdam', 52.368, 4.904],
  ['Dublin', 53.35, -6.26], ['Edinburgh', 55.953, -3.189], ['Manchester', 53.48, -2.242],
  ['Birmingham', 52.486, -1.89], ['Stockholm', 59.329, 18.069], ['Oslo', 59.914, 10.752],
  ['Helsinki', 60.17, 24.938], ['Copenhagen', 55.676, 12.568], ['Warsaw', 52.23, 21.012],
  ['Vienna', 48.208, 16.373], ['Zurich', 47.377, 8.542], ['Frankfurt', 50.11, 8.682],
  ['Lisbon', 38.722, -9.139], ['Athens', 37.984, 23.728], ['Istanbul', 41.008, 28.978],
  ['Moscow', 55.756, 37.617], ['Cairo', 30.044, 31.236], ['Lagos', 6.524, 3.379],
  ['Nairobi', -1.292, 36.822], ['Johannesburg', -26.204, 28.047], ['Cape Town', -33.925, 18.424],
  ['Dubai', 25.205, 55.271], ['Riyadh', 24.713, 46.675], ['Mumbai', 19.076, 72.878],
  ['Delhi', 28.704, 77.102], ['Bangalore', 12.972, 77.595], ['Singapore', 1.352, 103.82],
  ['Jakarta', -6.208, 106.846], ['Bangkok', 13.756, 100.502], ['Hong Kong', 22.32, 114.169],
  ['Shanghai', 31.23, 121.474], ['Beijing', 39.904, 116.407], ['Seoul', 37.567, 126.978],
  ['Tokyo', 35.676, 139.65], ['Osaka', 34.694, 135.502], ['Sydney', -33.869, 151.209],
  ['Melbourne', -37.814, 144.963], ['Auckland', -36.849, 174.763], ['New York', 40.713, -74.006],
  ['Washington', 38.907, -77.037], ['Boston', 42.36, -71.059], ['Chicago', 41.878, -87.63],
  ['Toronto', 43.653, -79.383], ['Montreal', 45.502, -73.567], ['Vancouver', 49.283, -123.121],
  ['San Francisco', 37.775, -122.419], ['Los Angeles', 34.052, -118.244], ['Seattle', 47.606, -122.332],
  ['Dallas', 32.777, -96.797], ['Miami', 25.762, -80.192], ['Mexico City', 19.433, -99.133],
  ['Sao Paulo', -23.551, -46.633], ['Rio de Janeiro', -22.907, -43.173], ['Buenos Aires', -34.604, -58.382],
  ['Santiago', -33.449, -70.669], ['Lima', -12.046, -77.043], ['Bogota', 4.711, -74.072],
  ['Reykjavik', 64.147, -21.942],
  // North America (data regions: USA, Canada, Mexico)
  ['Las Vegas', 36.17, -115.14], ['Phoenix', 33.448, -112.074], ['Denver', 39.739, -104.99],
  ['Houston', 29.76, -95.37], ['Austin', 30.267, -97.743], ['Atlanta', 33.749, -84.388],
  ['Salt Lake City', 40.761, -111.891], ['Albuquerque', 35.084, -106.65], ['Portland', 45.515, -122.679],
  ['San Diego', 32.716, -117.161], ['Minneapolis', 44.978, -93.265], ['Detroit', 42.331, -83.046],
  ['Philadelphia', 39.953, -75.165], ['Nashville', 36.163, -86.781], ['New Orleans', 29.951, -90.072],
  ['Anchorage', 61.218, -149.9], ['Honolulu', 21.307, -157.858], ['Calgary', 51.045, -114.072],
  ['Edmonton', 53.546, -113.494], ['Ottawa', 45.421, -75.697], ['Winnipeg', 49.895, -97.138],
  ['Quebec City', 46.813, -71.208], ['Halifax', 44.649, -63.575], ['Monterrey', 25.686, -100.316],
  ['Guadalajara', 20.659, -103.349], ['Tijuana', 32.514, -117.038], ['Cancun', 21.161, -86.851],
]; // prettier-ignore

const norm = (s: string) =>
  s
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z ]/g, '')
    .trim();

let countries: Place[] | null = null;

async function loadCountries(): Promise<Place[]> {
  if (countries) return countries;
  const topo = (await import('world-atlas/countries-110m.json')).default as unknown as Topology<{
    countries: GeometryCollection<{ name: string }>;
  }>;
  const fc = feature(topo, topo.objects.countries);
  countries = fc.features.map((f) => {
    const [[w, s], [e, n]] = geoBounds(f);
    const [lon, lat] = geoCentroid(f);
    return { name: f.properties?.name ?? '', lat, lon, bbox: [w, s, e, n], kind: 'country' };
  });
  return countries;
}

const ALIASES: Record<string, string> = {
  uk: 'united kingdom',
  britain: 'united kingdom',
  'great britain': 'united kingdom',
  england: 'united kingdom',
  usa: 'united states of america',
  us: 'united states of america',
  america: 'united states of america',
  'united states': 'united states of america',
  uae: 'united arab emirates',
};

export async function findPlace(query: string, kind?: 'country' | 'city'): Promise<Place | null> {
  const q = norm(ALIASES[norm(query)] ?? query);
  if (!q) return null;
  if (kind !== 'country') {
    const c = CITIES.find(([n]) => norm(n) === q);
    if (c) return { name: c[0], lat: c[1], lon: c[2], kind: 'city' };
  }
  const cs = await loadCountries();
  const country = cs.find((c) => norm(c.name) === q) ?? cs.find((c) => norm(c.name).startsWith(q));
  if (country) return country;
  try {
    const r = await fetch(
      `https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${encodeURIComponent(query)}`,
      { headers: { Accept: 'application/json' } },
    );
    const [hit] = (await r.json()) as { lat: string; lon: string; display_name: string }[];
    if (hit) {
      return {
        name: hit.display_name.split(',')[0] ?? query,
        lat: +hit.lat,
        lon: +hit.lon,
        kind: 'point',
      };
    }
  } catch {
    // offline: no geocoder
  }
  return null;
}
