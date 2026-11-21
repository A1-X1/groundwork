import { Banner } from '@astryxdesign/core/Banner';
import { Layout, LayoutContent, LayoutHeader, LayoutPanel } from '@astryxdesign/core/Layout';
import { ProgressBar } from '@astryxdesign/core/ProgressBar';
import { VStack } from '@astryxdesign/core/VStack';
import { HStack } from '@astryxdesign/core/HStack';
import { cellToLatLng, cellToParent, latLngToCell } from 'h3-js';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from './api/client';
import type { AssistantCommand, Poi } from './api/types';
import {
  loadProjects,
  projectWeights,
  saveProjects,
  type DataCentreSpec,
  type Project,
} from './lib/structures';
import { AreaDetail, AreasPanel } from './panels/AreasPanel';
import { SegmentedControl, SegmentedControlItem } from '@astryxdesign/core/SegmentedControl';
import type { Area, AreaSummary, StructureRecord } from './api/types';
import type { Basemap, MapArea } from './map/MapView';
import { HomeScreen } from './panels/HomeScreen';
import { findPlace } from './lib/places';
import { flushSync } from 'react-dom';
import { formatRaw, formatScore } from './lib/format';
import { overlayFor } from './lib/overlays';
import { kindForProfile, type ModelSpec, type SiteRender } from './map/buildings';
import { GlobeView, type GlobeTarget, type RegionHex } from './map/GlobeView';
import { ELEVATION_SCALE, MapView, type HexDatum, type MapFocus } from './map/MapView';
import { CommandBar } from './panels/CommandBar';
import { ConnectionsDialog } from './panels/ConnectionsDialog';
import { ApiError } from './api/client';
import { VoiceDock } from './panels/VoiceDock';
import { useVoice } from './state/useVoice';
import { ControlPanel } from './panels/ControlPanel';
import { CellDetail, SiteCompare, TopSites } from './panels/DetailPanel';
import { TopBar, type LegendSpec } from './panels/TopBar';
import { useGroundwork, type PlacedSite, type Selection } from './state/useGroundwork';

type RightView = 'overview' | 'detail' | 'compare-sites' | 'area';

const toProject = (r: StructureRecord): Project => ({
  id: r.id,
  name: r.name,
  type: r.type,
  profile: r.profile,
  createdAt: Date.parse(r.created_at),
  spec: (r.spec as unknown as DataCentreSpec | null) ?? undefined,
  priorities: r.priorities,
});

export default function App() {
  const gw = useGroundwork();
  const [view, setView] = useState<RightView>('overview');
  const [isPlacing, setPlacing] = useState(false);
  const [showMasked, setShowMasked] = useState(true);
  const [terrain, setTerrain] = useState(false);
  const [lowPower, setLowPower] = useState(false);
  const [focus, setFocus] = useState<MapFocus | null>(null);
  const [heroSiteId, setHeroSiteId] = useState<string | null>(null);
  const [globeVisible, setGlobeVisible] = useState(true);
  const [spinning, setSpinning] = useState(true);
  const [globeTarget, setGlobeTarget] = useState<GlobeTarget | null>(null);
  const [globeZoom, setGlobeZoom] = useState<{ dir: 'in' | 'out'; nonce: number } | null>(null);
  const [mapZoom, setMapZoom] = useState<{ dir: 'in' | 'out'; nonce: number } | null>(null);
  const [arrival, setArrival] = useState<{ lat: number; lon: number; nonce: number } | null>(null);
  const [globeNotice, setGlobeNotice] = useState<string | null>(null);
  const [screen, setScreen] = useState<'home' | 'explore'>('home');
  const [connectionsOpen, setConnectionsOpen] = useState(false);
  const [connectionsReason, setConnectionsReason] = useState<string | null>(null);
  const [modelIds, setModelIds] = useState<string[]>([]);
  const [modelSpecs, setModelSpecs] = useState<Record<string, ModelSpec>>({});
  const [projects, setProjects] = useState<Project[]>([]);
  /** Structures live in the API's database; browser storage is the fallback when it's down. */
  const [projectsLocal, setProjectsLocal] = useState(false);
  const [basemap, setBasemap] = useState<Basemap>('map');
  const [isDrawing, setDrawing] = useState(false);
  const [draft, setDraft] = useState<[number, number][]>([]);
  const [pendingName, setPendingName] = useState<string | null>(null);
  const [areaError, setAreaError] = useState<string | null>(null);
  const [areas, setAreas] = useState<Area[]>([]);
  const [selectedAreaId, setSelectedAreaId] = useState<string | null>(null);
  const [areaSummary, setAreaSummary] = useState<
    | { status: 'loading' }
    | { status: 'ready'; data: AreaSummary }
    | { status: 'error'; message: string }
    | null
  >(null);
  const [project, setProject] = useState<Project | null>(null);
  const [pois, setPois] = useState<Poi[]>([]);

  useEffect(() => {
    api
      .pois()
      .then(setPois)
      .catch(() => setPois([]));
  }, []);
  useEffect(() => {
    api
      .structures()
      .then((rs) => setProjects(rs.map(toProject)))
      .catch(() => {
        setProjectsLocal(true);
        setProjects(loadProjects());
      });
    api
      .areas()
      .then(setAreas)
      .catch(() => setAreas([]));
  }, []);
  useEffect(() => {
    if (projectsLocal) saveProjects(projects);
  }, [projects, projectsLocal]);

  const createProject = useCallback(
    async (p: Project): Promise<Project> => {
      if (projectsLocal) {
        setProjects((ps) => [p, ...ps]);
        return p;
      }
      try {
        const rec = await api.createStructure({
          name: p.name,
          type: p.type,
          profile: p.profile,
          spec: (p.spec as unknown as Record<string, unknown>) ?? null,
          priorities: p.priorities ?? [],
          area_id: null,
        });
        const saved = toProject(rec);
        setProjects((ps) => [saved, ...ps]);
        return saved;
      } catch {
        setProjectsLocal(true);
        setProjects((ps) => [p, ...ps]);
        return p;
      }
    },
    [projectsLocal],
  );

  const removeProject = useCallback(
    (id: string) => {
      setProjects((ps) => ps.filter((x) => x.id !== id));
      if (!projectsLocal) api.deleteStructure(id).catch(() => undefined);
    },
    [projectsLocal],
  );

  // ---- areas
  const mapAreas: MapArea[] = useMemo(
    () => areas.map((a) => ({ id: a.id, name: a.name, ring: a.geometry.coordinates[0] ?? [] })),
    [areas],
  );
  const selectedArea = areas.find((a) => a.id === selectedAreaId) ?? null;

  useEffect(() => {
    if (!selectedAreaId || !gw.profile) {
      setAreaSummary(null);
      return;
    }
    let alive = true;
    setAreaSummary({ status: 'loading' });
    api
      .areaSummary(selectedAreaId, gw.profile.id)
      .then((d) => alive && setAreaSummary({ status: 'ready', data: d }))
      .catch(
        (e: unknown) =>
          alive && setAreaSummary({ status: 'error', message: String((e as Error).message) }),
      );
    return () => {
      alive = false;
    };
  }, [selectedAreaId, gw.profile]);

  const overlay = overlayFor(gw.overlayId);
  const scoreData = 'data' in gw.score ? gw.score.data : undefined;
  const layerAsync = overlay.layer ? gw.layerValues[overlay.layer] : undefined;
  const layerMeta = overlay.layer ? gw.layersById.get(overlay.layer) : undefined;

  useEffect(() => {
    if (overlay.layer) gw.ensureLayer(overlay.layer);
  }, [overlay.layer]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- ranks (local, for tooltips and fixture mode)
  const ranks = useMemo(() => {
    const m = new Map<string, number>();
    (scoreData?.cells ?? [])
      .filter((c) => c.score != null)
      .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
      .forEach((c, i) => m.set(c.h3, i + 1));
    return m;
  }, [scoreData]);

  // ---- coarse (res 5) hexes for the globe, and where detailed hexes exist
  // Where detailed hexes exist, independent of the chosen use case (any layer covers the grid).
  const [coverage, setCoverage] = useState<string[]>([]);
  useEffect(() => {
    const first = gw.layers[0];
    if (!first || coverage.length) return;
    api
      .layer(first.id)
      .then((lv) => setCoverage(lv.cells.map((c) => c.h3)))
      .catch(() => undefined);
  }, [gw.layers, coverage.length]);
  const scoredIds = useMemo(
    () => new Set([...coverage, ...(scoreData?.cells.map((c) => c.h3) ?? [])]),
    [scoreData, coverage],
  );
  const regionHexes: RegionHex[] = useMemo(() => {
    const acc = new Map<string, { sum: number; n: number }>();
    if (!scoreData) {
      // No use case yet: show the covered region as neutral coarse hexes.
      const parents = new Set(coverage.map((h) => cellToParent(h, 5)));
      return [...parents].map((h3) => ({ h3, t: 0.25 }));
    }
    for (const c of scoreData.cells) {
      if (c.score == null) continue;
      const parent = cellToParent(c.h3, 5);
      const a = acc.get(parent) ?? { sum: 0, n: 0 };
      a.sum += c.score;
      a.n += 1;
      acc.set(parent, a);
    }
    const avgs = [...acc].map(([h3, a]) => ({ h3, v: a.sum / a.n }));
    const lo = Math.min(...avgs.map((x) => x.v));
    const span = Math.max(1e-6, Math.max(...avgs.map((x) => x.v)) - lo);
    return avgs.map((x) => ({ h3: x.h3, t: (x.v - lo) / span }));
  }, [scoreData, coverage]);
  const hasDetail = useCallback(
    (lat: number, lon: number) => scoredIds.has(latLngToCell(lat, lon, 8)),
    [scoredIds],
  );

  // ---- hexes for the map
  const cells: HexDatum[] = useMemo(() => {
    if (!scoreData && !overlay.layer) {
      return coverage.map((h3) => ({
        h3,
        t: 0.08,
        h: 0,
        masked: false,
        tooltip: 'Choose a use case to score this hexagon',
        neutral: true,
      }));
    }
    if (!overlay.layer && scoreData) {
      const scores = scoreData.cells.flatMap((c) => (c.score == null ? [] : [c.score]));
      const lo = Math.min(...scores);
      const span = Math.max(1e-6, Math.max(...scores) - lo);
      return scoreData.cells.map((c) => {
        const t = c.score == null ? 0 : (c.score - lo) / span;
        return {
          h3: c.h3,
          t,
          h: t,
          masked: c.masked,
          tooltip: c.masked
            ? 'No-go area'
            : `Score ${formatScore(c.score)} · rank ${ranks.get(c.h3)?.toLocaleString('en-GB')}`,
        };
      });
    }
    if (layerAsync?.status !== 'ready') return [];
    const maskedSet = new Set(scoreData?.cells.filter((c) => c.masked).map((c) => c.h3));
    return layerAsync.data.cells.map((c) => ({
      h3: c.h3,
      t: c.value,
      h: c.value,
      masked: maskedSet.has(c.h3),
      tooltip: `${layerMeta?.label ?? overlay.label}: ${formatRaw(c.raw, layerMeta?.unit ?? '')}`,
    }));
  }, [scoreData, overlay.layer, overlay.label, layerAsync, layerMeta, ranks]);

  const legend: LegendSpec | null =
    !overlay.layer && !gw.profile
      ? null
      : overlay.layer
        ? layerMeta
          ? {
              title: layerMeta.label,
              ramp: overlay.ramp,
              low: formatRaw(layerMeta.min, layerMeta.unit),
              high: formatRaw(layerMeta.max, layerMeta.unit),
            }
          : null
        : {
            title: `${gw.profile?.label ?? ''} suitability`,
            ramp: 'suitability',
            low: 'Worse',
            high: 'Better',
          };

  // ---- placed sites → three.js
  const heightOf = useCallback(
    (h3: string) => {
      const c = cells.find((x) => x.h3 === h3);
      return c && !c.masked ? c.h * ELEVATION_SCALE : 0;
    },
    [cells],
  );
  // Agent-designed buildings: load the spec for any placed site whose profile has one.
  useEffect(() => {
    const wanted = new Set(gw.sites.map((x) => x.profile).filter((p) => modelIds.includes(p)));
    for (const id of wanted) {
      if (modelSpecs[id]) continue;
      api
        .model3d(id)
        .then((spec) => setModelSpecs((m) => ({ ...m, [id]: spec as ModelSpec })))
        .catch(() => undefined);
    }
  }, [gw.sites, modelIds, modelSpecs]);

  const siteRenders: SiteRender[] = useMemo(
    () =>
      gw.sites.map((s) => ({
        id: s.id,
        kind: kindForProfile(s.profile),
        spec: modelSpecs[s.profile],
        lat: s.lat,
        lon: s.lon,
        baseHeight: heightOf(s.h3),
        isSelected: gw.selection?.h3 === s.h3,
      })),
    [gw.sites, gw.selection, heightOf, modelSpecs],
  );

  // ---- interactions
  const select = useCallback(
    (sel: Selection) => {
      gw.setSelection(sel);
      setView('detail');
    },
    [gw],
  );

  const onHexClick = useCallback(
    (h3: string, lat: number, lon: number) => {
      const sel = { h3, lat, lon };
      if (isPlacing) {
        gw.placeSite(sel);
        setPlacing(false);
      }
      select(sel);
    },
    [isPlacing, gw, select],
  );

  const openSite = useCallback(
    (site: PlacedSite, el: HTMLElement | null) => {
      const apply = () => {
        if (site.profile !== gw.profile?.id) gw.chooseProfile(site.profile);
        select(site);
        setFocus({ lat: site.lat, lon: site.lon, nonce: Date.now() });
      };
      const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
      if (!document.startViewTransition || reduced || !el) {
        apply();
        return;
      }
      el.style.viewTransitionName = 'site-hero';
      const t = document.startViewTransition(() => {
        el.style.viewTransitionName = '';
        flushSync(() => {
          apply();
          setHeroSiteId(site.id);
        });
      });
      void t.finished.finally(() => setHeroSiteId(null));
    },
    [gw, select],
  );

  // ---- globe ⇄ map
  const flyGlobe = useCallback((lat: number, lon: number, level: GlobeTarget['level']) => {
    setGlobeNotice(null);
    if (level !== 'world') setSpinning(false);
    setGlobeVisible(true);
    setGlobeTarget({ lat, lon, level, nonce: Date.now() });
  }, []);

  const onArrive = useCallback(
    (t: GlobeTarget) => {
      if (t.level === 'world') return;
      if (hasDetail(t.lat, t.lon)) {
        if (t.level !== 'city') return;
        setGlobeVisible(false);
        setArrival({ lat: t.lat, lon: t.lon, nonce: Date.now() });
      } else {
        setGlobeNotice('Detailed hexes aren’t built here yet. London is the demo region.');
      }
    },
    [hasDetail],
  );

  /** Go to a place: on the map if it is already showing and has data, else via the globe.
   *  Without detailed data the globe stops at country distance (the texture is coarse). */
  const goTo = useCallback(
    (lat: number, lon: number, wantCity = true) => {
      const detail = hasDetail(lat, lon);
      if (!globeVisible && detail) {
        setFocus({ lat, lon, nonce: Date.now() });
        return;
      }
      flyGlobe(lat, lon, wantCity && detail ? 'city' : 'country');
    },
    [globeVisible, hasDetail, flyGlobe],
  );

  // ---- assistant commands
  const pointRef = useRef(gw.point);
  pointRef.current = gw.point;

  const explain = useCallback((): string => {
    const p = pointRef.current;
    if (p.status !== 'ready') return 'Select a hexagon first and I’ll explain its score.';
    const d = p.data;
    if (d.masked)
      return `This hexagon is ruled out: it is inside ${d.masks.join(' and ').replace(/_/g, ' ')}.`;
    const top = Object.entries(d.breakdown).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
    const label = (id: string) => gw.layersById.get(id)?.label.toLowerCase() ?? id;
    const helps = top
      .filter(([, v]) => v > 0)
      .slice(0, 2)
      .map(([k]) => label(k));
    const hurts = top
      .filter(([, v]) => v < 0)
      .slice(0, 2)
      .map(([k]) => label(k));
    return (
      `It scores ${formatScore(d.score)} out of 100, rank ${d.rank ?? '–'} of ${d.ranked_cells}. ` +
      (helps.length ? `Helped most by ${helps.join(' and ')}. ` : '') +
      (hurts.length ? `Held back by ${hurts.join(' and ')}.` : '')
    );
  }, [gw.layersById]);

  const resolvePoint = useCallback(
    async (args: Record<string, unknown>) => {
      if (typeof args.lat === 'number' && typeof args.lon === 'number') {
        return { lat: args.lat, lon: args.lon };
      }
      if (typeof args.name === 'string') {
        const place = await findPlace(args.name);
        if (place) return { lat: place.lat, lon: place.lon };
      }
      return gw.selection ? { lat: gw.selection.lat, lon: gw.selection.lon } : null;
    },
    [gw.selection],
  );

  const runCommands = useCallback(
    async (cmds: AssistantCommand[]): Promise<string[]> => {
      const notes: string[] = [];
      for (const { type, args } of cmds) {
        const str = (k: string) => (typeof args[k] === 'string' ? (args[k] as string) : '');
        switch (type) {
          case 'PAN_COUNTRY':
          case 'PAN_CITY':
          case 'PAN_REGION': {
            if (Array.isArray(args.bbox) && args.bbox.length === 4) {
              const [w, so, e, n] = args.bbox as number[];
              goTo(((so ?? 0) + (n ?? 0)) / 2, ((w ?? 0) + (e ?? 0)) / 2, false);
              break;
            }
            const place = await findPlace(
              str('name'),
              type === 'PAN_COUNTRY' ? 'country' : undefined,
            );
            if (!place) notes.push(`I couldn't find ${str('name') || 'that place'}.`);
            else goTo(place.lat, place.lon, place.kind !== 'country');
            break;
          }
          case 'ZOOM':
            if (globeVisible)
              setGlobeZoom({ dir: args.direction === 'out' ? 'out' : 'in', nonce: Date.now() });
            else setMapZoom({ dir: args.direction === 'out' ? 'out' : 'in', nonce: Date.now() });
            break;
          case 'RESET_VIEW':
            flyGlobe(25, 10, 'world');
            setSpinning(true);
            break;
          case 'ROTATE_GLOBE':
            setSpinning(args.state !== 'off');
            break;
          case 'SET_PROFILE':
            gw.chooseProfile(str('id'));
            break;
          case 'SET_OVERLAY': {
            const id = str('layer');
            gw.setOverlayId(
              ['suitability', 'thermal', 'height', 'flood', 'crime', 'air'].includes(id)
                ? id
                : `layer:${id}`,
            );
            break;
          }
          case 'SET_WEIGHT':
            gw.setWeight(str('layer'), Number(args.weight));
            break;
          case 'RESET_WEIGHTS':
            gw.resetWeights();
            break;
          case 'TOGGLE_MASKS':
            setShowMasked(args.state !== 'off');
            break;
          case 'TOGGLE_TERRAIN':
            setTerrain(args.state !== 'off');
            break;
          case 'SHOW_TOP_SITES':
            if (typeof args.profile === 'string') gw.chooseProfile(args.profile);
            gw.setSelection(null);
            setView('overview');
            if (globeVisible) flyGlobe(51.5, -0.11, 'city');
            break;
          case 'SELECT_PLACE':
          case 'COMPARE_USE_CASES':
          case 'EXPLAIN':
          case 'PLACE_SITE': {
            if (type === 'EXPLAIN' && !args.name && args.lat == null) {
              notes.push(explain());
              break;
            }
            const pt = await resolvePoint(args);
            if (!pt) {
              notes.push('Tell me where, for example “place a school at 51.52, -0.1”.');
              break;
            }
            if (!hasDetail(pt.lat, pt.lon)) {
              goTo(pt.lat, pt.lon);
              notes.push('There are no detailed hexes there yet.');
              break;
            }
            const sel = { h3: latLngToCell(pt.lat, pt.lon, 8), ...pt };
            if (typeof args.profile === 'string') gw.chooseProfile(args.profile);
            if (type === 'PLACE_SITE') gw.placeSite(sel);
            select(sel);
            goTo(pt.lat, pt.lon);
            if (type === 'EXPLAIN') notes.push('Opened the explanation for that spot.');
            break;
          }
          case 'REMOVE_SITE':
          case 'RENAME_SITE': {
            const key = str('id').toLowerCase();
            const site =
              gw.sites.find((x) => x.id === key || x.name.toLowerCase() === key) ?? gw.sites.at(-1);
            if (!site) notes.push('There are no placed sites yet.');
            else if (type === 'REMOVE_SITE') gw.removeSite(site.id);
            else if (str('name')) gw.renameSite(site.id, str('name'));
            break;
          }
          case 'COMPARE_SITES':
            if (gw.sites.length >= 2) setView('compare-sites');
            else notes.push('Place at least two sites to compare them.');
            break;
          case 'HELP':
            notes.push(
              'Try: “fly to Tokyo”, “best house sites”, “thermal view”, “set crime rate to 80”, ' +
                '“place a data centre here”, “why this score?”, “reset view”.',
            );
            break;
        }
      }
      return notes;
    },
    [gw, globeVisible, goTo, flyGlobe, explain, resolvePoint, hasDetail, select],
  );

  /** Agent UI commands are flat ({command, ...args}); the executor takes {type, args}. */
  const fromAgent = (cmds: Record<string, unknown>[]): AssistantCommand[] =>
    cmds.map(({ command, ...args }) => ({ type: String(command), args }));

  const TOOL_LABELS: Record<string, string> = {
    get_catalog: 'Checking what Groundwork already knows…',
    add_layer: 'Adding a data source…',
    add_source_layer: 'Adding a data source…',
    write_profile: 'Writing the scoring profile…',
    validate_profile: 'Checking the profile…',
    write_model3d: 'Designing the 3D building…',
    build_layers: 'Building the new layers…',
    train_model: 'Training the feasibility model…',
    ui_command: 'Updating the map…',
  };

  const runPlanningAgent = useCallback(
    async (text: string, onProgress?: (msg: string) => void): Promise<string> => {
      let final = '';
      const notes: string[] = [];
      await api.runAgent(text, (e) => {
        if (e.type === 'tool_call' && typeof e.name === 'string') {
          onProgress?.(TOOL_LABELS[e.name] ?? `Running ${e.name.replace(/_/g, ' ')}…`);
        } else if (e.type === 'ui' && Array.isArray(e.commands)) {
          void runCommands(fromAgent(e.commands as Record<string, unknown>[])).then((n) =>
            notes.push(...n),
          );
        } else if (e.type === 'action_required') {
          if (e.action === 'connect_azure' || e.action === 'connect_mistral') {
            setConnectionsReason(typeof e.message === 'string' ? e.message : null);
            setConnectionsOpen(true);
          } else if (typeof e.message === 'string') {
            notes.push(e.message);
          }
        } else if (e.type === 'message' && typeof e.content === 'string' && e.content) {
          onProgress?.(e.content);
        } else if ((e.type === 'done' || e.type === 'end') && typeof e.content === 'string') {
          final = e.content;
        } else if (e.type === 'error' && typeof e.message === 'string') {
          final = `The planning agent stopped: ${e.message}`;
        }
      });
      // New profiles, layers or 3D models may exist now.
      await gw.reload().catch(() => undefined);
      api
        .models3d()
        .then(setModelIds)
        .catch(() => undefined);
      return [final || 'Done.', ...notes].join(' ');
    },
    [gw, runCommands],
  );

  /** "I want to build a nuclear plant" → planning agent; "thermal view" → fast commands. */
  const looksLikePlanning = (t: string) =>
    /\b(build|building|plan|planning|create|new use case|looking for|site for|where should)\b/i.test(
      t,
    ) && !gw.profileList.some((p) => t.toLowerCase().includes(p.label.toLowerCase()));

  const ask = useCallback(
    async (text: string, onProgress?: (msg: string) => void): Promise<string> => {
      if (looksLikePlanning(text)) {
        try {
          return await runPlanningAgent(text, onProgress);
        } catch (e) {
          if (!(e instanceof ApiError && e.status === 503)) throw e;
        }
      }
      const res = await api.assistant(text, {
        profile: gw.profile?.id ?? null,
        overlay: gw.overlayId,
        selected_h3: gw.selection?.h3 ?? null,
        site_ids: gw.sites.map((x) => x.id),
      });
      if (res.commands.length === 0) {
        try {
          return await runPlanningAgent(text, onProgress);
        } catch (e) {
          if (!(e instanceof ApiError && e.status === 503)) throw e;
        }
      }
      const notes = await runCommands(res.commands);
      return notes.length ? notes.join(' ') : res.reply;
    },
    [gw, runCommands, runPlanningAgent], // eslint-disable-line react-hooks/exhaustive-deps
  );

  // ---- structures (home screen)
  const openProject = useCallback(
    (p: Project) => {
      const prof = gw.profileList.find((x) => x.id === p.profile);
      if (!prof) return;
      gw.applyProfileWeights(p.profile, projectWeights(p, prof.layers));
      gw.setSelection(null);
      setView('overview');
      setProject(p);
      setScreen('explore');
      setGlobeVisible(true);
      setSpinning(false);
      // let the globe mount and start turning before the dive
      window.setTimeout(() => flyGlobe(51.5, -0.11, 'city'), 350);
    },
    [gw, flyGlobe],
  );

  const startDraw = useCallback(() => {
    setAreaError(null);
    setDraft([]);
    setPendingName(null);
    setPlacing(false);
    setDrawing(true);
  }, []);
  const cancelDraw = useCallback(() => {
    setDrawing(false);
    setDraft([]);
    setPendingName(null);
  }, []);
  const finishDraw = useCallback(() => {
    setDrawing(false);
    setDraft((d) => {
      if (d.length < 3) {
        setAreaError('An area needs at least three corners.');
        return [];
      }
      setPendingName('');
      return d;
    });
  }, []);
  const saveArea = useCallback(async () => {
    const name = (pendingName ?? '').trim() || `Area ${areas.length + 1}`;
    const ring = [...draft, draft[0]!];
    try {
      const a = await api.createArea(name, { type: 'Polygon', coordinates: [ring] });
      setAreas((as) => [a, ...as]);
      setSelectedAreaId(a.id);
      setView('area');
      setPendingName(null);
      setDraft([]);
      setAreaError(null);
    } catch (e) {
      setAreaError(e instanceof Error ? e.message : 'Could not save the area.');
    }
  }, [pendingName, draft, areas.length]);
  const selectArea = useCallback(
    (id: string) => {
      const a = areas.find((x) => x.id === id);
      if (!a) return;
      setSelectedAreaId(id);
      setView('area');
      const ring = a.geometry.coordinates[0] ?? [];
      const lon = ring.reduce((t, p) => t + p[0], 0) / Math.max(1, ring.length);
      const lat = ring.reduce((t, p) => t + p[1], 0) / Math.max(1, ring.length);
      goTo(lat, lon);
    },
    [areas, goTo],
  );
  const renameArea = useCallback((id: string, name: string) => {
    api
      .renameArea(id, name)
      .then((a) => setAreas((as) => as.map((x) => (x.id === id ? a : x))))
      .catch((e: unknown) => setAreaError(String((e as Error).message)));
  }, []);
  const deleteArea = useCallback((id: string) => {
    setAreas((as) => as.filter((x) => x.id !== id));
    setSelectedAreaId((cur) => (cur === id ? null : cur));
    api.deleteArea(id).catch(() => undefined);
  }, []);

  const voice = useVoice(ask);

  const selectedSite = gw.sites.find(
    (s) => s.h3 === gw.selection?.h3 && s.profile === gw.profile?.id,
  );
  const fallbackCell = scoreData?.cells.find((c) => c.h3 === gw.selection?.h3);
  const isMapLoading =
    gw.score.status === 'loading' || (!!overlay.layer && layerAsync?.status === 'loading');

  const bootError = gw.profiles.status === 'error' ? gw.profiles.message : null;

  return (
    <Layout
      header={
        <LayoutHeader hasDivider padding={0}>
          <TopBar
            legend={screen === 'explore' ? legend : null}
            onGlobe={() => {
              setScreen('explore');
              flyGlobe(51.5, -0.11, 'country');
            }}
            onHome={() => setScreen('home')}
            onConnections={() => {
              setConnectionsReason(null);
              setConnectionsOpen(true);
            }}
          />
          <ConnectionsDialog
            isOpen={connectionsOpen}
            onOpenChange={setConnectionsOpen}
            reason={connectionsReason}
          />
        </LayoutHeader>
      }
      start={
        screen === 'explore' && (
          <LayoutPanel width={340} hasDivider padding={4} label="Controls">
            <ControlPanel
              project={project}
              onEditProject={() => setScreen('home')}
              gw={gw}
              isPlacing={isPlacing}
              onTogglePlacing={() => setPlacing((p) => !p)}
              showMasked={showMasked}
              onShowMasked={setShowMasked}
              terrain={terrain}
              onTerrain={setTerrain}
              lowPower={lowPower}
              onOpenSite={openSite}
              onCompareSites={() => setView('compare-sites')}
              areas={
                <AreasPanel
                  areas={areas}
                  selectedId={selectedAreaId}
                  isDrawing={isDrawing}
                  draftPoints={draft.length}
                  pendingName={pendingName}
                  error={areaError}
                  onStartDraw={() => {
                    startDraw();
                    if (globeVisible) flyGlobe(51.5, -0.11, 'city');
                  }}
                  onCancelDraw={cancelDraw}
                  onFinishDraw={finishDraw}
                  onPendingName={setPendingName}
                  onSave={() => void saveArea()}
                  onSelect={selectArea}
                  onRename={renameArea}
                  onDelete={deleteArea}
                />
              }
            />
          </LayoutPanel>
        )
      }
      content={
        <LayoutContent padding={0} isScrollable={false} label={screen === 'home' ? 'Home' : 'Map'}>
          {screen === 'home' && (
            <HomeScreen
              profiles={gw.profileList}
              layersById={gw.layersById}
              projects={projects}
              onCreate={(p) => {
                void createProject(p).then(openProject);
              }}
              onOpen={openProject}
              onRemove={removeProject}
            />
          )}
          <VStack
            height="100%"
            style={{ position: 'relative', display: screen === 'home' ? 'none' : undefined }}
          >
            <MapView
              cells={cells}
              ramp={overlay.layer ? overlay.ramp : 'suitability'}
              showMasked={showMasked}
              selectedH3={gw.selection?.h3 ?? null}
              sites={siteRenders}
              relief={!!overlay.relief}
              terrain={terrain}
              lowPower={lowPower}
              isPlacing={isPlacing}
              focus={focus}
              onHexClick={onHexClick}
              onLowPower={() => setLowPower(true)}
              arrival={arrival}
              zoomCmd={mapZoom}
              pois={pois}
              isActive={screen === 'explore'}
              basemap={basemap}
              isDrawing={isDrawing}
              draft={draft}
              areas={mapAreas}
              selectedAreaId={selectedAreaId}
              onDrawPoint={(lon, lat) => setDraft((d) => [...d, [lon, lat]])}
              onDrawFinish={finishDraw}
              onAreaClick={selectArea}
            />
            {!globeVisible && (
              <HStack
                padding={4}
                style={{ position: 'absolute', insetInlineStart: 0, insetBlockEnd: 0, zIndex: 3 }}
              >
                <HStack
                  padding={1}
                  style={{
                    background: 'var(--color-background-card)',
                    borderRadius: 'var(--radius-container)',
                    boxShadow: 'var(--shadow-med)',
                  }}
                >
                  <SegmentedControl
                    label="Base map"
                    value={basemap}
                    onChange={(v) => setBasemap(v as Basemap)}
                    size="sm"
                  >
                    <SegmentedControlItem value="map" label="Map" />
                    <SegmentedControlItem value="satellite" label="Satellite" />
                    <SegmentedControlItem value="grid" label="Grid" />
                  </SegmentedControl>
                </HStack>
              </HStack>
            )}
            <GlobeView
              isVisible={globeVisible}
              isSpinning={spinning}
              target={globeTarget}
              zoom={globeZoom}
              regionHexes={regionHexes}
              notice={globeNotice}
              onArrive={onArrive}
              onEnterRegion={() => flyGlobe(51.5, -0.11, 'city')}
              onUserInteract={() => setSpinning(false)}
            />
            <HStack
              padding={4}
              justify="center"
              style={{
                position: 'absolute',
                insetInline: 0,
                insetBlockStart: 'var(--spacing-2)',
                zIndex: 3,
                pointerEvents: 'none',
              }}
            >
              <HStack
                padding={2}
                width="100%"
                maxWidth={600}
                style={{
                  pointerEvents: 'auto',
                  background: 'var(--color-background-card)',
                  borderRadius: 'var(--radius-container)',
                  boxShadow: 'var(--shadow-med)',
                }}
              >
                <CommandBar onSubmit={ask} />
              </HStack>
            </HStack>
            <HStack
              justify="center"
              paddingBlockEnd={4}
              style={{
                position: 'absolute',
                insetInline: 0,
                insetBlockEnd: 0,
                zIndex: 3,
                pointerEvents: 'none',
              }}
            >
              <VoiceDock
                state={voice.state}
                level={voice.level}
                message={voice.message}
                isAvailable={voice.engine !== null}
                onStart={voice.start}
                onStop={voice.stop}
              />
            </HStack>
            <VStack
              style={{
                position: 'absolute',
                insetInline: 0,
                insetBlockStart: 0,
                opacity: isMapLoading ? 1 : 0,
                transition: 'opacity 200ms',
                pointerEvents: 'none',
              }}
            >
              <ProgressBar label="Updating map" isLabelHidden isIndeterminate />
            </VStack>
            {(bootError || (gw.score.status === 'error' && !scoreData)) && (
              <VStack
                padding={4}
                style={{ position: 'absolute', insetInline: 0, insetBlockStart: 0 }}
              >
                <Banner
                  status="error"
                  title="The map has no data yet"
                  description={
                    bootError ?? (gw.score.status === 'error' ? gw.score.message : 'Unknown error')
                  }
                  collapsible={false}
                />
              </VStack>
            )}
          </VStack>
        </LayoutContent>
      }
      end={
        screen === 'explore' && (
          <LayoutPanel width={380} hasDivider padding={4} label="Details">
            {view === 'area' && selectedArea ? (
              <AreaDetail
                area={selectedArea}
                profileLabel={gw.profile?.label ?? null}
                summary={areaSummary}
                onBack={() => {
                  setSelectedAreaId(null);
                  setView('overview');
                }}
                onBest={(h3) => {
                  const [lat, lon] = cellToLatLng(h3);
                  select({ h3, lat, lon });
                  setFocus({ lat, lon, nonce: Date.now() });
                }}
              />
            ) : view === 'compare-sites' && gw.sites.length >= 2 ? (
              <SiteCompare
                sites={gw.sites}
                profiles={gw.profileList}
                profile={gw.profile}
                layersById={gw.layersById}
                onBack={() => setView('overview')}
              />
            ) : view === 'detail' && gw.selection ? (
              <CellDetail
                selection={gw.selection}
                profile={gw.profile}
                profiles={gw.profileList}
                layersById={gw.layersById}
                point={gw.point}
                compare={gw.compare}
                fallbackCell={fallbackCell}
                fallbackRank={{ rank: ranks.get(gw.selection.h3) ?? null, total: ranks.size }}
                site={selectedSite}
                heroActive={!!selectedSite && heroSiteId === selectedSite.id}
                onBack={() => {
                  gw.setSelection(null);
                  setView('overview');
                }}
                onPlace={() => gw.selection && gw.placeSite(gw.selection)}
                onChooseProfile={gw.chooseProfile}
              />
            ) : (
              <TopSites
                profiles={gw.profileList}
                onChooseProfile={gw.chooseProfile}
                profile={gw.profile}
                cells={scoreData?.cells}
                isLoading={gw.score.status === 'loading'}
                onPick={(c) => {
                  const [lat, lon] = cellToLatLng(c.h3);
                  select({ h3: c.h3, lat, lon });
                  setFocus({ lat, lon, nonce: Date.now() });
                }}
              />
            )}
          </LayoutPanel>
        )
      }
    />
  );
}
