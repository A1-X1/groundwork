import { HStack } from '@astryxdesign/core/HStack';
import { Spinner } from '@astryxdesign/core/Spinner';
import { Step, Stepper } from '@astryxdesign/core/Stepper';
import { Text } from '@astryxdesign/core/Text';
import { VStack } from '@astryxdesign/core/VStack';
import { SURFACE } from './FloatingPanel';

export const AGENT_STEPS = ['Choosing data', 'Profile', '3D model', 'Training', 'Results'] as const;

/** Map the agent's free-text step name to an index in AGENT_STEPS. */
export function stepIndex(step: unknown): number {
  const s = String(step ?? '').toLowerCase();
  if (/result|preview|score|done/.test(s)) return 4;
  if (/train|model fit|feasib/.test(s)) return 3;
  if (/3d|model|design|building/.test(s)) return 2;
  if (/profile|weight/.test(s)) return 1;
  return 0;
}

export interface ProgressLine {
  /** Seconds since the run started. */
  at: number;
  text: string;
}

export interface AgentProgressState {
  title: string;
  step: number;
  message: string | null;
  /** Detailed progress from the agent's events (phase is 1-based). */
  phaseIndex?: number;
  phaseTotal?: number;
  phaseLabel?: string;
  elapsed?: number;
  eta?: number;
  /** Most recent step details, newest last (a few lines, so users see it isn't stuck). */
  log?: ProgressLine[];
}

export const LOG_LINES = 6;

/** "1:49" from seconds. */
export function clock(s: number): string {
  const t = Math.max(0, Math.round(s));
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`;
}

/** "about 1 min left", "about 40 s left", "almost done". */
export function remaining(s: number): string {
  if (s <= 5) return 'almost done';
  if (s < 60) return `about ${Math.round(s / 10) * 10 || 10} s left`;
  return `about ${Math.round(s / 60)} min left`;
}

/** Fold one agent event into the progress state (phase, timing, detail log). */
export function applyAgentEvent(
  cur: AgentProgressState | null,
  e: Record<string, unknown>,
): AgentProgressState | null {
  const num = (k: string) => (typeof e[k] === 'number' ? (e[k] as number) : undefined);
  const phaseIndex = num('phase_index');
  const detail = typeof e.detail === 'string' && e.detail ? e.detail : null;
  if (phaseIndex === undefined && !detail) return cur;
  const base: AgentProgressState = cur ?? { title: 'Working on it', step: 0, message: null };
  const elapsed = num('elapsed_s') ?? base.elapsed;
  const next: AgentProgressState = {
    ...base,
    phaseIndex: phaseIndex ?? base.phaseIndex,
    phaseTotal: num('phase_total') ?? base.phaseTotal,
    phaseLabel: typeof e.phase_label === 'string' ? e.phase_label : base.phaseLabel,
    elapsed,
    eta: num('eta_s') ?? base.eta,
  };
  if (detail) {
    const log = [...(base.log ?? [])];
    if (log.at(-1)?.text !== detail) log.push({ at: elapsed ?? 0, text: detail });
    next.log = log.slice(-LOG_LINES);
    next.message = detail;
  }
  return next;
}

/** Floating card shown while the planning agent builds something. */
export function AgentProgress({ state }: { state: AgentProgressState }) {
  const detailed = state.phaseIndex != null && state.phaseTotal != null;
  return (
    <VStack
      gap={3}
      padding={4}
      width={520}
      maxWidth="calc(100vw - 32px)"
      className="gw-pop"
      role="status"
      aria-live="polite"
      style={{ pointerEvents: 'auto', borderRadius: 'var(--radius-element)', ...SURFACE }}
    >
      <HStack gap={2} align="center">
        <Spinner size="sm" />
        <Text weight="semibold">{state.title}</Text>
      </HStack>

      {detailed ? (
        <>
          {/* segmented bar: one segment per phase */}
          <HStack gap={1} aria-hidden>
            {Array.from({ length: state.phaseTotal! }, (_, i) => (
              <VStack
                key={i}
                style={{
                  flex: 1,
                  height: 6,
                  borderRadius: 'var(--radius-full)',
                  background:
                    i < state.phaseIndex! - 1
                      ? 'var(--color-accent)'
                      : i === state.phaseIndex! - 1
                        ? 'color-mix(in oklab, var(--color-accent) 55%, transparent)'
                        : 'var(--color-border)',
                }}
              />
            ))}
          </HStack>
          <Text type="supporting" color="secondary" hasTabularNumbers display="block">
            Step {state.phaseIndex} of {state.phaseTotal}
            {state.phaseLabel ? ` · ${state.phaseLabel}` : ''}
            {state.elapsed != null ? ` · ${clock(state.elapsed)} elapsed` : ''}
            {state.eta != null ? ` · ${remaining(state.eta)}` : ''}
          </Text>
        </>
      ) : (
        <Stepper activeStep={state.step} density="compact" label="Agent progress">
          {AGENT_STEPS.map((label, i) => (
            <Step
              key={label}
              step={i}
              label={label}
              status={i < state.step ? 'success' : undefined}
            />
          ))}
        </Stepper>
      )}

      {state.log && state.log.length > 0 ? (
        <VStack
          as="ol"
          gap={1}
          aria-label="Recent steps"
          style={{ maxHeight: 132, overflowY: 'auto', margin: 0, padding: 0, listStyle: 'none' }}
        >
          {state.log.map((l, i) => (
            <HStack as="li" key={`${l.at}-${i}`} gap={2} align="start">
              <Text type="code" color="secondary" hasTabularNumbers>
                {clock(l.at)}
              </Text>
              <Text
                type="supporting"
                color={i === state.log!.length - 1 ? undefined : 'secondary'}
                maxLines={1}
              >
                {l.text}
              </Text>
            </HStack>
          ))}
        </VStack>
      ) : (
        state.message && (
          <Text type="supporting" color="secondary" display="block" maxLines={2}>
            {state.message}
          </Text>
        )
      )}
    </VStack>
  );
}
