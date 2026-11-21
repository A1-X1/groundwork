import { HStack } from '@astryxdesign/core/HStack';
import { Icon } from '@astryxdesign/core/Icon';
import { IconButton } from '@astryxdesign/core/IconButton';
import { Text } from '@astryxdesign/core/Text';
import { TextInput } from '@astryxdesign/core/TextInput';
import { VStack } from '@astryxdesign/core/VStack';
import { SendHorizontal } from 'lucide-react';
import { useState } from 'react';

interface Props {
  onSubmit: (text: string, onProgress?: (msg: string) => void) => Promise<string>;
}

/** Typed commands. Voice goes through the orb (VoiceOrb + useVoice). */
export function CommandBar({ onSubmit }: Props) {
  const [text, setText] = useState('');
  const [reply, setReply] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const q = text.trim();
    if (!q || busy) return;
    setBusy(true);
    setText(''); // accepted: clear straight away
    (document.activeElement as HTMLElement | null)?.blur();
    try {
      setReply(await onSubmit(q, (m) => setReply(m)));
    } catch (e) {
      setText(q); // keep the text only when it failed, so it can be retried
      setReply(e instanceof Error ? e.message : 'Something went wrong.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <VStack gap={1} width="100%" maxWidth={560}>
      <HStack gap={1} align="end">
        <TextInput
          label="Ask Groundwork"
          isLabelHidden
          placeholder="Try “best school sites”, “fly to Tokyo”, “thermal view”"
          value={text}
          onChange={(v: string) => setText(v)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void submit();
          }}
          width="100%"
        />
        <IconButton
          label="Send command"
          icon={<Icon icon={SendHorizontal} size="sm" />}
          variant="secondary"
          isLoading={busy}
          onClick={() => void submit()}
        />
      </HStack>
      {reply && (
        <Text type="supporting" color="secondary" display="block" role="status" maxLines={2}>
          {reply}
        </Text>
      )}
    </VStack>
  );
}
