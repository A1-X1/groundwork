/**
 * Street-level imagery for a hexagon (user request): a preview image in the detail panel that
 * opens a full-screen viewer you can move around in. Google Street View when a Google Maps key
 * is set on the server, else Mapillary; the API picks and proxies the preview.
 */
import { Button } from '@astryxdesign/core/Button';
import { HStack } from '@astryxdesign/core/HStack';
import { Icon } from '@astryxdesign/core/Icon';
import { IconButton } from '@astryxdesign/core/IconButton';
import { Link } from '@astryxdesign/core/Link';
import { Skeleton } from '@astryxdesign/core/Skeleton';
import { StatusDot } from '@astryxdesign/core/StatusDot';
import { Text } from '@astryxdesign/core/Text';
import { TextInput } from '@astryxdesign/core/TextInput';
import { VStack } from '@astryxdesign/core/VStack';
import { Camera, X } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api, type StreetViewConfig } from '../api/client';

// ---------------------------------------------------------------- shared config

let configPromise: Promise<StreetViewConfig> | null = null;
export function streetViewConfig(refresh = false): Promise<StreetViewConfig> {
  if (refresh || !configPromise)
    configPromise = api.streetViewConfig().catch(() => ({ provider: null }) as StreetViewConfig);
  return configPromise;
}

// ---------------------------------------------------------------- preview (detail panel)

type PreviewState =
  | { status: 'loading' }
  | { status: 'ready'; url: string; panoId: string | null; credit: string }
  | { status: 'none' }
  | { status: 'off' }
  | { status: 'error'; message: string };

export function StreetPreview({ lat, lon }: { lat: number; lon: number }) {
  const [state, setState] = useState<PreviewState>({ status: 'loading' });
  const [config, setConfig] = useState<StreetViewConfig | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    let url: string | null = null;
    setState({ status: 'loading' });
    void streetViewConfig().then(async (cfg) => {
      if (!alive) return;
      setConfig(cfg);
      if (!cfg.provider) return setState({ status: 'off' });
      try {
        const r = await api.streetViewPreview(lat, lon);
        if (!alive) return;
        if (r === null) return setState({ status: 'none' });
        url = URL.createObjectURL(r.blob);
        setState({ status: 'ready', url, panoId: r.panoId, credit: r.credit });
      } catch (e) {
        if (alive)
          setState({ status: 'error', message: e instanceof Error ? e.message : 'Failed.' });
      }
    });
    return () => {
      alive = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [lat, lon]);

  if (state.status === 'off') return null; // no provider: nothing to show (Connections adds one)
  return (
    <VStack gap={2}>
      {state.status === 'loading' && <Skeleton height={180} />}
      {state.status === 'none' && (
        <Text type="supporting" color="secondary">
          No street imagery here (nothing within 200 m).
        </Text>
      )}
      {state.status === 'error' && (
        <Text type="supporting" color="secondary">
          Street imagery unavailable: {state.message}
        </Text>
      )}
      {state.status === 'ready' && (
        <>
          <Button
            label="Open street view"
            variant="ghost"
            onClick={() => setOpen(true)}
            style={{
              padding: 0,
              height: 'auto',
              borderRadius: 'var(--radius-element)',
              overflow: 'hidden',
            }}
          >
            <img
              src={state.url}
              alt="Street-level view near this hexagon. Click to look around."
              width="100%"
              style={{ display: 'block', aspectRatio: '16 / 9', objectFit: 'cover', width: '100%' }}
            />
          </Button>
          <HStack justify="between" align="center">
            <Text type="supporting" color="secondary">
              {state.credit}
            </Text>
            <Button
              label="Look around"
              size="sm"
              variant="secondary"
              icon={<Icon icon={Camera} size="sm" />}
              onClick={() => setOpen(true)}
            />
          </HStack>
        </>
      )}
      {open && config?.provider && state.status === 'ready' && (
        <StreetViewer
          provider={config.provider}
          browserKey={config.browser_key ?? ''}
          lat={lat}
          lon={lon}
          panoId={state.panoId}
          credit={state.credit}
          onClose={() => setOpen(false)}
        />
      )}
    </VStack>
  );
}

// ---------------------------------------------------------------- full-screen viewer

const loaded = new Map<string, Promise<void>>();
function loadScript(src: string): Promise<void> {
  let p = loaded.get(src);
  if (!p) {
    p = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = src;
      s.async = true;
      s.onload = () => resolve();
      s.onerror = () => reject(new Error(`Couldn't load ${new URL(src).host}`));
      document.head.appendChild(s);
    });
    loaded.set(src, p);
  }
  return p;
}
function loadCss(href: string) {
  if (document.querySelector(`link[href="${href}"]`)) return;
  const l = document.createElement('link');
  l.rel = 'stylesheet';
  l.href = href;
  document.head.appendChild(l);
}

const MAPILLARY_JS = 'https://unpkg.com/mapillary-js@4.1.2/dist/mapillary.js';
const MAPILLARY_CSS = 'https://unpkg.com/mapillary-js@4.1.2/dist/mapillary.css';

interface ViewerProps {
  provider: 'google' | 'mapillary';
  browserKey: string;
  lat: number;
  lon: number;
  panoId: string | null;
  credit: string;
  onClose: () => void;
}

/* eslint-disable @typescript-eslint/no-explicit-any -- third-party globals loaded at runtime */
export function StreetViewer({
  provider,
  browserKey,
  lat,
  lon,
  panoId,
  credit,
  onClose,
}: ViewerProps) {
  const hostRef = useRef<HTMLElement | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  useEffect(() => {
    const el = hostRef.current;
    if (!el) return;
    let viewer: any = null;
    let alive = true;
    (async () => {
      try {
        if (provider === 'google') {
          await loadScript(
            `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(browserKey)}&v=weekly`,
          );
          const g = (window as any).google;
          if (!alive) return;
          viewer = new g.maps.StreetViewPanorama(el, {
            position: { lat, lng: lon },
            pov: { heading: 0, pitch: 0 },
            zoom: 1,
            addressControl: true,
            fullscreenControl: false,
            motionTracking: false,
          });
          if (panoId) viewer.setPano(panoId);
        } else {
          loadCss(MAPILLARY_CSS);
          await loadScript(MAPILLARY_JS);
          const m = (window as any).mapillary;
          if (!alive || !panoId) return;
          viewer = new m.Viewer({ accessToken: browserKey, container: el, imageId: panoId });
        }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : 'The viewer failed to load.');
      }
    })();
    return () => {
      alive = false;
      viewer?.remove?.();
    };
  }, [provider, browserKey, lat, lon, panoId]);

  return (
    <VStack
      role="dialog"
      aria-modal="true"
      aria-label="Street view"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 50,
        background: 'var(--color-background-body)',
      }}
    >
      <VStack ref={hostRef} style={{ position: 'absolute', inset: 0 }} />
      {error && (
        <VStack align="center" justify="center" style={{ position: 'absolute', inset: 0 }}>
          <Text color="secondary">{error}</Text>
        </VStack>
      )}
      <HStack
        gap={2}
        align="center"
        padding={2}
        style={{
          position: 'absolute',
          insetBlockStart: 'var(--spacing-4)',
          insetInlineEnd: 'var(--spacing-4)',
          borderRadius: 'var(--radius-full)',
          background: 'var(--color-background-card)',
          border: '1px solid var(--color-border)',
          boxShadow: 'var(--shadow-high)',
        }}
      >
        <Text type="supporting" color="secondary">
          {credit} · arrows or drag to move
        </Text>
        <IconButton
          label="Close street view"
          icon={<Icon icon={X} size="sm" />}
          variant="secondary"
          size="sm"
          onClick={onClose}
        />
      </HStack>
    </VStack>
  );
}
/* eslint-enable @typescript-eslint/no-explicit-any */

// ---------------------------------------------------------------- Connections rows

export function StreetViewConnections() {
  const [cfg, setCfg] = useState<StreetViewConfig | null>(null);
  const [which, setWhich] = useState<'google' | 'mapillary' | null>(null);
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(() => void streetViewConfig(true).then(setCfg), []);
  useEffect(refresh, [refresh]);

  const save = async () => {
    if (!which || !key.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setCfg(await api.saveStreetViewKey(which, key.trim()));
      configPromise = null;
      setKey('');
      setWhich(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save the key.');
    } finally {
      setBusy(false);
    }
  };

  if (!cfg) return <Skeleton height={80} />;
  const connected = cfg.provider !== null;
  return (
    <VStack gap={3}>
      <HStack gap={3} align="center">
        <Icon icon={Camera} size="lg" />
        <VStack gap={0.5}>
          <HStack gap={2} align="center">
            <Text weight="semibold">Street view</Text>
            <StatusDot
              variant={connected ? 'success' : 'neutral'}
              label={
                connected
                  ? `Connected: ${cfg.provider === 'google' ? 'Google' : 'Mapillary'}`
                  : 'Not connected'
              }
            />
          </HStack>
          <Text type="supporting" color="secondary" textWrap="pretty">
            Street-level previews when you click a hexagon. Google Street View, or free Mapillary.
          </Text>
        </VStack>
      </HStack>
      {which ? (
        <VStack gap={2}>
          <TextInput
            label={which === 'google' ? 'Google Maps API key' : 'Mapillary client token'}
            type="password"
            autoComplete="off"
            value={key}
            onChange={(v: string) => setKey(v)}
            onKeyDown={(e) => e.key === 'Enter' && void save()}
            hasAutoFocus
          />
          <Text type="supporting" color="secondary" display="block" textWrap="pretty">
            {which === 'google' ? (
              <>
                Enable the Maps JavaScript API and Street View Static API at{' '}
                <Link href="https://console.cloud.google.com/google/maps-apis" isExternalLink>
                  Google Cloud
                </Link>
                . Restrict the key to your site. It's kept in the server's .env.
              </>
            ) : (
              <>
                Free: create an app at{' '}
                <Link href="https://www.mapillary.com/dashboard/developers" isExternalLink>
                  mapillary.com
                </Link>{' '}
                and copy its client token. It's kept in the server's .env.
              </>
            )}
          </Text>
          {error && (
            <Text type="supporting" color="secondary">
              {error}
            </Text>
          )}
          <HStack gap={2}>
            <Button
              label="Save key"
              variant="primary"
              isDisabled={!key.trim()}
              isLoading={busy}
              onClick={() => void save()}
            />
            <Button label="Cancel" variant="ghost" onClick={() => setWhich(null)} />
          </HStack>
        </VStack>
      ) : (
        <HStack gap={2} wrap="wrap">
          <Button
            label="Add Google Maps key"
            variant="secondary"
            size="sm"
            onClick={() => setWhich('google')}
          />
          <Button
            label="Add Mapillary token"
            variant="secondary"
            size="sm"
            onClick={() => setWhich('mapillary')}
          />
          {connected && cfg.provider && (
            <Button
              label="Disconnect"
              variant="ghost"
              size="sm"
              onClick={() =>
                void api.deleteStreetViewKey(cfg.provider!).then((c) => {
                  configPromise = null;
                  setCfg(c);
                })
              }
            />
          )}
        </HStack>
      )}
    </VStack>
  );
}
