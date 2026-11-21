/** Mirrors shared/contracts/score_response.schema.json and the API's pydantic models. */

export type Better = 'higher' | 'lower';

export interface ProfileLayer {
  id: string;
  weight: number;
  better: Better;
}

export interface Profile {
  id: string;
  label: string;
  description: string;
  layers: ProfileLayer[];
  masks: string[];
  has_model: boolean;
}

export interface LayerMeta {
  id: string;
  label: string;
  unit: string;
  kind: 'raster' | 'proximity' | 'aggregate';
  description: string;
  source: string;
  min: number;
  max: number;
}

export interface ScoredCell {
  h3: string;
  score: number | null;
  masked: boolean;
  breakdown: Record<string, number>;
}

export interface ScoreResponse {
  profile: string;
  resolution: number;
  generated_at: string;
  cells: ScoredCell[];
}

export interface LayerValue {
  h3: string;
  value: number;
  raw: number;
}

export interface LayerValues {
  layer: string;
  resolution: number;
  cells: LayerValue[];
}

export interface PointScore {
  profile: string;
  h3: string;
  lat: number;
  lon: number;
  score: number | null;
  masked: boolean;
  rank: number | null;
  ranked_cells: number;
  percentile: number | null;
  breakdown: Record<string, number>;
  raw: Record<string, number>;
  feasibility: number | null;
  shap: Record<string, number> | null;
}

export interface CompareEntry {
  profile: string;
  label: string;
  score: number | null;
  masked: boolean;
  rank: number | null;
  ranked_cells: number;
  percentile: number | null;
}

export interface CompareResponse {
  h3: string;
  lat: number;
  lon: number;
  results: CompareEntry[];
}

export interface Health {
  status: 'ok';
  scoring_source: string;
  data_generated_at: string | null;
  layers: Record<string, 'real' | 'synthetic' | 'unknown'>;
  real_layers: number;
  synthetic_layers: number;
}

export interface ApiErrorBody {
  error: { code: string; message: string; detail?: unknown };
}
