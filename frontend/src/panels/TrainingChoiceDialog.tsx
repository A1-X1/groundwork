/**
 * Shown when the planning agent wants to train but Azure ML isn't connected
 * (`action_required {action: "choose_training"}`): connect Azure, or let the Mistral data
 * aggregator agent build the profile instead.
 */
import { Button } from '@astryxdesign/core/Button';
import { Dialog, DialogHeader } from '@astryxdesign/core/Dialog';
import { HStack } from '@astryxdesign/core/HStack';
import { Text } from '@astryxdesign/core/Text';
import { VStack } from '@astryxdesign/core/VStack';
import { MicrosoftLogo, MistralLogo } from './BrandLogos';

interface Props {
  isOpen: boolean;
  message: string | null;
  onOpenChange: (open: boolean) => void;
  onConnectAzure: () => void;
  onUseAggregator: () => void;
}

export function TrainingChoiceDialog({
  isOpen,
  message,
  onOpenChange,
  onConnectAzure,
  onUseAggregator,
}: Props) {
  return (
    <Dialog isOpen={isOpen} onOpenChange={onOpenChange} width={460}>
      <DialogHeader title="Azure ML isn’t connected" onOpenChange={onOpenChange} />
      <VStack gap={5} paddingInline={6} paddingBlockEnd={6}>
        <Text color="secondary" display="block" textWrap="pretty">
          {message ??
            'Training the feasibility model needs Azure ML. Connect it, or let the Mistral data aggregator build the profile from the data sources instead.'}
        </Text>
        <HStack gap={2} justify="end" wrap="wrap">
          <Button
            label="Connect Azure ML"
            variant="secondary"
            icon={<MicrosoftLogo />}
            onClick={onConnectAzure}
          />
          <Button
            label="Use Mistral data aggregator"
            variant="primary"
            icon={<MistralLogo />}
            onClick={onUseAggregator}
          />
        </HStack>
      </VStack>
    </Dialog>
  );
}
