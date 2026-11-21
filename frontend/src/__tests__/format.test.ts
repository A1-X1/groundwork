import { describe, expect, it } from 'vitest';
import { formatRank, formatRaw, formatScore, formatSigned } from '../lib/format';

describe('format', () => {
  it('formats scores and signed contributions', () => {
    expect(formatScore(0.823)).toBe('82');
    expect(formatScore(null)).toBe('—');
    expect(formatSigned(0.021)).toBe('+2.1');
    expect(formatSigned(-0.05)).toBe('−5');
  });
  it('formats raw units', () => {
    expect(formatRaw(1250, 'm')).toBe('1.3 km');
    expect(formatRaw(450, 'm')).toBe('450 m');
    expect(formatRaw(525000, '£')).toBe('£525,000');
    expect(formatRaw(1, 'flag')).toBe('Yes');
    expect(formatRank(3, 2122)).toBe('3 of 2,122');
  });
});
