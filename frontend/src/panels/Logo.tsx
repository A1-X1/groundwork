/**
 * Groundwork logo: a hexagon outline (one cell of the map grid) holding a stacked layer, the
 * "ground" you build on, followed by the wordmark. Keep the `size` contract
 * (inherit = scales with the surrounding headline). The favicon (public/favicon.svg) uses
 * the same mark.
 */
import { Text } from '@astryxdesign/core/Text';

/** The mark on its own, coloured with the theme accent. */
export function LogoMark({ size }: { size: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      width={size}
      height={size}
      aria-hidden
      style={{ display: 'inline-block', flex: 'none', transform: 'translateY(0.16em)' }}
    >
      <path
        d="M16 2.6 27.6 9.3v13.4L16 29.4 4.4 22.7V9.3z"
        fill="none"
        stroke="var(--color-accent)"
        strokeWidth="2.6"
        strokeLinejoin="round"
      />
      {/* top face of the layer */}
      <path d="M16 9.2 22.4 12.9 16 16.6 9.6 12.9z" fill="var(--color-accent)" />
      {/* the layer's sides, a V-shaped band below it */}
      <path
        d="M9.6 15.4 16 19.1 22.4 15.4v2.9L16 22l-6.4-3.7z"
        fill="var(--color-accent)"
        opacity="0.85"
      />
    </svg>
  );
}

export function Logo({ size = 'inherit' }: { size?: 'inherit' | 'md' }) {
  return (
    <Text
      type="inherit"
      weight="semibold"
      color="inherit"
      aria-label="Groundwork"
      style={{
        display: 'inline-flex',
        alignItems: 'baseline',
        gap: '0.28em',
        fontSize: size === 'md' ? 'var(--font-size-lg, 1.25rem)' : 'inherit',
        letterSpacing: '-0.015em',
        whiteSpace: 'nowrap',
      }}
    >
      <LogoMark size="1.05em" />
      Groundwork
    </Text>
  );
}
