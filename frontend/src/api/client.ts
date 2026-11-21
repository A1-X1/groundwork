import type {
  ApiErrorBody,
  AssistantResponse,
  Area,
  AreaSummary,
  GeoPolygon,
  StructureRecord,
  Poi,
  CompareResponse,
  Health,
  LayerMeta,
  LayerValues,
  PointScore,
  Profile,
  ScoreResponse,
} from './types';

export const API_URL = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');
export const USE_FIXTURE = import.meta.env.VITE_USE_FIXTURE === 'true';

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    });
  } catch {
    throw new ApiError(0, 'network', `Can't reach the API at ${API_URL}. Is \`make api\` running?`);
  }
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as ApiErrorBody | null;
    throw new ApiError(
      res.status,
      body?.error.code ?? 'http_error',
      body?.error.message ?? res.statusText,
    );
  }
  return (await res.json()) as T;
}

// ---------------------------------------------------------------- fixtures

const fixtures = USE_FIXTURE
  ? {
      profiles: () => import('../fixtures/profiles.json').then((m) => m.default as Profile[]),
      layers: () => import('../fixtures/layers.json').then((m) => m.default as LayerMeta[]),
      score: () =>
        import('../fixtures/score_response.json').then((m) => m.default as ScoreResponse),
    }
  : null;

function fixtureOnly(): never {
  throw new ApiError(0, 'fixture', 'Not available with fixture data. Run the API for this view.');
}

// ---------------------------------------------------------------- endpoints

export const api = {
  areas: (): Promise<Area[]> => (fixtures ? Promise.resolve([]) : request('/areas')),
  createArea: (name: string, geometry: GeoPolygon): Promise<Area> =>
    request('/areas', { method: 'POST', body: JSON.stringify({ name, geometry }) }),
  renameArea: (id: string, name: string): Promise<Area> =>
    request(`/areas/${id}`, { method: 'PATCH', body: JSON.stringify({ name }) }),
  deleteArea: (id: string): Promise<void> => request(`/areas/${id}`, { method: 'DELETE' }),
  areaSummary: (id: string, profile: string): Promise<AreaSummary> =>
    request(`/areas/${id}/summary?profile=${encodeURIComponent(profile)}`),

  structures: (): Promise<StructureRecord[]> =>
    fixtures ? Promise.resolve([]) : request('/structures'),
  createStructure: (
    s: Omit<StructureRecord, 'id' | 'created_at' | 'updated_at'>,
  ): Promise<StructureRecord> =>
    request('/structures', { method: 'POST', body: JSON.stringify(s) }),
  deleteStructure: (id: string): Promise<void> =>
    request(`/structures/${id}`, { method: 'DELETE' }),

  assistantStatus: (): Promise<{ mistral: boolean; voxtral_model: string | null }> =>
    fixtures
      ? Promise.resolve({ mistral: false, voxtral_model: null })
      : request('/assistant/status'),

  transcribe: async (audio: Blob): Promise<{ text: string }> => {
    const form = new FormData();
    const ext = audio.type.includes('ogg') ? 'ogg' : audio.type.includes('mp4') ? 'm4a' : 'webm';
    form.append('file', audio, `speech.${ext}`);
    form.append('language', 'en');
    let res: Response;
    try {
      res = await fetch(`${API_URL}/assistant/transcribe`, { method: 'POST', body: form });
    } catch {
      throw new ApiError(0, 'network', `Can't reach the API at ${API_URL}.`);
    }
    if (!res.ok) {
      const body = (await res.json().catch(() => null)) as ApiErrorBody | null;
      throw new ApiError(
        res.status,
        body?.error.code ?? 'http_error',
        body?.error.message ?? res.statusText,
      );
    }
    return (await res.json()) as { text: string };
  },

  pois: (): Promise<Poi[]> => (fixtures ? Promise.resolve([]) : request('/pois')),

  assistant: (text: string, context: Record<string, unknown>): Promise<AssistantResponse> =>
    fixtures
      ? Promise.reject(fixtureOnly())
      : request('/assistant/command', { method: 'POST', body: JSON.stringify({ text, context }) }),

  health: (): Promise<Health> =>
    fixtures
      ? Promise.resolve({
          status: 'ok',
          scoring_source: 'fixture',
          data_generated_at: null,
          layers: {},
          real_layers: 0,
          synthetic_layers: 0,
        })
      : request('/health'),

  profiles: async (): Promise<Profile[]> => {
    if (!fixtures) return request('/profiles');
    const [profiles, score] = await Promise.all([fixtures.profiles(), fixtures.score()]);
    return profiles.filter((p) => p.id === score.profile);
  },

  layers: (): Promise<LayerMeta[]> => (fixtures ? fixtures.layers() : request('/layers')),

  layer: (id: string): Promise<LayerValues> =>
    fixtures ? Promise.reject(fixtureOnly()) : request(`/layers/${encodeURIComponent(id)}`),

  score: (profile: string, weights?: Record<string, number>): Promise<ScoreResponse> => {
    if (fixtures) return fixtures.score();
    if (weights && Object.keys(weights).length > 0) {
      return request('/score/custom', {
        method: 'POST',
        body: JSON.stringify({ profile, weights }),
      });
    }
    return request(`/score/${encodeURIComponent(profile)}`);
  },

  point: (
    profile: string,
    lat: number,
    lon: number,
    weights?: Record<string, number>,
  ): Promise<PointScore> => {
    if (fixtures) return Promise.reject(fixtureOnly());
    const w =
      weights && Object.keys(weights).length
        ? `&weights=${encodeURIComponent(
            Object.entries(weights)
              .map(([k, v]) => `${k}:${v}`)
              .join(','),
          )}`
        : '';
    return request(`/score/${encodeURIComponent(profile)}/point?lat=${lat}&lon=${lon}${w}`);
  },

  compare: (profiles: string[], lat: number, lon: number): Promise<CompareResponse> =>
    fixtures
      ? Promise.reject(fixtureOnly())
      : request(
          `/compare?profiles=${profiles.map(encodeURIComponent).join(',')}&lat=${lat}&lon=${lon}`,
        ),
};
