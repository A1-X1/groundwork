/**
 * Map key: which icon and colour means what, for the POI categories currently on the map
 * only. A small floating card at the bottom right (left of the map controls) that collapses
 * to a pill; the state is remembered.
 */
import { Button } from '@astryxdesign/core/Button';
import { HStack } from '@astryxdesign/core/HStack';
import { Icon } from '@astryxdesign/core/Icon';
import { IconButton } from '@astryxdesign/core/IconButton';
import { Text } from '@astryxdesign/core/Text';
import { VStack } from '@astryxdesign/core/VStack';
import { KeyRound, PanelRightClose } from 'lucide-react';
import { useState } from 'react';
import { CATEGORIES, categoryOf, poiIconUrl, type PoiCategory } from '../map/poiIcons';
import { EDGE, SURFACE } from './FloatingPanel';

const KEY = 'groundwork.panel.key.collapsed';
const anchor = {
  position: 'absolute',
  insetBlockEnd: EDGE,
  insetInlineEnd: `calc(${EDGE} + var(--spacing-12, 48px))`,
  zIndex: 4,
} as const;

function remembered(): boolean {
  try {
    return window.localStorage.getItem(KEY) === '1';
  } catch {
    return false;
  }
}

/** One row per category in view (first kind seen stands for its category's icon). */
export function keyRows(kinds: string[]): { category: PoiCategory; kind: string }[] {
  const seen = new Map<string, { category: PoiCategory; kind: string }>();
  for (const kind of kinds) {
    const category = categoryOf(kind);
    if (!seen.has(category.id)) seen.set(category.id, { category, kind });
  }
  const order = (c: PoiCategory) => {
    const i = CATEGORIES.findIndex((x) => x.id === c.id);
    return i < 0 ? CATEGORIES.length : i;
  };
  return [...seen.values()].sort((a, b) => order(a.category) - order(b.category));
}

export function MapKey({ kinds }: { kinds: string[] }) {
  const [collapsed, setCollapsed] = useState(remembered);
  const set = (v: boolean) => {
    setCollapsed(v);
    try {
      window.localStorage.setItem(KEY, v ? '1' : '0');
    } catch {
      // storage unavailable: session only
    }
  };
  const rows = keyRows(kinds);
  if (rows.length === 0) return null;

  if (collapsed) {
    return (
      <HStack
        padding={1}
        className="gw-pop gw-pop-end"
        style={{ ...anchor, borderRadius: 'var(--radius-full)', ...SURFACE }}
      >
        <Button
          label="Show key"
          variant="ghost"
          size="sm"
          icon={<Icon icon={KeyRound} size="sm" />}
          onClick={() => set(false)}
        >
          Key
        </Button>
      </HStack>
    );
  }
  return (
    <VStack
      as="aside"
      aria-label="Map key"
      className="gw-pop gw-pop-end"
      style={{ ...anchor, maxWidth: 300, borderRadius: 'var(--radius-page, 20px)', ...SURFACE }}
    >
      <HStack
        justify="between"
        align="center"
        paddingInlineStart={4}
        paddingInlineEnd={2}
        paddingBlockStart={2}
      >
        <Text type="supporting" weight="medium" color="secondary" className="gw-caps">
          Key
        </Text>
        <IconButton
          label="Hide key"
          icon={<Icon icon={PanelRightClose} size="sm" />}
          variant="ghost"
          size="sm"
          onClick={() => set(true)}
        />
      </HStack>
      <VStack as="ul" gap={2} paddingInline={4} paddingBlockEnd={4} paddingBlockStart={1}>
        {rows.map(({ category, kind }) => (
          <HStack as="li" key={category.id} gap={2} align="center">
            <img src={poiIconUrl(kind)} width={22} height={22} alt="" />
            <Text type="supporting">{category.label}</Text>
          </HStack>
        ))}
      </VStack>
    </VStack>
  );
}
