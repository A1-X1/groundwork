import { Button } from '@astryxdesign/core/Button';
import { Collapsible } from '@astryxdesign/core/Collapsible';
import { Heading } from '@astryxdesign/core/Heading';
import { Icon } from '@astryxdesign/core/Icon';
import { HStack } from '@astryxdesign/core/HStack';
import { IconButton } from '@astryxdesign/core/IconButton';
import { List, ListItem } from '@astryxdesign/core/List';
import { Selector } from '@astryxdesign/core/Selector';
import { Skeleton } from '@astryxdesign/core/Skeleton';
import { Slider } from '@astryxdesign/core/Slider';
import { Switch } from '@astryxdesign/core/Switch';
import { Text } from '@astryxdesign/core/Text';
import { TextInput } from '@astryxdesign/core/TextInput';
import { VStack } from '@astryxdesign/core/VStack';
import { Check, MapPin, Pencil, Trash2 } from 'lucide-react';
import { useState, type MouseEvent, type ReactNode } from 'react';
import type { LayerMeta, ProfileLayer } from '../api/types';
import { VIEWS } from '../lib/overlays';
import type { Basemap } from '../map/MapView';
import { SegmentedControl, SegmentedControlItem } from '@astryxdesign/core/SegmentedControl';
import type { GroundworkState, PlacedSite } from '../state/useGroundwork';
import { MetadataList, MetadataListItem } from '@astryxdesign/core/MetadataList';
import { estimate, GPUS, STRUCTURE_TYPES, type Project } from '../lib/structures';

const n1 = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 1 });
const n0 = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 });

function ProjectSummary({ project, onEdit }: { project: Project; onEdit: () => void }) {
  const type = STRUCTURE_TYPES.find((t) => t.id === project.type);
  const e = project.spec ? estimate(project.spec) : null;
  return (
    <VStack gap={3}>
      <HStack justify="between" align="center">
        <VStack gap={0.5}>
          <Text type="supporting" color="secondary">
            {type?.label}
          </Text>
          <Heading level={2}>{project.name}</Heading>
        </VStack>
        <Button label="All structures" variant="ghost" size="sm" onClick={onEdit} />
      </HStack>
      {e && project.spec && (
        <MetadataList>
          <MetadataListItem label="Accelerators">
            <Text hasTabularNumbers>
              {n0.format(project.spec.gpuCount)} ×{' '}
              {GPUS.find((g) => g.id === project.spec?.gpu)?.label}
            </Text>
          </MetadataListItem>
          <MetadataListItem label="Facility power">
            <Text hasTabularNumbers>{n1.format(e.facilityMw)} MW</Text>
          </MetadataListItem>
          <MetadataListItem label="Peak compute">
            <Text hasTabularNumbers>{n1.format(e.peakPflops)} PFLOPS</Text>
          </MetadataListItem>
        </MetadataList>
      )}
    </VStack>
  );
}

const VISIBLE_SLIDERS = 4;

interface Props {
  basemap: Basemap;
  onBasemap: (b: Basemap) => void;
  areas: ReactNode;
  project: Project | null;
  onEditProject: () => void;
  gw: GroundworkState;
  isPlacing: boolean;
  onTogglePlacing: () => void;
  showMasked: boolean;
  onShowMasked: (v: boolean) => void;
  terrain: boolean;
  onTerrain: (v: boolean) => void;
  lowPower: boolean;
  onOpenSite: (site: PlacedSite, el: HTMLElement | null) => void;
  onCompareSites: () => void;
}

function WeightSlider({
  layer,
  meta,
  note,
  value,
  total,
  onChange,
}: {
  layer: ProfileLayer;
  meta: LayerMeta | undefined;
  /** What this layer means for the profile (from the data aggregator), if known. */
  note?: string;
  value: number;
  total: number;
  onChange: (v: number) => void;
}) {
  const share = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <Slider
      label={meta?.label ?? layer.id}
      description={note ?? (layer.better === 'lower' ? 'Lower is better' : 'Higher is better')}
      value={value}
      min={0}
      max={100}
      step={1}
      valueDisplay="text"
      formatValue={() => `${share}%`}
      onChange={(v: number) => onChange(v)}
      width="100%"
    />
  );
}

function SiteRow({
  site,
  profileLabel,
  onOpen,
  onRename,
  onRemove,
}: {
  site: PlacedSite;
  profileLabel: string;
  onOpen: (el: HTMLElement | null) => void;
  onRename: (name: string) => void;
  onRemove: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(site.name);
  if (editing) {
    const commit = () => {
      onRename(draft.trim() || site.name);
      setEditing(false);
    };
    return (
      <HStack gap={1} align="end">
        <TextInput
          label="Site name"
          isLabelHidden
          value={draft}
          onChange={(v: string) => setDraft(v)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commit();
            if (e.key === 'Escape') setEditing(false);
          }}
          hasAutoFocus
          size="md"
        />
        <IconButton
          label="Save name"
          icon={<Icon icon={Check} size="sm" />}
          variant="ghost"
          onClick={commit}
        />
      </HStack>
    );
  }
  return (
    <ListItem
      label={site.name}
      description={profileLabel}
      startContent={<Icon icon={MapPin} size="sm" />}
      onClick={(e: MouseEvent) => onOpen(e.currentTarget as HTMLElement)}
      endContent={
        <HStack gap={0.5}>
          <IconButton
            label={`Rename ${site.name}`}
            icon={<Icon icon={Pencil} size="sm" />}
            variant="ghost"
            size="sm"
            onClick={(e: MouseEvent) => {
              e.stopPropagation();
              setDraft(site.name);
              setEditing(true);
            }}
          />
          <IconButton
            label={`Remove ${site.name}`}
            icon={<Icon icon={Trash2} size="sm" />}
            variant="ghost"
            size="sm"
            onClick={(e: MouseEvent) => {
              e.stopPropagation();
              onRemove();
            }}
          />
        </HStack>
      }
    />
  );
}

export function ControlPanel(props: Props) {
  const { gw } = props;
  const profile = gw.profile;
  const total = Object.values(gw.weights).reduce((a, b) => a + b, 0);
  const sortedLayers = [...(profile?.layers ?? [])].sort((a, b) => b.weight - a.weight);
  const top = sortedLayers.slice(0, VISIBLE_SLIDERS);
  const rest = sortedLayers.slice(VISIBLE_SLIDERS);
  const overlay = VIEWS.find((v) => v.id === gw.overlayId);

  const overlayOptions = [
    {
      type: 'section' as const,
      title: 'Views',
      options: VIEWS.map((v) => ({ value: v.id, label: v.label })),
    },
    {
      type: 'section' as const,
      title: 'All layers',
      options: gw.layers.map((l) => ({ value: `layer:${l.id}`, label: l.label })),
    },
  ];

  const slider = (l: ProfileLayer) => (
    <WeightSlider
      key={l.id}
      layer={l}
      meta={gw.layersById.get(l.id)}
      note={profile?.notes?.[l.id]}
      value={gw.weights[l.id] ?? 0}
      total={total}
      onChange={(v) => gw.setWeight(l.id, v)}
    />
  );

  return (
    <VStack gap={6} paddingBlockEnd={6}>
      {props.project && <ProjectSummary project={props.project} onEdit={props.onEditProject} />}
      <VStack gap={3}>
        {gw.profiles.status === 'loading' ? (
          <Skeleton height={64} />
        ) : (
          <Selector
            label="Use case"
            options={gw.profileList.map((p) => ({ value: p.id, label: p.label }))}
            value={profile?.id}
            placeholder="Choose what you're building"
            onChange={(v) => v && gw.chooseProfile(v)}
            width="100%"
            description={profile?.description}
          />
        )}
      </VStack>

      {(profile || gw.profiles.status === 'loading') && (
        <VStack gap={3}>
          <HStack justify="between" align="center">
            <Heading level={2}>Weights</Heading>
            <Button
              label="Reset weights"
              variant="ghost"
              size="sm"
              isDisabled={gw.isDefaultWeights}
              onClick={gw.resetWeights}
            />
          </HStack>
          {profile ? (
            <VStack gap={4}>{top.map(slider)}</VStack>
          ) : (
            <VStack gap={4}>
              {[0, 1, 2, 3].map((i) => (
                <Skeleton key={i} height={56} index={i} />
              ))}
            </VStack>
          )}
          {rest.length > 0 && (
            <Collapsible
              trigger={<Text weight="medium">More layers ({rest.length})</Text>}
              defaultIsOpen={false}
            >
              <VStack gap={4} paddingBlockStart={2}>
                {rest.map(slider)}
              </VStack>
            </Collapsible>
          )}
          {gw.weightsError && (
            <Text color="secondary" display="block" role="alert">
              {gw.weightsError}
            </Text>
          )}
        </VStack>
      )}

      <VStack gap={3}>
        <Heading level={2}>Map</Heading>
        <SegmentedControl
          label="Base map"
          value={props.basemap}
          onChange={(v) => props.onBasemap(v as Basemap)}
          layout="fill"
          size="sm"
        >
          <SegmentedControlItem value="map" label="Map" />
          <SegmentedControlItem value="satellite" label="Satellite" />
          <SegmentedControlItem value="grid" label="Grid" />
        </SegmentedControl>
        <Selector
          label="Overlay"
          options={overlayOptions}
          value={gw.overlayId}
          onChange={(v) => v && gw.setOverlayId(v)}
          hasSearch
          searchPlaceholder="Search layers"
          width="100%"
        />
        <Switch
          label="Show no-go areas"
          description={
            profile?.masks.length
              ? `Masked by ${profile.masks
                  .map((m) => gw.layersById.get(m)?.label ?? m)
                  .join(', ')
                  .toLowerCase()}`
              : undefined
          }
          value={props.showMasked}
          onChange={props.onShowMasked}
        />
        {overlay?.relief && (
          <Switch
            label="3D terrain"
            description={props.lowPower ? 'Turned off to keep the map smooth' : undefined}
            value={props.terrain && !props.lowPower}
            isDisabled={props.lowPower}
            onChange={props.onTerrain}
          />
        )}
      </VStack>

      {props.areas}

      <VStack gap={3}>
        <HStack justify="between" align="center">
          <Heading level={2}>Placed sites</Heading>
          <Button
            label={props.isPlacing ? 'Cancel' : 'Place site'}
            variant="secondary"
            size="sm"
            icon={<Icon icon={MapPin} size="sm" />}
            onClick={props.onTogglePlacing}
          />
        </HStack>
        {props.isPlacing && (
          <Text color="secondary" display="block" role="status">
            Click a hexagon to place a {profile?.label.toLowerCase() ?? 'site'}.
          </Text>
        )}
        {gw.sites.length === 0 && !props.isPlacing ? (
          <Text color="secondary" display="block" textWrap="pretty">
            Place a {profile?.label.toLowerCase() ?? 'site'} on the map to keep it here and compare
            locations.
          </Text>
        ) : (
          <List density="compact" edge="outset">
            {gw.sites.map((s) => (
              <SiteRow
                key={s.id}
                site={s}
                profileLabel={gw.profileList.find((p) => p.id === s.profile)?.label ?? s.profile}
                onOpen={(el) => props.onOpenSite(s, el)}
                onRename={(name) => gw.renameSite(s.id, name)}
                onRemove={() => gw.removeSite(s.id)}
              />
            ))}
          </List>
        )}
        {gw.sites.length >= 2 && (
          <Button label="Compare sites" variant="secondary" onClick={props.onCompareSites} />
        )}
      </VStack>

      {gw.health && gw.health.synthetic_layers > 0 && (
        <Text type="supporting" color="secondary" display="block" textWrap="pretty">
          {gw.health.synthetic_layers} of {Object.keys(gw.health.layers).length} layers use
          synthetic stand-in data.
        </Text>
      )}
    </VStack>
  );
}
