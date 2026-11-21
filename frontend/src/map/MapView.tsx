import { MapboxOverlay } from '@deck.gl/mapbox';
import { H3HexagonLayer } from '@deck.gl/geo-layers';
import { IconLayer, PathLayer, PolygonLayer, ScatterplotLayer } from '@deck.gl/layers';
import type { PickingInfo } from '@deck.gl/core';
import { VStack } from '@astryxdesign/core/VStack';
import { cellToLatLng, polygonToCells } from 'h3-js';
import * as maplibregl from 'maplibre-gl';
import type { StyleSpecification } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { Poi } from '../api/types';
import { POI_LABEL, poiIconUrl } from './poiIcons';
import { MASKED_RGB, RAMPS, sample, type RampId } from '../lib/colour';
import { BuildingsLayer, type SiteRender } from './buildings';
import { GLOBE_ZOOM } from '../lib/viewport';
import { onLand, type LandMask } from '../lib/land';

export interface HexDatum {
  h3: string;
  /** Colour position 0–1. */
  t: number;
  /** Extrusion 0–1. */
  h: number;
  masked: boolean;
  tooltip: string;
  /** Covered by data but not scored yet (no use case chosen). */
  neutral?: boolean;
}

export interface MapFocus {
  lat: number;
  lon: number;
  nonce: number;
}

interface Props {
  cells: HexDatum[];
  ramp: RampId;
  showMasked: boolean;
  selectedH3: string | null;
  sites: SiteRender[];
  relief: boolean;
  terrain: boolean;
  lowPower: boolean;
  isPlacing: boolean;
  focus: MapFocus | null;
  onHexClick: (h3: string, lat: number, lon: number) => void;
  onLowPower: () => void;
  /** Set when the globe hands over: the map flies in to this point. */
  arrival: { lat: number; lon: number; nonce: number } | null;
  zoomCmd: { dir: 'in' | 'out'; nonce: number } | null;
  pois: Poi[];
  /** Land with data (from region marker cells): the surrounding grid is clipped to it. */
  landMask?: LandMask | null;
  /** Outlines of the regions with data, drawn while zoomed out past the hex threshold. */
  regionOutlines?: { name: string; bbox: [number, number, number, number] }[];
  /** False while hidden behind the home screen; the map resizes when it becomes visible. */
  isActive: boolean;
  basemap: Basemap;
  isDrawing: boolean;
  draft: [number, number][];
  areas: MapArea[];
  selectedAreaId: string | null;
  onDrawPoint: (lon: number, lat: number) => void;
  onDrawFinish: () => void;
  onAreaClick: (id: string) => void;
  /** Reports the camera after each move (for "already there" checks and agent context). */
  onView?: (v: {
    center: [number, number];
    zoom: number;
    bbox: [number, number, number, number];
  }) => void;
  /** The user zoomed out past the globe threshold: hand back to the globe at this point. */
  onZoomOut?: (lon: number, lat: number) => void;
}

export type Basemap = 'map' | 'satellite' | 'grid';

export interface MapArea {
  id: string;
  name: string;
  ring: [number, number][];
}

export const ELEVATION_SCALE = 1800;
/** Points of interest appear once the map is zoomed in past this level. */
export const POI_MIN_ZOOM = 10.8;
const CENTRE: [number, number] = [-0.11, 51.5];
const DEM_TILES = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png';
const STYLES = {
  light: 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',
  dark: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
};
const ACCENT: [number, number, number] = [118, 172, 255];
const SATELLITE_TILES =
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';

function satelliteStyle(): StyleSpecification {
  return {
    version: 8,
    sources: {
      satellite: {
        type: 'raster',
        tiles: [SATELLITE_TILES],
        tileSize: 256,
        maxzoom: 18,
        attribution: 'Imagery © Esri, Maxar, Earthstar Geographics',
      },
    },
    layers: [
      { id: 'background', type: 'background', paint: { 'background-color': '#0b0e12' } },
      // dimmed so hexes and icons stay readable
      {
        id: 'satellite',
        type: 'raster',
        source: 'satellite',
        paint: { 'raster-brightness-max': 0.7 },
      },
    ],
  };
}

function styleFor(b: Basemap): string | StyleSpecification {
  if (b === 'satellite') return satelliteStyle();
  if (b === 'grid') return fallbackStyle(true);
  return STYLES.dark;
}

/** H3 resolution for the surrounding grid at a zoom level (about 8–30 px per hex). */
function contextRes(zoom: number): number {
  if (zoom < 5) return 3;
  if (zoom < 6.5) return 4;
  if (zoom < 8) return 5;
  if (zoom < 9.3) return 6;
  if (zoom < 10.6) return 7;
  return 8;
}
const MAX_CONTEXT_CELLS = 7000;
const HOME = { zoom: 9.7, pitch: 50, bearing: -12 };

function fallbackStyle(dark: boolean): StyleSpecification {
  return {
    version: 8,
    sources: {},
    layers: [
      {
        id: 'background',
        type: 'background',
        paint: { 'background-color': dark ? '#16191d' : '#eef0f2' },
      },
    ],
  };
}

// The app is dark-only (Groundwork theme), so the basemap is too.
const prefersDark = () => true;
const prefersReducedMotion = () =>
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;

function addRelief(map: maplibregl.Map, relief: boolean, terrain: boolean) {
  if (!map.isStyleLoaded()) return;
  if (!map.getSource('dem')) {
    map.addSource('dem', {
      type: 'raster-dem',
      tiles: [DEM_TILES],
      tileSize: 256,
      encoding: 'terrarium',
      maxzoom: 13,
    });
  }
  const has = !!map.getLayer('hillshade');
  if (relief && !has) {
    const firstSymbol = map
      .getStyle()
      .layers.find((l: { type: string }) => l.type === 'symbol')?.id;
    map.addLayer(
      {
        id: 'hillshade',
        type: 'hillshade',
        source: 'dem',
        paint: { 'hillshade-exaggeration': 0.6, 'hillshade-shadow-color': '#3a3a3a' },
      },
      firstSymbol,
    );
  } else if (!relief && has) {
    map.removeLayer('hillshade');
  }
  map.setTerrain(terrain ? { source: 'dem', exaggeration: 1.5 } : null);
}

export function MapView(props: Props) {
  const containerRef = useRef<HTMLElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const buildingsRef = useRef<BuildingsLayer | null>(null);
  const propsRef = useRef(props);
  propsRef.current = props;
  const [showPois, setShowPois] = useState(false);
  const [viewport, setViewport] = useState<{
    bbox: [number, number, number, number];
    zoom: number;
  } | null>(null);

  // ---- one-time map setup
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const dark = prefersDark();
    const map = new maplibregl.Map({
      container: container as HTMLDivElement,
      style: styleFor(propsRef.current.basemap),
      center: CENTRE,
      zoom: 5.2,
      pitch: 0,
      bearing: 0,
      maxPitch: 70,
      minZoom: GLOBE_ZOOM - 1.2,
      pixelRatio: Math.min(window.devicePixelRatio, 2),
      attributionControl: { compact: true },
      canvasContextAttributes: { antialias: true },
    });
    mapRef.current = map;
    if (import.meta.env.DEV) (window as unknown as { __gwMap?: maplibregl.Map }).__gwMap = map;
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right');
    // Snappier zoom, calmer pan (user request): ~2× wheel/pinch zoom rate, ~0.6× pan inertia.
    map.scrollZoom.setWheelZoomRate(2 / 450);
    map.scrollZoom.setZoomRate(2 / 100);
    map.dragPan.enable({ linearity: 0.25, maxSpeed: 840, deceleration: 4200 });
    map.on('moveend', () => {
      const c = map.getCenter();
      const b = map.getBounds();
      propsRef.current.onView?.({
        center: [c.lng, c.lat],
        zoom: map.getZoom(),
        bbox: [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()],
      });
    });
    // Zooming out (wheel, pinch, buttons or a "zoom out" command) past the threshold returns
    // to the globe, every time. Camera moves made in code (fly-tos) don't count.
    // Checked on every zoom step (not only zoomend: at minZoom the wheel stops emitting one).
    // Scroll-zoom steps carry no originalEvent in MapLibre 5, so track user input directly.
    let lastInput = 0;
    const markInput = () => (lastInput = performance.now());
    for (const t of ['wheel', 'pointerdown', 'touchstart', 'keydown'] as const)
      map.getContainer().addEventListener(t, markInput, { passive: true, capture: true });
    let handedBack = false;
    const maybeHandBack = (e: { originalEvent?: unknown; gwUser?: boolean }) => {
      if (map.getZoom() >= GLOBE_ZOOM) {
        handedBack = false;
        return;
      }
      const byUser = !!(e.originalEvent || e.gwUser) || performance.now() - lastInput < 1500;
      if (handedBack || !byUser || !propsRef.current.isActive) return;
      handedBack = true;
      const c = map.getCenter();
      propsRef.current.onZoomOut?.(c.lng, c.lat);
    };
    map.on('zoom', maybeHandBack);
    map.on('zoomend', maybeHandBack);

    const overlay = new MapboxOverlay({ interleaved: true, layers: [] });
    overlayRef.current = overlay;
    map.addControl(overlay);

    map.on('zoom', () => setShowPois(map.getZoom() >= POI_MIN_ZOOM));
    const updateViewport = () => {
      const b = map.getBounds();
      setViewport({
        bbox: [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()],
        zoom: map.getZoom(),
      });
    };
    map.on('moveend', updateViewport);
    map.on('load', updateViewport);

    // ---- drawing an area: click to add points, double-click (or click the first point) to finish
    map.on('click', (e) => {
      if (!propsRef.current.isDrawing) return;
      const d = propsRef.current.draft;
      const first = d[0];
      if (first && d.length >= 3) {
        const p0 = map.project(first);
        if (Math.hypot(p0.x - e.point.x, p0.y - e.point.y) < 12) {
          propsRef.current.onDrawFinish();
          return;
        }
      }
      propsRef.current.onDrawPoint(e.lngLat.lng, e.lngLat.lat);
    });
    map.on('dblclick', (e) => {
      if (!propsRef.current.isDrawing) return;
      e.preventDefault();
      propsRef.current.onDrawFinish();
    });

    const buildings = new BuildingsLayer();
    buildingsRef.current = buildings;

    let loaded = false;
    const styleTimeout = window.setTimeout(() => {
      if (!loaded) map.setStyle(fallbackStyle(dark));
    }, 8000);
    map.on('error', (e: { error?: unknown }) => {
      // Basemap unreachable (offline demo): drop to a plain background, keep the hexes.
      const msg = String((e.error as Error | undefined)?.message ?? '');
      if (!loaded && propsRef.current.basemap === 'map' && /style|fetch|Failed/i.test(msg)) {
        map.setStyle(fallbackStyle(dark));
      }
    });
    map.on('style.load', () => {
      loaded = true;
      if (!map.getLayer(buildings.id)) map.addLayer(buildings);
      addRelief(map, propsRef.current.relief, propsRef.current.terrain);
    });

    // ---- frame-rate watchdog: degrade gracefully on slow GPUs
    let frames = 0;
    let start = 0;
    let slowStreak = 0;
    map.on('movestart', () => {
      frames = 0;
      start = performance.now();
    });
    map.on('render', () => {
      frames++;
    });
    map.on('moveend', () => {
      const secs = (performance.now() - start) / 1000;
      if (secs < 0.8) return;
      const fps = frames / secs;
      slowStreak = fps < 24 ? slowStreak + 1 : 0;
      if (slowStreak >= 2 && !propsRef.current.lowPower) propsRef.current.onLowPower();
    });

    return () => {
      window.clearTimeout(styleTimeout);
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // ---- hand-over from the globe
  useEffect(() => {
    const map = mapRef.current;
    const a = props.arrival;
    if (!map || !a) return;
    map.resize();
    // Start from a globe-like distance above the target so the hand-over reads as one zoom.
    const c = map.getCenter();
    if (Math.abs(c.lng - a.lon) > 2 || Math.abs(c.lat - a.lat) > 2 || map.getZoom() < GLOBE_ZOOM)
      map.jumpTo({ center: [a.lon, a.lat], zoom: 5, pitch: 0, bearing: 0 });
    map.flyTo({
      center: [a.lon, a.lat],
      ...HOME,
      zoom:
        Math.abs(a.lat - CENTRE[1]) < 0.3 && Math.abs(a.lon - CENTRE[0]) < 0.5 ? HOME.zoom : 10.8,
      duration: prefersReducedMotion() ? 0 : 2000,
      essential: false,
    });
  }, [props.arrival]);

  useEffect(() => {
    if (props.isActive) mapRef.current?.resize();
  }, [props.isActive]);

  // ---- basemap switch
  const firstBasemap = useRef(true);
  useEffect(() => {
    if (firstBasemap.current) {
      firstBasemap.current = false;
      return;
    }
    mapRef.current?.setStyle(styleFor(props.basemap));
  }, [props.basemap]);

  // ---- drawing mode: crosshair, no double-click zoom
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (props.isDrawing) map.doubleClickZoom.disable();
    else map.doubleClickZoom.enable();
    map.getCanvas().style.cursor = props.isDrawing || props.isPlacing ? 'crosshair' : '';
  }, [props.isDrawing, props.isPlacing]);

  // ---- surrounding grid: empty hexes around (and beyond) the scored region
  const dataIds = useMemo(() => new Set(props.cells.map((c) => c.h3)), [props.cells]);
  const contextCells = useMemo(() => {
    if (!viewport) return [];
    const res = contextRes(viewport.zoom);
    const [w, so, e, n] = viewport.bbox;
    const padX = (e - w) * 0.15;
    const padY = (n - so) * 0.15;
    const ring: [number, number][] = [
      [so - padY, w - padX],
      [so - padY, e + padX],
      [n + padY, e + padX],
      [n + padY, w - padX],
    ];
    let cells: string[] = [];
    try {
      cells = polygonToCells(ring, res);
    } catch {
      return [];
    }
    if (cells.length > MAX_CONTEXT_CELLS) return [];
    // Only where data exists: no empty hexes over the sea (user request).
    const mask = props.landMask;
    if (mask) cells = cells.filter((c) => onLand(c, mask));
    return res === 8 ? cells.filter((c) => !dataIds.has(c)) : cells;
  }, [viewport, dataIds, props.landMask]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !props.zoomCmd) return;
    if (props.zoomCmd.dir === 'in') map.zoomIn();
    else map.zoomOut(undefined, { gwUser: true });
  }, [props.zoomCmd]);

  // ---- relief / terrain
  useEffect(() => {
    const map = mapRef.current;
    if (map?.isStyleLoaded()) addRelief(map, props.relief, props.terrain && !props.lowPower);
  }, [props.relief, props.terrain, props.lowPower]);

  // ---- fly to focus
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !props.focus) return;
    map.easeTo({
      center: [props.focus.lon, props.focus.lat],
      zoom: Math.max(map.getZoom(), 11.2),
      duration: prefersReducedMotion() ? 0 : 900,
    });
  }, [props.focus]);

  // ---- buildings
  useEffect(() => {
    buildingsRef.current?.setSites(props.sites);
  }, [props.sites]);

  // ---- hex layer
  const visible = useMemo(
    () => (props.showMasked ? props.cells : props.cells.filter((c) => !c.masked)),
    [props.cells, props.showMasked],
  );

  // In low-power mode only the top quarter of hexes are extruded.
  const extrudeFloor = useMemo(() => {
    if (!props.lowPower) return -1;
    const hs = visible.map((c) => c.h).sort((a, b) => a - b);
    return hs[Math.floor(hs.length * 0.75)] ?? 0;
  }, [visible, props.lowPower]);

  useEffect(() => {
    const overlay = overlayRef.current;
    if (!overlay) return;
    const ramp = RAMPS[props.ramp];
    const selected = props.selectedH3;
    const reduced = prefersReducedMotion();
    const layer = new H3HexagonLayer<HexDatum>({
      id: 'hexes',
      data: visible,
      getHexagon: (d) => d.h3,
      extruded: true,
      highPrecision: false,
      coverage: 0.94,
      elevationScale: ELEVATION_SCALE,
      getElevation: (d) => (d.masked || d.h < extrudeFloor ? 0 : d.h),
      getFillColor: (d) => {
        if (d.h3 === selected) return [...ACCENT, 255];
        if (d.masked) return [...MASKED_RGB, 110];
        if (d.neutral) return [118, 130, 148, 120];
        return [...sample(ramp, d.t), 235];
      },
      material: { ambient: 0.6, diffuse: 0.55, shininess: 12, specularColor: [40, 40, 40] },
      pickable: true,
      autoHighlight: true,
      highlightColor: [255, 255, 255, 110],
      updateTriggers: {
        getFillColor: [props.ramp, selected, visible],
        getElevation: [visible, extrudeFloor],
      },
      transitions: reduced
        ? {}
        : {
            getElevation: { duration: 650, type: 'interpolation' },
            getFillColor: { duration: 450, type: 'interpolation' },
          },
      onClick: (info: PickingInfo<HexDatum>) => {
        if (!info.object || propsRef.current.isDrawing) return;
        const [lat, lon] = cellToLatLng(info.object.h3);
        propsRef.current.onHexClick(info.object.h3, lat, lon);
      },
      onHover: (info: PickingInfo<HexDatum>) => {
        const canvas = mapRef.current?.getCanvas();
        if (canvas && !propsRef.current.isPlacing && !propsRef.current.isDrawing) {
          canvas.style.cursor = info.object ? 'pointer' : '';
        }
      },
    });
    const poiLayer = new IconLayer<Poi>({
      id: 'pois',
      data: props.pois,
      visible: showPois,
      getPosition: (d) => [d.lon, d.lat, extrudeFloor >= 0 ? 0 : 0],
      getIcon: (d) => ({ url: poiIconUrl(d.kind), width: 64, height: 64, mask: false }),
      getSize: 26,
      sizeUnits: 'pixels',
      billboard: true,
      pickable: true,
      parameters: { depthCompare: 'always' },
      transitions: prefersReducedMotion() ? {} : { getSize: 200 },
    });
    const gridStrength = props.basemap === 'grid' ? 70 : 26;
    const contextLayer = new H3HexagonLayer<string>({
      id: 'context-grid',
      data: contextCells,
      getHexagon: (d) => d,
      filled: false,
      stroked: true,
      extruded: false,
      highPrecision: false,
      getLineColor: [255, 255, 255, gridStrength],
      lineWidthMinPixels: 1,
      lineWidthMaxPixels: 1,
      pickable: false,
    });
    const areaLayer = new PolygonLayer<MapArea>({
      id: 'areas',
      data: props.areas,
      getPolygon: (d) => d.ring,
      filled: true,
      stroked: true,
      getFillColor: (d) => [...ACCENT, d.id === props.selectedAreaId ? 46 : 22],
      getLineColor: [...ACCENT, 230],
      getLineWidth: (d) => (d.id === props.selectedAreaId ? 3 : 1.5),
      lineWidthUnits: 'pixels',
      pickable: !props.isDrawing,
      parameters: { depthCompare: 'always' },
      updateTriggers: { getFillColor: props.selectedAreaId, getLineWidth: props.selectedAreaId },
      onClick: (info: PickingInfo<MapArea>) => {
        if (info.object && !propsRef.current.isDrawing)
          propsRef.current.onAreaClick(info.object.id);
        return true;
      },
    });
    const draftPath = props.draft.length
      ? [...props.draft, ...(props.draft.length > 2 ? [props.draft[0]!] : [])]
      : [];
    const draftLayers = props.isDrawing
      ? [
          new PathLayer<[number, number][]>({
            id: 'draft-path',
            data: draftPath.length > 1 ? [draftPath] : [],
            getPath: (d) => d,
            getColor: [...ACCENT, 255],
            getWidth: 2,
            widthUnits: 'pixels',
            parameters: { depthCompare: 'always' },
          }),
          new ScatterplotLayer<[number, number]>({
            id: 'draft-points',
            data: props.draft,
            getPosition: (d) => d,
            getRadius: (_d, { index }) => (index === 0 ? 7 : 5),
            radiusUnits: 'pixels',
            getFillColor: (_d, { index }) =>
              index === 0 ? [...ACCENT, 255] : [255, 255, 255, 255],
            getLineColor: [...ACCENT, 255],
            stroked: true,
            lineWidthMinPixels: 2,
            parameters: { depthCompare: 'always' },
          }),
        ]
      : [];
    const outlines = props.regionOutlines ?? [];
    const outlineLayer = new PathLayer<{ name: string; bbox: [number, number, number, number] }>({
      id: 'region-outlines',
      data: outlines,
      getPath: ({ bbox: [w, so, e, n] }) => [[w, so], [e, so], [e, n], [w, n], [w, so]],
      getColor: [...ACCENT, 200],
      getWidth: 1.5,
      widthUnits: 'pixels',
      visible: outlines.length > 0,
      parameters: { depthCompare: 'always' },
    }); // prettier-ignore
    overlay.setProps({
      layers: [contextLayer, layer, areaLayer, outlineLayer, poiLayer, ...draftLayers],
      getTooltip: ({ object }: PickingInfo<HexDatum | Poi | MapArea>) =>
        object && !propsRef.current.isDrawing
          ? {
              text:
                'kind' in object
                  ? `${POI_LABEL[object.kind]}: ${object.name}\n${object.source}`
                  : 'ring' in object
                    ? object.name
                    : object.tooltip,
              style: {
                fontFamily: 'var(--font-family-body, system-ui)',
                fontSize: '13px',
                fontVariantNumeric: 'tabular-nums',
                background: 'var(--color-background-card, #fff)',
                color: 'var(--color-text-primary, #111)',
                border: '1px solid var(--color-border, #ddd)',
                borderRadius: 'var(--radius-element, 6px)',
                padding: '6px 8px',
              },
            }
          : null,
    });
  }, [
    visible,
    props.ramp,
    props.selectedH3,
    extrudeFloor,
    props.pois,
    showPois,
    contextCells,
    props.basemap,
    props.areas,
    props.selectedAreaId,
    props.draft,
    props.isDrawing,
    props.regionOutlines,
  ]);

  return (
    <VStack
      ref={containerRef}
      width="100%"
      height="100%"
      style={{ position: 'absolute', inset: 0 }}
      aria-label="3D map of London hexagons. Click a hexagon for details."
      role="application"
    />
  );
}
