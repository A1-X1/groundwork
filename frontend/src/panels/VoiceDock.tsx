import { Button } from '@astryxdesign/core/Button';
import { HStack } from '@astryxdesign/core/HStack';
import { Icon } from '@astryxdesign/core/Icon';
import { IconButton } from '@astryxdesign/core/IconButton';
import { Text } from '@astryxdesign/core/Text';
import { VStack } from '@astryxdesign/core/VStack';
import { ChevronDown, Mic } from 'lucide-react';
import { useState, type ComponentProps } from 'react';
import { VoiceOrb } from '../map/VoiceOrb';

const KEY = 'groundwork.voiceDock.hidden';

function readHidden(): boolean {
  try {
    return window.localStorage.getItem(KEY) === '1';
  } catch {
    return false;
  }
}

/** The voice assistant in its own small card, with a hide control that collapses to a pill. */
export function VoiceDock(props: ComponentProps<typeof VoiceOrb>) {
  const [hidden, setHidden] = useState(readHidden);
  const set = (v: boolean) => {
    setHidden(v);
    try {
      window.localStorage.setItem(KEY, v ? '1' : '0');
    } catch {
      // storage unavailable: remember for this session only
    }
  };
  const surface = {
    pointerEvents: 'auto' as const,
    background: 'var(--color-background-card)',
    borderRadius: 'var(--radius-container)',
    boxShadow: 'var(--shadow-med)',
  };

  if (hidden) {
    return (
      <HStack padding={1} style={surface}>
        <Button
          label="Voice"
          variant="ghost"
          size="sm"
          icon={<Icon icon={Mic} size="sm" />}
          onClick={() => set(false)}
        />
      </HStack>
    );
  }
  return (
    <VStack gap={1} paddingInline={3} paddingBlock={2} width={200} style={surface}>
      <HStack justify="between" align="center">
        <Text type="supporting" weight="medium" color="secondary">
          Assistant
        </Text>
        <IconButton
          label="Hide voice assistant"
          icon={<Icon icon={ChevronDown} size="sm" />}
          variant="ghost"
          size="sm"
          onClick={() => set(true)}
        />
      </HStack>
      <VoiceOrb {...props} />
    </VStack>
  );
}
