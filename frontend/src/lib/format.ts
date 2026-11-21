const nf = (max: number) =>
  new Intl.NumberFormat('en-GB', { maximumFractionDigits: max, minimumFractionDigits: 0 });

const pct = new Intl.NumberFormat('en-GB', { style: 'percent', maximumFractionDigits: 0 });
const gbp = new Intl.NumberFormat('en-GB', {
  style: 'currency',
  currency: 'GBP',
  maximumFractionDigits: 0,
});

/** A 0–1 score as an integer out of 100. */
export function formatScore(score: number | null | undefined): string {
  return score == null ? '—' : nf(0).format(score * 100);
}

export function formatPercent(v: number | null | undefined): string {
  return v == null ? '—' : pct.format(v);
}

export function formatSigned(v: number): string {
  const s = nf(1).format(Math.abs(v * 100));
  return `${v >= 0 ? '+' : '−'}${s}`;
}

export function formatRaw(value: number | undefined, unit: string): string {
  if (value == null || !Number.isFinite(value)) return '—';
  switch (unit) {
    case '£':
      return gbp.format(value);
    case 'm':
      return value >= 1000 ? `${nf(1).format(value / 1000)} km` : `${nf(0).format(value)} m`;
    case 'flag':
      return value >= 0.5 ? 'Yes' : 'No';
    case 'share':
      return pct.format(value);
    case 'index':
      return nf(2).format(value);
    default: {
      const digits = Math.abs(value) >= 100 ? 0 : 1;
      return `${nf(digits).format(value)} ${unit}`.trim();
    }
  }
}

export function formatRank(rank: number | null, total: number): string {
  if (rank == null) return 'Not ranked';
  return `${nf(0).format(rank)} of ${nf(0).format(total)}`;
}
