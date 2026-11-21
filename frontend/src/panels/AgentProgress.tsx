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

export interface AgentProgressState {
  title: string;
  step: number;
  message: string | null;
}

/** Floating card shown while the planning agent builds something (SHOW_PROGRESS). */
export function AgentProgress({ state }: { state: AgentProgressState }) {
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
      {state.message && (
        <Text type="supporting" color="secondary" display="block" maxLines={2}>
          {state.message}
        </Text>
      )}
    </VStack>
  );
}
