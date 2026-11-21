import { Button } from '@astryxdesign/core/Button';
import { HStack } from '@astryxdesign/core/HStack';
import { Icon } from '@astryxdesign/core/Icon';
import { IconButton } from '@astryxdesign/core/IconButton';
import { Text } from '@astryxdesign/core/Text';
import { VStack } from '@astryxdesign/core/VStack';
import { PanelLeftClose, PanelRightClose, type LucideIcon } from 'lucide-react';
import { useState, type ReactNode } from 'react';

/** Inset between floating cards and the viewport edge (respects safe areas). */
export const EDGE = 'max(var(--spacing-4), env(safe-area-inset-left))';
export const SURFACE = {
  background: 'var(--color-background-card)',
  border: '1px solid var(--color-border)',
  boxShadow: 'var(--shadow-high)',
} as const;

function remembered(key: string): boolean {
  try {
    return window.localStorage.getItem(key) === '1';
  } catch {
    return false;
  }
}

interface Props {
  side: 'start' | 'end';
  label: string;
  icon: LucideIcon;
  width: number;
  /** Top offset (px) so the card clears the navbar. */
  top: number;
  /** Space kept free at the bottom for map controls and the voice dock. */
  bottom: number;
  children: ReactNode;
}

/**
 * A card that floats over the map, inset from the viewport edge, with fully rounded corners and
 * a soft shadow. Collapses to a pill at its own edge so the map can take the whole screen.
 */
export function FloatingPanel({ side, label, icon, width, top, bottom, children }: Props) {
  const key = `groundwork.panel.${label.toLowerCase()}.collapsed`;
  const [collapsed, setCollapsed] = useState(() => remembered(key));
  const set = (v: boolean) => {
    setCollapsed(v);
    try {
      window.localStorage.setItem(key, v ? '1' : '0');
    } catch {
      // storage unavailable: session only
    }
  };
  const anchor = side === 'start' ? { insetInlineStart: EDGE } : { insetInlineEnd: EDGE };

  if (collapsed) {
    return (
      <HStack
        padding={1}
        className={`gw-pop gw-pop-${side}`}
        style={{
          position: 'absolute',
          top,
          ...anchor,
          zIndex: 4,
          borderRadius: 'var(--radius-full)',
          ...SURFACE,
        }}
      >
        <Button
          label={`Show ${label.toLowerCase()}`}
          variant="ghost"
          size="sm"
          icon={<Icon icon={icon} size="sm" />}
          onClick={() => set(false)}
        >
          {label}
        </Button>
      </HStack>
    );
  }
  return (
    <VStack
      as="aside"
      aria-label={label}
      width={width}
      className={`gw-pop gw-pop-${side}`}
      style={{
        position: 'absolute',
        top,
        ...anchor,
        zIndex: 4,
        maxHeight: `calc(100% - ${top + bottom}px)`,
        borderRadius: 'var(--radius-page, 20px)',
        overflow: 'hidden',
        ...SURFACE,
      }}
    >
      <HStack
        justify="between"
        align="center"
        paddingInlineStart={4}
        paddingInlineEnd={2}
        paddingBlockStart={2}
      >
        <Text type="supporting" weight="medium" color="secondary" className="gw-caps">
          {label}
        </Text>
        <IconButton
          label={`Hide ${label.toLowerCase()}`}
          icon={<Icon icon={side === 'start' ? PanelLeftClose : PanelRightClose} size="sm" />}
          variant="ghost"
          size="sm"
          onClick={() => set(true)}
        />
      </HStack>
      <VStack isScrollable paddingInline={4} paddingBlockEnd={4} paddingBlockStart={1}>
        {children}
      </VStack>
    </VStack>
  );
}
