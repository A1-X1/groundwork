import { Banner } from '@astryxdesign/core/Banner';
import { Button } from '@astryxdesign/core/Button';
import { Collapsible } from '@astryxdesign/core/Collapsible';
import { Heading } from '@astryxdesign/core/Heading';
import { Icon } from '@astryxdesign/core/Icon';
import { HStack } from '@astryxdesign/core/HStack';
import { IconButton } from '@astryxdesign/core/IconButton';
import { List, ListItem } from '@astryxdesign/core/List';
import { MetadataList, MetadataListItem } from '@astryxdesign/core/MetadataList';
import { Selector } from '@astryxdesign/core/Selector';
import { Skeleton } from '@astryxdesign/core/Skeleton';
import { Table } from '@astryxdesign/core/Table';
import { Text } from '@astryxdesign/core/Text';
import { VStack } from '@astryxdesign/core/VStack';
import { ArrowLeft, MapPin } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { CompareResponse, LayerMeta, PointScore, Profile, ScoredCell } from '../api/types';
import { api } from '../api/client';
import { DIVERGING } from '../lib/colour';
import { formatPercent, formatRank, formatRaw, formatScore, formatSigned } from '../lib/format';
import type { Async, PlacedSite, Selection } from '../state/useGroundwork';

const STAGGER_MS = 30;

// ---------------------------------------------------------------- diverging bars

function DivergingBars({
  values,
  labelFor,
  limit = 8,
  format = formatSigned,
}: {
  values: Record<string, number>;
  labelFor: (id: string) => string;
  limit?: number;
  format?: (v: number) => string;
}) {
  const entries = Object.entries(values)
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
    .slice(0, limit);
  const max = Math.max(1e-6, ...entries.map(([, v]) => Math.abs(v)));
  return (
    <VStack gap={2} as="ul" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
      {entries.map(([id, v], i) => {
        const pct = (Math.abs(v) / max) * 50;
        return (
          <VStack
            as="li"
            key={id}
            gap={1}
            className="gw-stagger"
            style={{ animationDelay: `${i * STAGGER_MS}ms` }}
          >
            <HStack justify="between" gap={2}>
              <Text maxLines={1}>{labelFor(id)}</Text>
              <Text hasTabularNumbers color="secondary">
                {format(v)}
              </Text>
            </HStack>
            <HStack
              height={8}
              aria-hidden
              style={{
                position: 'relative',
                background: 'var(--color-background-muted)',
                borderRadius: 'var(--radius-inner)',
              }}
            >
              <HStack
                style={{
                  position: 'absolute',
                  insetBlock: 0,
                  insetInlineStart: v >= 0 ? '50%' : `${50 - pct}%`,
                  width: `${pct}%`,
                  background: v >= 0 ? DIVERGING.positive : DIVERGING.negative,
                  borderRadius: 'var(--radius-inner)',
                  transition: 'width 300ms ease, inset-inline-start 300ms ease',
                }}
              />
            </HStack>
          </VStack>
        );
      })}
    </VStack>
  );
}

// ---------------------------------------------------------------- overview

export function TopSites({
  profile,
  cells,
  isLoading,
  onPick,
}: {
  profile: Profile | undefined;
  cells: ScoredCell[] | undefined;
  isLoading: boolean;
  onPick: (cell: ScoredCell, rank: number) => void;
}) {
  const ranked = (cells ?? [])
    .filter((c) => c.score != null)
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  const masked = (cells ?? []).filter((c) => c.masked).length;
  return (
    <VStack gap={4}>
      <VStack gap={1}>
        <Heading level={2} textWrap="balance">
          Best {profile?.label.toLowerCase() ?? ''} sites in London
        </Heading>
        {cells ? (
          <Text color="secondary" display="block" hasTabularNumbers textWrap="pretty">
            {ranked.length.toLocaleString('en-GB')} hexagons scored,{' '}
            {masked.toLocaleString('en-GB')} ruled out by no-go masks.
          </Text>
        ) : (
          <Skeleton height={20} width="80%" />
        )}
      </VStack>
      {!cells && isLoading ? (
        <VStack gap={2}>
          {Array.from({ length: 10 }, (_, i) => (
            <Skeleton key={i} height={44} index={i} />
          ))}
        </VStack>
      ) : (
        <List density="compact" edge="outset" hasDividers>
          {ranked.slice(0, 10).map((c, i) => (
            <ListItem
              key={c.h3}
              label={<Text hasTabularNumbers>Score {formatScore(c.score)}</Text>}
              description={
                <Text type="code" color="secondary">
                  {c.h3}
                </Text>
              }
              startContent={
                <Text hasTabularNumbers weight="semibold" color="secondary">
                  {String(i + 1).padStart(2, '0')}
                </Text>
              }
              onClick={() => onPick(c, i + 1)}
            />
          ))}
        </List>
      )}
      <Text type="supporting" color="secondary" display="block" textWrap="pretty">
        Click a hexagon or a row to see why it scores the way it does.
      </Text>
    </VStack>
  );
}

// ---------------------------------------------------------------- cell detail

interface DetailProps {
  selection: Selection;
  profile: Profile | undefined;
  profiles: Profile[];
  layersById: Map<string, LayerMeta>;
  point: Async<PointScore>;
  compare: Async<CompareResponse>;
  fallbackCell: ScoredCell | undefined;
  fallbackRank: { rank: number | null; total: number };
  site: PlacedSite | undefined;
  heroActive: boolean;
  onBack: () => void;
  onPlace: () => void;
  onChooseProfile: (id: string) => void;
}

export function CellDetail(p: DetailProps) {
  const labelFor = (id: string) => p.layersById.get(id)?.label ?? id;
  const data = p.point.status === 'ready' ? p.point.data : undefined;
  const loading = p.point.status === 'loading';
  const score = data?.score ?? p.fallbackCell?.score ?? null;
  const masked = data?.masked ?? p.fallbackCell?.masked ?? false;
  const breakdown = data?.breakdown ?? p.fallbackCell?.breakdown ?? {};
  const rank = data ? { rank: data.rank, total: data.ranked_cells } : p.fallbackRank;
  const percentile = data?.percentile;
  const hitMasks = data?.masks ?? [];
  const shapValues = data?.shap
    ? Object.fromEntries(
        [...data.shap.positive, ...data.shap.negative].map((d) => [d.layer, d.value / 10]),
      )
    : null;
  const profileLayerIds = new Set(p.profile?.layers.map((l) => l.id));
  const rawEntries = Object.entries(data?.raw ?? {});
  const title = p.site?.name ?? `${p.profile?.label ?? 'Site'} at this hexagon`;

  return (
    <VStack gap={6} paddingBlockEnd={6}>
      <VStack gap={2}>
        <HStack gap={1} align="center">
          <IconButton
            label="Back to best sites"
            icon={<Icon icon={ArrowLeft} size="sm" />}
            variant="ghost"
            size="sm"
            onClick={p.onBack}
          />
          <Text type="code" color="secondary">
            {p.selection.h3}
          </Text>
        </HStack>
        <Heading
          level={2}
          textWrap="balance"
          style={p.heroActive ? { viewTransitionName: 'site-hero' } : undefined}
        >
          {title}
        </Heading>
        <HStack gap={3} align="end">
          <Text type="display-2" hasTabularNumbers weight="semibold">
            {masked ? 'No-go' : formatScore(score)}
          </Text>
          {!masked && (
            <Text color="secondary" hasTabularNumbers>
              / 100 · rank {formatRank(rank.rank, rank.total)}
              {percentile != null && ` · beats ${formatPercent(percentile)}`}
            </Text>
          )}
        </HStack>
        {data?.model && data.feasibility != null && data.sustainability != null && (
          <Text color="secondary" display="block" hasTabularNumbers textWrap="pretty">
            Weighted score {formatScore(data.sustainability)} × model feasibility{' '}
            {data.feasibility.toFixed(2)}
          </Text>
        )}
      </VStack>

      {masked && (
        <Banner
          status="warning"
          title="Ruled out by a hard mask"
          description={
            hitMasks.length
              ? `This hexagon is inside: ${hitMasks.map(labelFor).join(', ')}.`
              : 'This hexagon falls inside one of the profile’s no-go areas.'
          }
          collapsible={false}
        />
      )}

      <Button
        label={p.site ? 'Placed here' : `Place ${p.profile?.label.toLowerCase() ?? 'site'} here`}
        variant="primary"
        icon={<Icon icon={MapPin} size="sm" />}
        isDisabled={!!p.site}
        onClick={p.onPlace}
        width="100%"
      />

      {!masked && (
        <VStack gap={3}>
          <Heading level={3}>Why this score</Heading>
          <Text color="secondary" display="block" textWrap="pretty">
            Each layer’s pull relative to the London average, in score points.
          </Text>
          {Object.keys(breakdown).length ? (
            <DivergingBars values={breakdown} labelFor={labelFor} />
          ) : (
            <Skeleton height={160} />
          )}
        </VStack>
      )}

      {shapValues && Object.keys(shapValues).length > 0 && (
        <VStack gap={3}>
          <Heading level={3}>What the model sees</Heading>
          <Text color="secondary" display="block" textWrap="pretty">
            {data?.model?.note ??
              'The feasibility model learns where similar sites have been built, not where they should be.'}
          </Text>
          <DivergingBars
            values={shapValues}
            labelFor={labelFor}
            limit={10}
            format={(v) => `${v >= 0 ? '+' : '−'}${Math.abs(v * 10).toFixed(2)}`}
          />
          {data?.model && (
            <Text type="supporting" color="secondary" display="block" hasTabularNumbers>
              Trained on {data.model.n_positives ?? '?'}
              {data.model.positives_synthetic ? ' synthetic' : ''} examples
              {data.model.auc_spatial_cv != null &&
                ` · spatial CV AUC ${data.model.auc_spatial_cv.toFixed(2)}`}
            </Text>
          )}
        </VStack>
      )}

      <VStack gap={3}>
        <Heading level={3}>Compare use cases</Heading>
        {p.compare.status === 'ready' ? (
          <List density="compact" edge="outset" hasDividers>
            {p.compare.data.results.map((r) => (
              <ListItem
                key={r.profile}
                label={r.label}
                isSelected={r.profile === p.profile?.id}
                description={r.masked ? 'No-go here' : `Rank ${formatRank(r.rank, r.ranked_cells)}`}
                endContent={
                  <Text hasTabularNumbers weight="semibold">
                    {r.masked ? '—' : formatScore(r.score)}
                  </Text>
                }
                onClick={() => p.onChooseProfile(r.profile)}
              />
            ))}
          </List>
        ) : p.compare.status === 'error' ? (
          <Text color="secondary" display="block">
            {p.compare.message}
          </Text>
        ) : (
          <Skeleton height={4 * 48} />
        )}
      </VStack>

      <VStack gap={3}>
        <Heading level={3}>Measured here</Heading>
        {loading ? (
          <Skeleton height={200} />
        ) : p.point.status === 'error' ? (
          <Text color="secondary" display="block">
            {p.point.message}
          </Text>
        ) : (
          <>
            <MetadataList>
              {rawEntries
                .filter(([id]) => profileLayerIds.has(id))
                .map(([id, v]) => (
                  <MetadataListItem key={id} label={labelFor(id)}>
                    <Text hasTabularNumbers>{formatRaw(v, p.layersById.get(id)?.unit ?? '')}</Text>
                  </MetadataListItem>
                ))}
            </MetadataList>
            <Collapsible trigger={<Text weight="medium">All layers</Text>} defaultIsOpen={false}>
              <MetadataList>
                {rawEntries
                  .filter(([id]) => !profileLayerIds.has(id))
                  .map(([id, v]) => (
                    <MetadataListItem key={id} label={labelFor(id)}>
                      <Text hasTabularNumbers>
                        {formatRaw(v, p.layersById.get(id)?.unit ?? '')}
                      </Text>
                    </MetadataListItem>
                  ))}
              </MetadataList>
            </Collapsible>
          </>
        )}
      </VStack>
    </VStack>
  );
}

// ---------------------------------------------------------------- site comparison

export function SiteCompare({
  sites,
  profiles,
  profile,
  layersById,
  onBack,
}: {
  sites: PlacedSite[];
  profiles: Profile[];
  profile: Profile | undefined;
  layersById: Map<string, LayerMeta>;
  onBack: () => void;
}) {
  const [a, setA] = useState(sites[0]?.id ?? '');
  const [b, setB] = useState(sites[1]?.id ?? '');
  const [rows, setRows] = useState<Async<Record<string, unknown>[]>>({ status: 'loading' });
  const siteA = sites.find((s) => s.id === a);
  const siteB = sites.find((s) => s.id === b);

  useEffect(() => {
    if (!siteA || !siteB || !profile) return;
    let alive = true;
    setRows({ status: 'loading' });
    const ids = profiles.map((x) => x.id);
    Promise.all([
      api.compare(ids, siteA.lat, siteA.lon),
      api.compare(ids, siteB.lat, siteB.lon),
      api.point(profile.id, siteA.lat, siteA.lon),
      api.point(profile.id, siteB.lat, siteB.lon),
    ])
      .then(([ca, cb, pa, pb]) => {
        if (!alive) return;
        const scoreRows = ca.results.map((r, i) => {
          const rb = cb.results[i];
          return {
            id: `score-${r.profile}`,
            metric: `${r.label} score`,
            a: r.masked ? 'No-go' : formatScore(r.score),
            b: rb?.masked ? 'No-go' : formatScore(rb?.score),
          };
        });
        const layerRows = profile.layers.map((l) => {
          const unit = layersById.get(l.id)?.unit ?? '';
          return {
            id: `layer-${l.id}`,
            metric: layersById.get(l.id)?.label ?? l.id,
            a: formatRaw(pa.raw[l.id], unit),
            b: formatRaw(pb.raw[l.id], unit),
          };
        });
        setRows({ status: 'ready', data: [...scoreRows, ...layerRows] });
      })
      .catch(
        (e: unknown) =>
          alive && setRows({ status: 'error', message: String((e as Error).message) }),
      );
    return () => {
      alive = false;
    };
  }, [siteA, siteB, profile, profiles, layersById]);

  const options = sites.map((s) => ({ value: s.id, label: s.name }));
  return (
    <VStack gap={5} paddingBlockEnd={6}>
      <HStack gap={1} align="center">
        <IconButton
          label="Back to best sites"
          icon={<Icon icon={ArrowLeft} size="sm" />}
          variant="ghost"
          size="sm"
          onClick={onBack}
        />
        <Heading level={2}>Compare placed sites</Heading>
      </HStack>
      <HStack gap={2}>
        <Selector
          label="Site A"
          options={options}
          value={a}
          onChange={(v) => v && setA(v)}
          width="100%"
        />
        <Selector
          label="Site B"
          options={options}
          value={b}
          onChange={(v) => v && setB(v)}
          width="100%"
        />
      </HStack>
      {rows.status === 'ready' ? (
        <Table
          data={rows.data}
          idKey="id"
          density="compact"
          columns={[
            { key: 'metric', header: 'Measure' },
            {
              key: 'a',
              header: siteA?.name ?? 'A',
              align: 'end',
              renderCell: (r) => <Text hasTabularNumbers>{String(r.a)}</Text>,
            },
            {
              key: 'b',
              header: siteB?.name ?? 'B',
              align: 'end',
              renderCell: (r) => <Text hasTabularNumbers>{String(r.b)}</Text>,
            },
          ]}
        />
      ) : rows.status === 'error' ? (
        <Text color="secondary" display="block">
          {rows.message}
        </Text>
      ) : (
        <Skeleton height={320} />
      )}
    </VStack>
  );
}
