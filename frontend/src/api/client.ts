import type { BBox } from '../lib/viewport';
import type {
  ApiErrorBody,
  AgentEvent,
  Region,
  Review,
  AssistantResponse,
  AzureConfig,
  Connections,
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

/** Read-only requests retry while the API is still starting (make dev starts both at once). */
const RETRY_DELAYS_MS = [500, 1000, 1500, 2000, 3000, 4000, 5000, 5000];

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response | null = null;
  const retries = !init?.method || init.method === 'GET' ? RETRY_DELAYS_MS : [];
  for (let attempt = 0; ; attempt++) {
    try {
      res = await fetch(`${API_URL}${path}`, {
        ...init,
        headers: { 'Content-Type': 'application/json', ...init?.headers },
      });
      break;
    } catch {
      const wait = retries[attempt];
      if (wait == null)
        throw new ApiError(
          0,
          'network',
          `Can't reach the API at ${API_URL}. Is \`make dev\` (or \`make api\`) running? Check its terminal for errors.`,
        );
      await new Promise((r) => setTimeout(r, wait));
    }
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
  review: (text: string, context: Record<string, unknown>): Promise<Review> =>
    fixtures
      ? Promise.resolve({ verdict: 'ok', reason: '', suggestion: null, source: 'rules' })
      : request('/assistant/review', { method: 'POST', body: JSON.stringify({ text, context }) }),

  /** Voxtral TTS: MP3 for a reply, plus the voice slug used (e.g. gb_oliver_cheerful). */
  speak: async (text: string, speaker?: string): Promise<{ audio: Blob; voice: string }> => {
    let res: Response;
    try {
      res = await fetch(`${API_URL}/assistant/speak`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, speaker }),
      });
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
    return { audio: await res.blob(), voice: res.headers.get('X-Voice') ?? 'voxtral' };
  },

  regions: (): Promise<Region[]> => (fixtures ? Promise.resolve([]) : request('/regions')),

  models3d: (): Promise<string[]> => (fixtures ? Promise.resolve([]) : request('/models3d')),
  model3d: (id: string): Promise<unknown> => request(`/models3d/${encodeURIComponent(id)}`),

  connections: (): Promise<Connections> => request('/connections'),
  saveMistral: (apiKey: string): Promise<Connections['mistral']> =>
    request('/connections/mistral', { method: 'PUT', body: JSON.stringify({ api_key: apiKey }) }),
  forgetMistral: (): Promise<Connections['mistral']> =>
    request('/connections/mistral', { method: 'DELETE' }),
  saveAzure: (cfg: AzureConfig): Promise<Connections['azure_ml']> =>
    request('/connections/azure', { method: 'PUT', body: JSON.stringify(cfg) }),
  forgetAzure: (): Promise<Connections['azure_ml']> =>
    request('/connections/azure', { method: 'DELETE' }),
  azureLogin: (): Promise<Connections['azure_ml']> =>
    request('/connections/azure/login', { method: 'POST' }),

  /** Streams the planning agent. Resolves when the stream ends; rejects with ApiError(503) when
   *  the agent isn't installed. */
  runAgent: async (
    prompt: string,
    onEvent: (e: AgentEvent) => void,
    context?: Record<string, unknown>,
  ): Promise<void> => {
    let res: Response;
    try {
      res = await fetch(`${API_URL}/agent/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, context: context ?? {} }),
      });
    } catch {
      throw new ApiError(0, 'network', `Can't reach the API at ${API_URL}.`);
    }
    if (!res.ok || !res.body) {
      const body = (await res.json().catch(() => null)) as ApiErrorBody | null;
      throw new ApiError(
        res.status,
        body?.error.code ?? 'http_error',
        body?.error.message ?? res.statusText,
      );
    }
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i: number;
      while ((i = buf.indexOf('\n\n')) >= 0) {
        const chunk = buf.slice(0, i);
        buf = buf.slice(i + 2);
        const data = chunk.split('\n').find((l) => l.startsWith('data: '));
        if (data) onEvent(JSON.parse(data.slice(6)) as AgentEvent);
      }
    }
  },

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

  /** Points of interest, for the visible area when `bbox` is given (the API caps at 4,000). */
  pois: (bbox?: BBox | null): Promise<Poi[]> =>
    fixtures ? Promise.resolve([]) : request(`/pois${bbox ? `?bbox=${bbox.join(',')}` : ''}`),

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

  layer: (id: string, bbox?: BBox | null): Promise<LayerValues> =>
    fixtures
      ? Promise.reject(fixtureOnly())
      : request(`/layers/${encodeURIComponent(id)}${bbox ? `?bbox=${bbox.join(',')}` : ''}`),

  /** Scores for a profile; with `bbox`, only the cells inside it (viewport fetching). */
  score: (
    profile: string,
    weights?: Record<string, number>,
    bbox?: BBox | null,
  ): Promise<ScoreResponse> => {
    if (fixtures) return fixtures.score();
    if (weights && Object.keys(weights).length > 0) {
      return request('/score/custom', {
        method: 'POST',
        body: JSON.stringify({ profile, weights, ...(bbox ? { bbox } : {}) }),
      });
    }
    return request(`/score/${encodeURIComponent(profile)}${bbox ? `?bbox=${bbox.join(',')}` : ''}`);
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
