import { Button } from '@astryxdesign/core/Button';
import { Icon } from '@astryxdesign/core/Icon';
import { Globe2 } from 'lucide-react';
import { HStack } from '@astryxdesign/core/HStack';
import { Link } from '@astryxdesign/core/Link';
import { Text } from '@astryxdesign/core/Text';
import { VStack } from '@astryxdesign/core/VStack';
import { API_URL, USE_FIXTURE } from '../api/client';
import { Logo } from './Logo';
import { cssGradient, RAMPS, type RampId } from '../lib/colour';

export interface LegendSpec {
  title: string;
  ramp: RampId;
  low: string;
  high: string;
}

export function TopBar({
  legend,
  onGlobe,
  onHome,
}: {
  legend: LegendSpec | null;
  onGlobe: () => void;
  onHome: () => void;
}) {
  return (
    <HStack
      justify="between"
      align="center"
      gap={4}
      paddingInline={4}
      paddingBlock={2}
      wrap="wrap"
      style={{
        paddingInlineStart: 'max(var(--spacing-4), env(safe-area-inset-left))',
        paddingInlineEnd: 'max(var(--spacing-4), env(safe-area-inset-right))',
      }}
    >
      <HStack gap={2} align="center">
        <Button label="Groundwork home" variant="ghost" onClick={onHome} icon={undefined}>
          <Logo size="md" />
        </Button>
      </HStack>

      {legend && (
        <VStack gap={1} width={280} aria-label={`Legend: ${legend.title}`} role="group">
          <HStack justify="between">
            <Text type="supporting" weight="medium">
              {legend.title}
            </Text>
          </HStack>
          <HStack
            height={8}
            aria-hidden
            style={{
              background: cssGradient(RAMPS[legend.ramp]),
              borderRadius: 'var(--radius-inner)',
            }}
          />
          <HStack justify="between">
            <Text type="supporting" color="secondary" hasTabularNumbers>
              {legend.low}
            </Text>
            <Text type="supporting" color="secondary" hasTabularNumbers>
              {legend.high}
            </Text>
          </HStack>
        </VStack>
      )}

      <HStack gap={4} align="center">
        {USE_FIXTURE && <Text color="secondary">Fixture data</Text>}
        <Button
          label="Globe"
          variant="ghost"
          size="sm"
          icon={<Icon icon={Globe2} size="sm" />}
          onClick={onGlobe}
        />
        <Link href={`${API_URL}/docs`} isExternalLink>
          API docs
        </Link>
      </HStack>
    </HStack>
  );
}
