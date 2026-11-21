import { Button } from '@astryxdesign/core/Button';
import { Heading } from '@astryxdesign/core/Heading';
import { HStack } from '@astryxdesign/core/HStack';
import { Icon } from '@astryxdesign/core/Icon';
import { IconButton } from '@astryxdesign/core/IconButton';
import { List, ListItem } from '@astryxdesign/core/List';
import { MetadataList, MetadataListItem } from '@astryxdesign/core/MetadataList';
import { Skeleton } from '@astryxdesign/core/Skeleton';
import { Text } from '@astryxdesign/core/Text';
import { TextInput } from '@astryxdesign/core/TextInput';
import { VStack } from '@astryxdesign/core/VStack';
import { ArrowLeft, Check, Pencil, PenLine, Shapes, Trash2 } from 'lucide-react';
import { useState } from 'react';
import type { Area, AreaSummary } from '../api/types';
import { formatScore } from '../lib/format';

const n0 = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 });
const n1 = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 1 });

interface ListProps {
  areas: Area[];
  selectedId: string | null;
  isDrawing: boolean;
  draftPoints: number;
  pendingName: string | null;
  error: string | null;
  onStartDraw: () => void;
  onCancelDraw: () => void;
  onFinishDraw: () => void;
  onPendingName: (v: string) => void;
  onSave: () => void;
  onSelect: (id: string) => void;
  onRename: (id: string, name: string) => void;
  onDelete: (id: string) => void;
}

function AreaRow({
  area,
  isSelected,
  onSelect,
  onRename,
  onDelete,
}: {
  area: Area;
  isSelected: boolean;
  onSelect: () => void;
  onRename: (name: string) => void;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(area.name);
  if (editing) {
    const commit = () => {
      if (draft.trim()) onRename(draft.trim());
      setEditing(false);
    };
    return (
      <HStack gap={1} align="end">
        <TextInput
          label="Area name"
          isLabelHidden
          value={draft}
          onChange={(v: string) => setDraft(v)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commit();
            if (e.key === 'Escape') setEditing(false);
          }}
          hasAutoFocus
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
      label={area.name}
      isSelected={isSelected}
      startContent={<Icon icon={Shapes} size="sm" />}
      onClick={onSelect}
      endContent={
        <HStack gap={0.5}>
          <IconButton
            label={`Rename ${area.name}`}
            icon={<Icon icon={Pencil} size="sm" />}
            variant="ghost"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              setDraft(area.name);
              setEditing(true);
            }}
          />
          <IconButton
            label={`Delete ${area.name}`}
            icon={<Icon icon={Trash2} size="sm" />}
            variant="ghost"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
          />
        </HStack>
      }
    />
  );
}

export function AreasPanel(p: ListProps) {
  return (
    <VStack gap={3}>
      <HStack justify="between" align="center">
        <Heading level={2}>Areas</Heading>
        {!p.isDrawing && p.pendingName == null && (
          <Button
            label="Draw area"
            variant="secondary"
            size="sm"
            icon={<Icon icon={PenLine} size="sm" />}
            onClick={p.onStartDraw}
          />
        )}
      </HStack>

      {p.isDrawing && (
        <VStack gap={2}>
          <Text color="secondary" display="block" role="status" textWrap="pretty">
            Click the map to add corners ({p.draftPoints} so far). Double-click or click the first
            corner to finish.
          </Text>
          <HStack gap={2}>
            <Button
              label="Finish"
              variant="secondary"
              size="sm"
              isDisabled={p.draftPoints < 3}
              onClick={p.onFinishDraw}
            />
            <Button label="Cancel" variant="ghost" size="sm" onClick={p.onCancelDraw} />
          </HStack>
        </VStack>
      )}

      {p.pendingName != null && (
        <VStack gap={2}>
          <TextInput
            label="Name this area"
            value={p.pendingName}
            placeholder="e.g. Docklands shortlist"
            onChange={(v: string) => p.onPendingName(v)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') p.onSave();
              if (e.key === 'Escape') p.onCancelDraw();
            }}
            hasAutoFocus
          />
          <HStack gap={2}>
            <Button label="Save area" variant="secondary" size="sm" onClick={p.onSave} />
            <Button label="Discard" variant="ghost" size="sm" onClick={p.onCancelDraw} />
          </HStack>
        </VStack>
      )}

      {p.error && (
        <Text color="secondary" display="block" role="alert">
          {p.error}
        </Text>
      )}

      {p.areas.length === 0 && !p.isDrawing && p.pendingName == null ? (
        <Text color="secondary" display="block" textWrap="pretty">
          Draw an area to save a shortlist and see how it scores.
        </Text>
      ) : (
        <List density="compact" edge="outset">
          {p.areas.map((a) => (
            <AreaRow
              key={a.id}
              area={a}
              isSelected={a.id === p.selectedId}
              onSelect={() => p.onSelect(a.id)}
              onRename={(name) => p.onRename(a.id, name)}
              onDelete={() => p.onDelete(a.id)}
            />
          ))}
        </List>
      )}
    </VStack>
  );
}

export function AreaDetail({
  area,
  profileLabel,
  summary,
  onBack,
  onBest,
}: {
  area: Area;
  profileLabel: string | null;
  summary:
    | { status: 'loading' }
    | { status: 'ready'; data: AreaSummary }
    | { status: 'error'; message: string }
    | null;
  onBack: () => void;
  onBest: (h3: string) => void;
}) {
  return (
    <VStack gap={6} paddingBlockEnd={6}>
      <VStack gap={2}>
        <HStack gap={1} align="center">
          <IconButton
            label="Back"
            icon={<Icon icon={ArrowLeft} size="sm" />}
            variant="ghost"
            size="sm"
            onClick={onBack}
          />
          <Text color="secondary">Saved area</Text>
        </HStack>
        <Heading level={2} textWrap="balance">
          {area.name}
        </Heading>
      </VStack>
      {!profileLabel ? (
        <Text color="secondary" display="block" textWrap="pretty">
          Choose a use case to score this area.
        </Text>
      ) : summary?.status === 'ready' ? (
        <VStack gap={4}>
          <VStack gap={1}>
            <Text type="display-2" weight="semibold" hasTabularNumbers>
              {formatScore(summary.data.mean_score)}
            </Text>
            <Text color="secondary">Mean {profileLabel.toLowerCase()} score inside the area</Text>
          </VStack>
          <MetadataList>
            <MetadataListItem label="Size">
              <Text hasTabularNumbers>{n1.format(summary.data.area_km2)} km²</Text>
            </MetadataListItem>
            <MetadataListItem label="Hexagons">
              <Text hasTabularNumbers>{n0.format(summary.data.cells)}</Text>
            </MetadataListItem>
            <MetadataListItem label="With data">
              <Text hasTabularNumbers>{n0.format(summary.data.scored_cells)}</Text>
            </MetadataListItem>
            <MetadataListItem label="Ruled out">
              <Text hasTabularNumbers>{n0.format(summary.data.masked_cells)}</Text>
            </MetadataListItem>
            <MetadataListItem label="Best hexagon">
              <Text hasTabularNumbers>{formatScore(summary.data.best_score)}</Text>
            </MetadataListItem>
          </MetadataList>
          {summary.data.best_h3 && (
            <Button
              label="Open the best hexagon"
              variant="primary"
              onClick={() => onBest(summary.data.best_h3!)}
            />
          )}
          {summary.data.scored_cells === 0 && (
            <Text color="secondary" display="block" textWrap="pretty">
              There is no detailed data inside this area yet.
            </Text>
          )}
        </VStack>
      ) : summary?.status === 'error' ? (
        <Text color="secondary" display="block">
          {summary.message}
        </Text>
      ) : (
        <Skeleton height={240} />
      )}
    </VStack>
  );
}
