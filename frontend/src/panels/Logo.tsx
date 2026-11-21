/**
 * Placeholder Groundwork logo: a hex mark and wordmark. Swap for the real logo later;
 * keep the `size` contract (inherit = scales with the surrounding headline).
 */
import { Text } from '@astryxdesign/core/Text';

function HexMark({ size }: { size: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      width={size}
      height={size}
      aria-hidden
      style={{ display: 'inline-block', verticalAlign: '-0.12em', flex: 'none' }}
    >
      <path fill="var(--color-accent)" d="M16 1.5 28.6 8.75v14.5L16 30.5 3.4 23.25V8.75z" />
      <path
        fill="var(--color-background-body)"
        d="M16 9.5 21.6 12.75v6.5L16 22.5l-5.6-3.25v-6.5z"
      />
    </svg>
  );
}

export function Logo({ size = 'inherit' }: { size?: 'inherit' | 'md' }) {
  return (
    <Text
      type="inherit"
      weight="bold"
      color="inherit"
      aria-label="Groundwork"
      style={{
        display: 'inline-flex',
        alignItems: 'baseline',
        gap: '0.22em',
        fontSize: size === 'md' ? 'var(--font-size-lg, 1.25rem)' : 'inherit',
        letterSpacing: '-0.02em',
        whiteSpace: 'nowrap',
      }}
    >
      <HexMark size="0.9em" />
      Groundwork
    </Text>
  );
}
