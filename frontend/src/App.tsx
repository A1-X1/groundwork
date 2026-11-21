import { Banner } from '@astryxdesign/core/Banner';
import { Layout, LayoutContent, LayoutHeader, LayoutPanel } from '@astryxdesign/core/Layout';
import { ProgressBar } from '@astryxdesign/core/ProgressBar';
import { VStack } from '@astryxdesign/core/VStack';
import { cellToLatLng } from 'h3-js';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { flushSync } from 'react-dom';
import { formatRaw, formatScore } from './lib/format';
import { overlayFor } from './lib/overlays';
import { kindForProfile, type SiteRender } from './map/buildings';
import { ELEVATION_SCALE, MapView, type HexDatum, type MapFocus } from './map/MapView';
import { ControlPanel } from './panels/ControlPanel';
import { CellDetail, SiteCompare, TopSites } from './panels/DetailPanel';
import { TopBar, type LegendSpec } from './panels/TopBar';
import { useGroundwork, type PlacedSite, type Selection } from './state/useGroundwork';

type RightView = 'overview' | 'detail' | 'compare-sites';

export default function App() {
  const gw = useGroundwork();
  const [view, setView] = useState<RightView>('overview');
  const [isPlacing, setPlacing] = useState(false);
  const [showMasked, setShowMasked] = useState(true);
  const [terrain, setTerrain] = useState(false);
  const [lowPower, setLowPower] = useState(false);
  const [focus, setFocus] = useState<MapFocus | null>(null);
  const [heroSiteId, setHeroSiteId] = useState<string | null>(null);

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

  // ---- hexes for the map
  const cells: HexDatum[] = useMemo(() => {
    if (!scoreData) return [];
    if (!overlay.layer) {
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
    const maskedSet = new Set(scoreData.cells.filter((c) => c.masked).map((c) => c.h3));
    return layerAsync.data.cells.map((c) => ({
      h3: c.h3,
      t: c.value,
      h: c.value,
      masked: maskedSet.has(c.h3),
      tooltip: `${layerMeta?.label ?? overlay.label}: ${formatRaw(c.raw, layerMeta?.unit ?? '')}`,
    }));
  }, [scoreData, overlay.layer, overlay.label, layerAsync, layerMeta, ranks]);

  const legend: LegendSpec | null = overlay.layer
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
  const siteRenders: SiteRender[] = useMemo(
    () =>
      gw.sites.map((s) => ({
        id: s.id,
        kind: kindForProfile(s.profile),
        lat: s.lat,
        lon: s.lon,
        baseHeight: heightOf(s.h3),
        isSelected: gw.selection?.h3 === s.h3,
      })),
    [gw.sites, gw.selection, heightOf],
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
          <TopBar legend={legend} />
        </LayoutHeader>
      }
      start={
        <LayoutPanel width={340} hasDivider padding={4} label="Controls">
          <ControlPanel
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
          />
        </LayoutPanel>
      }
      content={
        <LayoutContent padding={0} isScrollable={false} label="Map">
          <VStack height="100%" style={{ position: 'relative' }}>
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
            />
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
        <LayoutPanel width={380} hasDivider padding={4} label="Details">
          {view === 'compare-sites' && gw.sites.length >= 2 ? (
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
      }
    />
  );
}
