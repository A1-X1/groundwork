import { describe, expect, it } from 'vitest';
import { applyAgentEvent, clock, LOG_LINES, remaining } from '../panels/AgentProgress';

describe('agent progress', () => {
  it('formats elapsed and remaining time', () => {
    expect(clock(109)).toBe('1:49');
    expect(remaining(70)).toBe('about 1 min left');
    expect(remaining(40)).toBe('about 40 s left');
    expect(remaining(3)).toBe('almost done');
  });

  it('starts a card from the first phase event and tracks phase, timing and details', () => {
    let s = applyAgentEvent(null, { type: 'tool_call', phase_index: 3, phase_total: 8, phase_label: 'Building data', elapsed_s: 109, eta_s: 65, detail: 'Adding data: Distance to parking' }); // prettier-ignore
    expect(s?.phaseIndex).toBe(3);
    expect(s?.log?.at(-1)).toEqual({ at: 109, text: 'Adding data: Distance to parking' });
    s = applyAgentEvent(s, { type: 'progress', detail: 'Building data 2 of 3: Retail land share' });
    expect(s?.phaseIndex).toBe(3); // kept from before
    expect(s?.message).toBe('Building data 2 of 3: Retail land share');
  });

  it('keeps only the last few detail lines and ignores events without progress info', () => {
    let s = applyAgentEvent(null, { type: 'tool_call', phase_index: 1, phase_total: 8 });
    for (let i = 0; i < 10; i++)
      s = applyAgentEvent(s, { type: 'progress', detail: `line ${i}`, elapsed_s: i });
    expect(s?.log).toHaveLength(LOG_LINES);
    expect(s?.log?.at(-1)?.text).toBe('line 9');
    expect(applyAgentEvent(s, { type: 'message', content: 'hi' })).toBe(s);
  });
});
