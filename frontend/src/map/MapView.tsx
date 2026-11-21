import { MapboxOverlay } from '@deck.gl/mapbox';
import { H3HexagonLayer } from '@deck.gl/geo-layers';
import type { PickingInfo } from '@deck.gl/core';
import { VStack } from '@astryxdesign/core/VStack';
import { cellToLatLng } from 'h3-js';
import * as maplibregl from 'maplibre-gl';
import type { StyleSpecification } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { useEffect, useMemo, useRef } from 'react';
import { MASKED_RGB, RAMPS, sample, type RampId } from '../lib/colour';
import { BuildingsLayer, type SiteRender } from './buildings';

export interface HexDatum {
  h3: string;
  /** Colour position 0–1. */
  t: number;
  /** Extrusion 0–1. */
  h: number;
  masked: boolean;
  tooltip: string;
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
}

export const ELEVATION_SCALE = 1800;
const CENTRE: [number, number] = [-0.11, 51.5];
const DEM_TILES = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png';
const STYLES = {
  light: 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',
  dark: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
};
const ACCENT: [number, number, number] = [47, 111, 94];

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

const prefersDark = () => window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;
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

  // ---- one-time map setup
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let dark = prefersDark();
    const map = new maplibregl.Map({
      container: container as HTMLDivElement,
      style: STYLES[dark ? 'dark' : 'light'],
      center: CENTRE,
      zoom: 9.7,
      pitch: 50,
      bearing: -12,
      maxPitch: 70,
      pixelRatio: Math.min(window.devicePixelRatio, 2),
      attributionControl: { compact: true },
      canvasContextAttributes: { antialias: true },
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right');

    const overlay = new MapboxOverlay({ interleaved: true, layers: [] });
    overlayRef.current = overlay;
    map.addControl(overlay);

    const buildings = new BuildingsLayer();
    buildingsRef.current = buildings;

    let loaded = false;
    const styleTimeout = window.setTimeout(() => {
      if (!loaded) map.setStyle(fallbackStyle(dark));
    }, 8000);
    map.on('error', (e: { error?: unknown }) => {
      // Basemap unreachable (offline demo): drop to a plain background, keep the hexes.
      const msg = String((e.error as Error | undefined)?.message ?? '');
      if (!loaded && /style|fetch|Failed/i.test(msg)) map.setStyle(fallbackStyle(dark));
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

    const mq = window.matchMedia?.('(prefers-color-scheme: dark)');
    const onScheme = () => {
      dark = mq.matches;
      map.setStyle(STYLES[dark ? 'dark' : 'light']);
    };
    mq?.addEventListener('change', onScheme);

    return () => {
      window.clearTimeout(styleTimeout);
      mq?.removeEventListener('change', onScheme);
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // ---- relief / terrain
  useEffect(() => {
    const map = mapRef.current;
    if (map?.isStyleLoaded()) addRelief(map, props.relief, props.terrain && !props.lowPower);
  }, [props.relief, props.terrain, props.lowPower]);

  // ---- cursor in placing mode
  useEffect(() => {
    const canvas = mapRef.current?.getCanvas();
    if (canvas) canvas.style.cursor = props.isPlacing ? 'crosshair' : '';
  }, [props.isPlacing]);

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
        if (!info.object) return;
        const [lat, lon] = cellToLatLng(info.object.h3);
        propsRef.current.onHexClick(info.object.h3, lat, lon);
      },
      onHover: (info: PickingInfo<HexDatum>) => {
        const canvas = mapRef.current?.getCanvas();
        if (canvas && !propsRef.current.isPlacing) {
          canvas.style.cursor = info.object ? 'pointer' : '';
        }
      },
    });
    overlay.setProps({
      layers: [layer],
      getTooltip: ({ object }: PickingInfo<HexDatum>) =>
        object
          ? {
              text: object.tooltip,
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
  }, [visible, props.ramp, props.selectedH3, extrudeFloor]);

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
