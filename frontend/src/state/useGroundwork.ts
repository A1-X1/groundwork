import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, ApiError } from '../api/client';
import type {
  CompareResponse,
  Health,
  LayerMeta,
  LayerValues,
  PointScore,
  Profile,
  ScoreResponse,
} from '../api/types';

export interface Selection {
  h3: string;
  lat: number;
  lon: number;
}

export interface PlacedSite extends Selection {
  id: string;
  name: string;
  profile: string;
}

export type Async<T> =
  | { status: 'idle' }
  | { status: 'loading'; data?: T }
  | { status: 'ready'; data: T }
  | { status: 'error'; message: string; data?: T };

const DEBOUNCE_MS = 200;

function message(err: unknown): string {
  return err instanceof ApiError || err instanceof Error ? err.message : 'Something went wrong.';
}

export function defaultWeights(p: Profile | undefined): Record<string, number> {
  return Object.fromEntries((p?.layers ?? []).map((l) => [l.id, Math.round(l.weight * 100)]));
}

export function useGroundwork() {
  const [profiles, setProfiles] = useState<Async<Profile[]>>({ status: 'loading' });
  const [layers, setLayers] = useState<LayerMeta[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [weightsError, setWeightsError] = useState<string | null>(null);
  const [score, setScore] = useState<Async<ScoreResponse>>({ status: 'idle' });
  const [overlayId, setOverlayId] = useState('suitability');
  const [layerValues, setLayerValues] = useState<Record<string, Async<LayerValues>>>({});
  const [selection, setSelection] = useState<Selection | null>(null);
  const [point, setPoint] = useState<Async<PointScore>>({ status: 'idle' });
  const [compare, setCompare] = useState<Async<CompareResponse>>({ status: 'idle' });
  const [sites, setSites] = useState<PlacedSite[]>([]);
  const [appliedWeights, setAppliedWeights] = useState<Record<string, number> | null>(null);

  const lastGoodWeights = useRef<Record<string, number>>({});
  const scoreSeq = useRef(0);
  const pointSeq = useRef(0);

  const profile = useMemo(
    () => (profiles.status === 'ready' ? profiles.data.find((p) => p.id === profileId) : undefined),
    [profiles, profileId],
  );
  const profileList = profiles.status === 'ready' ? profiles.data : [];
  // Latest list for callbacks that run after a reload (e.g. agent-created profiles).
  const profilesRef = useRef<Profile[]>([]);
  profilesRef.current = profileList;
  const layersById = useMemo(() => new Map(layers.map((l) => [l.id, l])), [layers]);

  /** Re-read profiles and layers (the planning agent can add both). */
  const reload = useCallback(async () => {
    const [ps, ls] = await Promise.all([api.profiles(), api.layers()]);
    profilesRef.current = ps;
    setProfiles({ status: 'ready', data: ps });
    setLayers(ls);
    setLayerValues({});
  }, []);

  // ---- bootstrap
  useEffect(() => {
    let alive = true;
    Promise.all([api.profiles(), api.layers()])
      .then(([ps, ls]) => {
        if (!alive) return;
        setProfiles({ status: 'ready', data: ps });
        setLayers(ls);
        // No default use case: the user picks what they are building.
      })
      .catch((e: unknown) => alive && setProfiles({ status: 'error', message: message(e) }));
    api
      .health()
      .then((h) => alive && setHealth(h))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  // ---- scoring: immediate on profile change, debounced on weight change, optimistic
  const isDefaultWeights = useMemo(() => {
    const d = defaultWeights(profile);
    return Object.keys(d).every((k) => d[k] === weights[k]);
  }, [profile, weights]);

  const lastProfileScored = useRef<string | null>(null);
  useEffect(() => {
    if (!profileId || !profile) return;
    const profileChanged = lastProfileScored.current !== profileId;
    const seq = ++scoreSeq.current;
    const run = () => {
      setScore((s) => ({ status: 'loading', data: 'data' in s ? s.data : undefined }));
      api
        .score(profileId, isDefaultWeights ? undefined : weights)
        .then((data) => {
          if (seq !== scoreSeq.current) return;
          lastProfileScored.current = profileId;
          lastGoodWeights.current = weights;
          setAppliedWeights(isDefaultWeights ? null : weights);
          setWeightsError(null);
          setScore({ status: 'ready', data });
        })
        .catch((e: unknown) => {
          if (seq !== scoreSeq.current) return;
          setScore((s) => ({
            status: 'error',
            message: message(e),
            data: 'data' in s ? s.data : undefined,
          }));
          if (!profileChanged) {
            // Roll back the sliders to the last weights the server accepted.
            setWeights(lastGoodWeights.current);
            setWeightsError(`Couldn't re-score: ${message(e)} Weights were reset.`);
          }
        });
    };
    if (profileChanged) {
      run();
      return;
    }
    const t = window.setTimeout(run, DEBOUNCE_MS);
    return () => window.clearTimeout(t);
    // weights is the trigger; isDefaultWeights is derived from it
  }, [profileId, profile, weights]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- layer overlays (cached per layer)
  const ensureLayer = useCallback(
    (layerId: string) => {
      const cur = layerValues[layerId];
      if (cur && cur.status !== 'error') return;
      setLayerValues((m) => ({ ...m, [layerId]: { status: 'loading' } }));
      api
        .layer(layerId)
        .then((data) => setLayerValues((m) => ({ ...m, [layerId]: { status: 'ready', data } })))
        .catch((e: unknown) =>
          setLayerValues((m) => ({ ...m, [layerId]: { status: 'error', message: message(e) } })),
        );
    },
    [layerValues],
  );

  // ---- point detail: follows the weights the server last accepted, so it matches the map
  useEffect(() => {
    if (!selection || !profileId) {
      setPoint({ status: 'idle' });
      return;
    }
    const seq = ++pointSeq.current;
    setPoint((p) => ({ status: 'loading', data: 'data' in p ? p.data : undefined }));
    api
      .point(profileId, selection.lat, selection.lon, appliedWeights ?? undefined)
      .then((d) => seq === pointSeq.current && setPoint({ status: 'ready', data: d }))
      .catch(
        (e: unknown) =>
          seq === pointSeq.current && setPoint({ status: 'error', message: message(e) }),
      );
  }, [selection, profileId, appliedWeights]);

  // ---- compare use cases at the selected location (default weights)
  const compareSeq = useRef(0);
  useEffect(() => {
    if (!selection || profileList.length === 0) {
      setCompare({ status: 'idle' });
      return;
    }
    const seq = ++compareSeq.current;
    setCompare({ status: 'loading' });
    api
      .compare(
        profileList.map((p) => p.id),
        selection.lat,
        selection.lon,
      )
      .then((d) => seq === compareSeq.current && setCompare({ status: 'ready', data: d }))
      .catch(
        (e: unknown) =>
          seq === compareSeq.current && setCompare({ status: 'error', message: message(e) }),
      );
  }, [selection, profileList.length]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- actions
  const chooseProfile = useCallback(
    (id: string) => {
      const p = profilesRef.current.find((x) => x.id === id);
      if (!p) return;
      const w = defaultWeights(p);
      lastGoodWeights.current = w;
      setWeightsError(null);
      setProfileId(id);
      setWeights(w);
    },
    [profileList],
  );

  /** Switch profile and apply a full set of slider weights in one go (from a structure). */
  const applyProfileWeights = useCallback(
    (id: string, w: Record<string, number>) => {
      const p = profilesRef.current.find((x) => x.id === id);
      if (!p) return;
      lastGoodWeights.current = defaultWeights(p);
      setWeightsError(null);
      setProfileId(id);
      setWeights(w);
    },
    [profileList],
  );

  const setWeight = useCallback((layerId: string, value: number) => {
    setWeightsError(null);
    setWeights((w) => ({ ...w, [layerId]: value }));
  }, []);

  const resetWeights = useCallback(() => {
    setWeightsError(null);
    setWeights(defaultWeights(profile));
  }, [profile]);

  const placeSite = useCallback(
    (sel: Selection) => {
      if (!profile) return;
      setSites((s) => {
        const n = s.filter((x) => x.profile === profile.id).length + 1;
        return [
          ...s,
          {
            ...sel,
            id: `${sel.h3}-${profile.id}-${Date.now()}`,
            name: `${profile.label} site ${n}`,
            profile: profile.id,
          },
        ];
      });
    },
    [profile],
  );

  const renameSite = useCallback((id: string, name: string) => {
    setSites((s) => s.map((x) => (x.id === id ? { ...x, name } : x)));
  }, []);

  const removeSite = useCallback((id: string) => {
    setSites((s) => s.filter((x) => x.id !== id));
  }, []);

  return {
    profiles,
    profileList,
    profile,
    layers,
    layersById,
    health,
    weights,
    weightsError,
    isDefaultWeights,
    score,
    overlayId,
    layerValues,
    selection,
    point,
    compare,
    sites,
    chooseProfile,
    applyProfileWeights,
    reload,
    latestProfiles: () => profilesRef.current,
    setWeight,
    resetWeights,
    setOverlayId,
    ensureLayer,
    setSelection,
    placeSite,
    renameSite,
    removeSite,
  };
}

export type GroundworkState = ReturnType<typeof useGroundwork>;
