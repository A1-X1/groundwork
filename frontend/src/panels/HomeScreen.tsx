import { Button } from '@astryxdesign/core/Button';
import { Collapsible } from '@astryxdesign/core/Collapsible';
import { CheckboxList, CheckboxListItem } from '@astryxdesign/core/CheckboxList';
import { ClickableCard } from '@astryxdesign/core/ClickableCard';
import { Grid } from '@astryxdesign/core/Grid';
import { Heading } from '@astryxdesign/core/Heading';
import { HStack } from '@astryxdesign/core/HStack';
import { Icon } from '@astryxdesign/core/Icon';
import { IconButton } from '@astryxdesign/core/IconButton';
import { List, ListItem } from '@astryxdesign/core/List';
import { MetadataList, MetadataListItem } from '@astryxdesign/core/MetadataList';
import { NumberInput } from '@astryxdesign/core/NumberInput';
import { SegmentedControl, SegmentedControlItem } from '@astryxdesign/core/SegmentedControl';
import { Selector } from '@astryxdesign/core/Selector';
import { Slider } from '@astryxdesign/core/Slider';
import { Switch } from '@astryxdesign/core/Switch';
import { Text } from '@astryxdesign/core/Text';
import { TextArea } from '@astryxdesign/core/TextArea';
import { TextInput } from '@astryxdesign/core/TextInput';
import { VStack } from '@astryxdesign/core/VStack';
import {
  ArrowLeft,
  Atom,
  FerrisWheel,
  Building2,
  Hospital,
  House,
  Pickaxe,
  Plus,
  School,
  Server,
  Sun,
  Trash2,
  Warehouse,
  Wind,
  type LucideIcon,
} from 'lucide-react';
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import type { LayerMeta, Profile } from '../api/types';
import {
  COOLING,
  DEFAULT_DC_SPEC,
  estimate,
  GPUS,
  STRUCTURE_TYPES,
  structureTypesFrom,
  type Cooling,
  type DataCentreSpec,
  type Project,
  type StructureType,
  type Workload,
} from '../lib/structures';
import { Logo } from './Logo';

const TYPE_ICONS: Record<string, LucideIcon> = {
  data_centre: Server,
  house: House,
  school: School,
  mine: Pickaxe,
  hospital: Hospital,
  warehouse: Warehouse,
  office: Building2,
  solar_farm: Sun,
  wind_farm: Wind,
  nuclear_power_plant: Atom,
  theme_park: FerrisWheel,
};

const n0 = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 });
const n1 = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 1 });

interface Props {
  profiles: Profile[];
  layersById: Map<string, LayerMeta>;
  projects: Project[];
  onCreate: (p: Project) => void;
  onOpen: (p: Project) => void;
  onRemove: (id: string) => void;
  /** Bumped by the agent's OPEN_CREATE command. */
  openCreateNonce: number;
  /** Command bar for the planning agent ("describe what you want to build"). */
  assistant: ReactNode;
  /** Regions with data, for the Custom tab's region choice. */
  regions?: { id: string; name: string }[];
  /** Custom tab: hand a free-text description to the planning agent. */
  onBuildCustom?: (prompt: string, region: string | null) => void;
}

type Step = { kind: 'home' } | { kind: 'type' } | { kind: 'details'; type: StructureType };

function DataCentreForm({
  spec,
  onChange,
}: {
  spec: DataCentreSpec;
  onChange: (s: DataCentreSpec) => void;
}) {
  const e = estimate(spec);
  const set = <K extends keyof DataCentreSpec>(k: K, v: DataCentreSpec[K]) =>
    onChange({ ...spec, [k]: v });
  return (
    <VStack gap={6}>
      <VStack gap={4}>
        <Heading level={3}>Compute</Heading>
        <Grid columns={{ minWidth: 220, max: 2 }} gap={4}>
          <Selector
            label="Accelerator"
            options={GPUS.map((g) => ({
              value: g.id,
              label: g.label,
              description: `${n0.format(g.tflops)} TFLOPS · ${n0.format(g.watts)} W · ${g.memoryGb} GB`,
            }))}
            value={spec.gpu}
            onChange={(v) => v && set('gpu', v)}
            width="100%"
          />
          <NumberInput
            label="Number of accelerators"
            value={spec.gpuCount}
            min={8}
            max={500000}
            step={8}
            onChange={(v) => set('gpuCount', Math.max(8, Math.round(v)))}
            formatValue={(v) => n0.format(v)}
            width="100%"
          />
        </Grid>
        <SegmentedControl
          label="Workload"
          value={spec.workload}
          onChange={(v) => set('workload', v as Workload)}
          layout="fill"
        >
          <SegmentedControlItem value="training" label="Training" />
          <SegmentedControlItem value="mixed" label="Mixed" />
          <SegmentedControlItem value="inference" label="Inference" />
        </SegmentedControl>
      </VStack>

      <VStack gap={4}>
        <Heading level={3}>Power and cooling</Heading>
        <SegmentedControl
          label="Cooling"
          value={spec.cooling}
          onChange={(v) =>
            onChange({ ...spec, cooling: v as Cooling, pue: COOLING[v as Cooling].pue })
          }
          layout="fill"
        >
          {(Object.keys(COOLING) as Cooling[]).map((c) => (
            <SegmentedControlItem key={c} value={c} label={COOLING[c].label} />
          ))}
        </SegmentedControl>
        <Grid columns={{ minWidth: 220, max: 2 }} gap={4}>
          <Slider
            label="Target PUE"
            value={spec.pue}
            min={1.03}
            max={1.8}
            step={0.01}
            valueDisplay="text"
            formatValue={(v) => v.toFixed(2)}
            onChange={(v: number) => set('pue', v)}
            width="100%"
          />
          <Slider
            label="Average utilisation"
            value={Math.round(spec.utilisation * 100)}
            min={10}
            max={100}
            valueDisplay="text"
            formatValue={(v) => `${v}%`}
            onChange={(v: number) => set('utilisation', v / 100)}
            width="100%"
          />
        </Grid>
        <Grid columns={{ minWidth: 220, max: 2 }} gap={4}>
          <Selector
            label="Redundancy"
            options={[
              { value: 'II', label: 'Tier II', description: 'Redundant components' },
              { value: 'III', label: 'Tier III', description: 'Concurrently maintainable' },
              { value: 'IV', label: 'Tier IV', description: 'Fault tolerant' },
            ]}
            value={spec.tier}
            onChange={(v) => v && set('tier', v as DataCentreSpec['tier'])}
            width="100%"
          />
          <Switch
            label="Prefer low-carbon power"
            value={spec.lowCarbon}
            onChange={(v) => set('lowCarbon', v)}
          />
        </Grid>
      </VStack>

      <VStack gap={3}>
        <Heading level={3}>Estimate</Heading>
        <MetadataList columns="multi">
          <MetadataListItem label="Peak compute">
            <Text hasTabularNumbers weight="semibold">
              {n1.format(e.peakPflops)} PFLOPS
            </Text>
          </MetadataListItem>
          <MetadataListItem label="IT load">
            <Text hasTabularNumbers weight="semibold">
              {n1.format(e.itMw)} MW
            </Text>
          </MetadataListItem>
          <MetadataListItem label="Facility power">
            <Text hasTabularNumbers weight="semibold">
              {n1.format(e.facilityMw)} MW
            </Text>
          </MetadataListItem>
          <MetadataListItem label="Energy per year">
            <Text hasTabularNumbers weight="semibold">
              {n0.format(e.annualGwh)} GWh
            </Text>
          </MetadataListItem>
          <MetadataListItem label="Racks">
            <Text hasTabularNumbers weight="semibold">
              {n0.format(e.racks)}
            </Text>
          </MetadataListItem>
          <MetadataListItem label="Accelerator memory">
            <Text hasTabularNumbers weight="semibold">
              {n1.format(e.memoryTb)} TB
            </Text>
          </MetadataListItem>
        </MetadataList>
        <Text type="supporting" color="secondary" display="block" textWrap="pretty">
          Planning estimates: vendor peak dense FP16/BF16 figures, servers at 1.8× accelerator
          power. Facility power and cooling choice set how much grid access, free cooling and fibre
          matter in the score.
        </Text>
      </VStack>
    </VStack>
  );
}

export function HomeScreen(props: Props) {
  const [step, setStep] = useState<Step>({ kind: 'home' });
  const [tab, setTab] = useState<'builtin' | 'custom'>('builtin');
  const [customPrompt, setCustomPrompt] = useState('');
  const [customRegion, setCustomRegion] = useState('');
  useEffect(() => {
    if (props.openCreateNonce) setStep({ kind: 'type' });
  }, [props.openCreateNonce]);
  const [name, setName] = useState('');
  const [spec, setSpec] = useState<DataCentreSpec>(DEFAULT_DC_SPEC);
  const [priorities, setPriorities] = useState<string[]>([]);
  const typeGroups = useMemo(() => structureTypesFrom(props.profiles), [props.profiles]);
  /** Use cases the planning agent generated earlier (Custom tab). */
  const generated = useMemo(
    () =>
      structureTypesFrom(props.profiles.filter((p) => p.generated)).main.concat(
        structureTypesFrom(props.profiles.filter((p) => p.generated)).more,
      ),
    [props.profiles],
  );
  const typeCard = (t: StructureType, i: number) => (
    <ClickableCard
      key={t.id}
      label={t.label}
      onClick={() => start(t)}
      padding={4}
      className="gw-stagger"
      style={{ animationDelay: `${i * 30}ms` }}
    >
      <VStack gap={3}>
        <Icon icon={TYPE_ICONS[t.id] ?? Building2} size="lg" />
        <VStack gap={1}>
          <Text weight="semibold">{t.label}</Text>
          <Text type="supporting" color="secondary" maxLines={2}>
            {t.blurb}
          </Text>
        </VStack>
      </VStack>
    </ClickableCard>
  );

  const start = (type: StructureType) => {
    setName('');
    setSpec(DEFAULT_DC_SPEC);
    setPriorities([]);
    setStep({ kind: 'details', type });
  };

  const create = (type: StructureType) => {
    if (!type.profile) return;
    const project: Project = {
      id: `p-${Date.now()}`,
      name: name.trim() || `New ${type.label.toLowerCase()}`,
      type: type.id,
      profile: type.profile,
      createdAt: Date.now(),
      ...(type.id === 'data_centre' ? { spec } : { priorities }),
    };
    props.onCreate(project);
    setStep({ kind: 'home' });
  };

  return (
    <VStack
      height="100%"
      isScrollable
      align="center"
      paddingInline={6}
      style={{
        paddingBlockStart: step.kind === 'home' ? '18vh' : 'var(--spacing-10)',
        paddingBlockEnd: 'var(--spacing-10)',
        transition: 'padding-block-start 300ms ease',
      }}
    >
      <VStack gap={10} width="100%" maxWidth={step.kind === 'details' ? 760 : 880}>
        {step.kind === 'home' && (
          <>
            <VStack gap={8} align="center">
              <Heading level={1} type="display-1" justify="center" textWrap="balance">
                What <Logo size="inherit" /> is needed today?
              </Heading>
              <ClickableCard
                label="Create a new structure"
                onClick={() => setStep({ kind: 'type' })}
                variant="transparent"
                padding={6}
                width={320}
                style={{
                  border: '1.5px dashed var(--color-border-emphasized)',
                  borderRadius: 'var(--radius-container)',
                }}
              >
                <HStack gap={2} justify="center" align="center">
                  <Icon icon={Plus} size="md" />
                  <Text type="large" weight="medium">
                    Create
                  </Text>
                </HStack>
              </ClickableCard>
              <VStack gap={2} width="100%" maxWidth={560} align="center">
                <Text color="secondary">or describe anything you want to build</Text>
                {props.assistant}
              </VStack>
            </VStack>

            {props.projects.length > 0 && (
              <VStack gap={3}>
                <Heading level={2}>Your structures</Heading>
                <List hasDividers edge="outset">
                  {props.projects.map((p) => {
                    const t =
                      STRUCTURE_TYPES.find((x) => x.id === p.type) ??
                      props.profiles.find((x) => x.id === p.profile);
                    const e = p.spec ? estimate(p.spec) : null;
                    return (
                      <ListItem
                        key={p.id}
                        label={p.name}
                        description={
                          e && p.spec
                            ? `${t?.label} · ${n0.format(p.spec.gpuCount)} × ${GPUS.find((g) => g.id === p.spec?.gpu)?.label} · ${n1.format(e.facilityMw)} MW`
                            : t?.label
                        }
                        startContent={<Icon icon={TYPE_ICONS[p.type] ?? Building2} size="md" />}
                        onClick={() => props.onOpen(p)}
                        endContent={
                          <IconButton
                            label={`Delete ${p.name}`}
                            icon={<Icon icon={Trash2} size="sm" />}
                            variant="ghost"
                            size="sm"
                            onClick={(ev) => {
                              ev.stopPropagation();
                              props.onRemove(p.id);
                            }}
                          />
                        }
                      />
                    );
                  })}
                </List>
              </VStack>
            )}
          </>
        )}

        {step.kind === 'type' && (
          <VStack gap={6}>
            <HStack gap={2} align="center">
              <IconButton
                label="Back"
                icon={<Icon icon={ArrowLeft} size="sm" />}
                variant="ghost"
                onClick={() => setStep({ kind: 'home' })}
              />
              <Heading level={1} textWrap="balance">
                What are you building?
              </Heading>
            </HStack>
            <SegmentedControl
              label="Kind of structure"
              value={tab}
              onChange={(v) => setTab(v as 'builtin' | 'custom')}
            >
              <SegmentedControlItem value="builtin" label="Built-in" />
              <SegmentedControlItem value="custom" label="Custom" />
            </SegmentedControl>
            {tab === 'custom' ? (
              <VStack gap={5}>
                <TextArea
                  label="Describe what you want to build"
                  placeholder="e.g. a hydrogen refuelling station near motorways"
                  description="The Mistral planning agent finds the data, builds a scoring profile and a 3D model, then opens it on the map."
                  value={customPrompt}
                  onChange={(v: string) => setCustomPrompt(v)}
                  rows={4}
                  hasAutoFocus
                />
                {(props.regions?.length ?? 0) > 0 && (
                  <Selector
                    label="Region"
                    options={[
                      { value: '', label: 'Wherever the data is' },
                      ...(props.regions ?? []).map((r) => ({ value: r.id, label: r.name })),
                    ]}
                    value={customRegion}
                    onChange={(v) => setCustomRegion(v ?? '')}
                    width="100%"
                  />
                )}
                <Button
                  label="Build it"
                  variant="primary"
                  size="lg"
                  isDisabled={!customPrompt.trim() || !props.onBuildCustom}
                  onClick={() => {
                    props.onBuildCustom?.(customPrompt.trim(), customRegion || null);
                    setCustomPrompt('');
                    setStep({ kind: 'home' });
                  }}
                />
                {generated.length > 0 && (
                  <VStack gap={3}>
                    <Heading level={3}>Generated before</Heading>
                    <Grid columns={{ minWidth: 190, max: 4 }} gap={3}>
                      {generated.map((t, i) => typeCard(t, i))}
                    </Grid>
                  </VStack>
                )}
              </VStack>
            ) : (
              <>
                <Grid columns={{ minWidth: 190, max: 4 }} gap={3}>
                  {typeGroups.main.map((t, i) => typeCard(t, i))}
                </Grid>
                {typeGroups.more.length > 0 && (
                  <Collapsible
                    trigger={<Text weight="medium">More ({typeGroups.more.length})</Text>}
                    defaultIsOpen={false}
                  >
                    <Grid columns={{ minWidth: 190, max: 4 }} gap={3}>
                      {typeGroups.more.map((t, i) => typeCard(t, i))}
                    </Grid>
                  </Collapsible>
                )}
              </>
            )}
          </VStack>
        )}

        {step.kind === 'details' && (
          <VStack gap={8}>
            <HStack gap={2} align="center">
              <IconButton
                label="Back"
                icon={<Icon icon={ArrowLeft} size="sm" />}
                variant="ghost"
                onClick={() => setStep({ kind: 'type' })}
              />
              <Heading level={1} textWrap="balance">
                New {step.type.label.toLowerCase()}
              </Heading>
            </HStack>
            <TextInput
              label="Name"
              placeholder={`e.g. ${step.type.id === 'data_centre' ? 'London training cluster' : `Family ${step.type.label.toLowerCase()}`}`}
              value={name}
              onChange={(v: string) => setName(v)}
              hasAutoFocus
            />
            {step.type.id === 'data_centre' ? (
              <DataCentreForm spec={spec} onChange={setSpec} />
            ) : (
              <CheckboxList
                label="What matters most?"
                description="These count for more in the score. You can fine-tune weights later."
                value={priorities}
                onChange={setPriorities}
              >
                {(props.profiles.find((p) => p.id === step.type.profile)?.layers ?? []).map((l) => (
                  <CheckboxListItem
                    key={l.id}
                    value={l.id}
                    label={props.layersById.get(l.id)?.label ?? l.id}
                    description={l.better === 'lower' ? 'Lower is better' : 'Higher is better'}
                  />
                ))}
              </CheckboxList>
            )}
            <Button
              label="Find the best sites"
              variant="primary"
              size="lg"
              onClick={() => create(step.type)}
            />
          </VStack>
        )}
      </VStack>
    </VStack>
  );
}
