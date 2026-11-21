import type { RampId } from './colour';

export interface OverlayDef {
  id: string;
  label: string;
  /** `null` = the profile's suitability score. */
  layer: string | null;
  ramp: RampId;
  /** Show the hillshade relief under the hexes. */
  relief?: boolean;
}

/** Curated views shown first in the overlay picker. */
export const VIEWS: OverlayDef[] = [
  { id: 'suitability', label: 'Suitability', layer: null, ramp: 'suitability' },
  { id: 'thermal', label: 'Thermal', layer: 'summer_max_temp', ramp: 'thermal' },
  { id: 'height', label: 'Height', layer: 'elevation', ramp: 'height', relief: true },
  { id: 'flood', label: 'Flood', layer: 'flood_risk', ramp: 'water' },
  { id: 'crime', label: 'Crime', layer: 'crime_rate', ramp: 'hazard' },
  { id: 'air', label: 'Air quality', layer: 'air_quality_no2', ramp: 'hazard' },
];

export function overlayFor(id: string): OverlayDef {
  const view = VIEWS.find((v) => v.id === id);
  if (view) return view;
  const layer = id.startsWith('layer:') ? id.slice('layer:'.length) : id;
  return { id, label: layer, layer, ramp: 'suitability' };
}
