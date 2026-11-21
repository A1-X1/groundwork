import { Button } from '@astryxdesign/core/Button';
import { HStack } from '@astryxdesign/core/HStack';
import { Icon } from '@astryxdesign/core/Icon';
import { IconButton } from '@astryxdesign/core/IconButton';
import { ToggleButton } from '@astryxdesign/core/ToggleButton';
import { Text } from '@astryxdesign/core/Text';
import { VStack } from '@astryxdesign/core/VStack';
import { ChevronDown, FlaskConical, Mic, MicOff, Send, Volume2, VolumeX } from 'lucide-react';
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

type Props = ComponentProps<typeof VoiceOrb> & {
  muted: boolean;
  onToggleMute: () => void;
  handsFree: boolean;
  onToggleHandsFree: () => void;
  /** Optional: stop listening and send what has been heard so far. */
  onSubmit?: () => void;
};

/** The voice assistant in its own small card, with a hide control that collapses to a pill. */
export function VoiceDock({
  muted,
  onToggleMute,
  handsFree,
  onToggleHandsFree,
  onSubmit,
  ...props
}: Props) {
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
    border: '1px solid var(--color-border)',
    borderRadius: 'var(--radius-element)',
    boxShadow: 'var(--shadow-high)',
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
    <VStack gap={2} padding={4} width={260} style={surface}>
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
      <HStack gap={2} align="center">
        {/* Each utterance sends itself when you pause; Send is an optional early finish. */}
        <ToggleButton
          label={handsFree ? 'Mic on' : 'Mic off'}
          tooltip={
            handsFree ? 'Turn the mic off' : 'Turn the mic on; just speak, it sends when you pause'
          }
          isPressed={handsFree}
          onPressedChange={onToggleHandsFree}
          icon={<Icon icon={MicOff} size="sm" />}
          pressedIcon={<Icon icon={Mic} size="sm" />}
          isDisabled={!props.isAvailable}
          size="sm"
        />
        {onSubmit && (
          <IconButton
            label="Send what I said"
            tooltip="Stop listening and process what it has heard"
            icon={<Icon icon={Send} size="sm" />}
            variant="ghost"
            size="sm"
            isDisabled={!handsFree || props.state !== 'listening'}
            onClick={onSubmit}
          />
        )}
        <IconButton
          label={muted ? 'Unmute spoken replies' : 'Mute spoken replies'}
          tooltip={muted ? 'Replies are silent' : 'Replies are spoken'}
          icon={<Icon icon={muted ? VolumeX : Volume2} size="sm" />}
          variant="ghost"
          size="sm"
          onClick={onToggleMute}
        />
        <IconButton
          label="Open the Voice Lab"
          tooltip="Voice Lab: test Voxtral with timings and raw output"
          icon={<Icon icon={FlaskConical} size="sm" />}
          variant="ghost"
          size="sm"
          href="#voice-lab"
        />
      </HStack>
    </VStack>
  );
}
