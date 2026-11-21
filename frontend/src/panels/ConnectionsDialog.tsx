import { Button } from '@astryxdesign/core/Button';
import { Dialog, DialogHeader } from '@astryxdesign/core/Dialog';
import { Heading } from '@astryxdesign/core/Heading';
import { HStack } from '@astryxdesign/core/HStack';
import { Link } from '@astryxdesign/core/Link';
import { Skeleton } from '@astryxdesign/core/Skeleton';
import { StatusDot } from '@astryxdesign/core/StatusDot';
import { Text } from '@astryxdesign/core/Text';
import { TextInput } from '@astryxdesign/core/TextInput';
import { VStack } from '@astryxdesign/core/VStack';
import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import type { AzureConfig, Connections } from '../api/types';

interface Props {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  /** Shown when the planning agent asked for Azure before continuing. */
  reason?: string | null;
}

const EMPTY: AzureConfig = { subscription_id: '', resource_group: '', workspace: '' };

export function ConnectionsDialog({ isOpen, onOpenChange, reason }: Props) {
  const [conn, setConn] = useState<Connections | null>(null);
  const [form, setForm] = useState<AzureConfig>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const c = await api.connections();
      setConn(c);
      if (c.azure_ml.config) setForm(c.azure_ml.config);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load connections.');
    }
  }, []);

  useEffect(() => {
    if (isOpen) void refresh();
  }, [isOpen, refresh]);

  // Poll while a device-code sign-in is pending.
  useEffect(() => {
    if (!isOpen || conn?.azure_ml.status !== 'pending') return;
    const t = window.setInterval(() => void refresh(), 3000);
    return () => window.clearInterval(t);
  }, [isOpen, conn?.azure_ml.status, refresh]);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong.');
    } finally {
      setBusy(false);
    }
  };

  const az = conn?.azure_ml;
  const valid = form.subscription_id && form.resource_group && form.workspace;

  return (
    <Dialog isOpen={isOpen} onOpenChange={onOpenChange} width={520} purpose="form">
      <DialogHeader title="Connections" onOpenChange={onOpenChange} />
      <VStack gap={6} padding={4}>
        {reason && (
          <Text display="block" textWrap="pretty">
            {reason}
          </Text>
        )}
        {!conn ? (
          <Skeleton height={220} />
        ) : (
          <>
            <VStack gap={2}>
              <HStack gap={2} align="center">
                <StatusDot
                  variant={conn.mistral.configured ? 'success' : 'neutral'}
                  label={conn.mistral.configured ? 'Connected' : 'Not configured'}
                />
                <Heading level={3}>Mistral</Heading>
              </HStack>
              <Text color="secondary" display="block" textWrap="pretty">
                {conn.mistral.configured
                  ? `Connected: ${conn.mistral.chat_model} for commands, ${conn.mistral.voxtral_model} for voice.`
                  : 'Not configured. Add MISTRAL_API_KEY to the server’s .env; voice falls back to the browser.'}
              </Text>
            </VStack>

            <VStack gap={3}>
              <HStack gap={2} align="center">
                <StatusDot
                  variant={
                    az?.status === 'signed_in'
                      ? 'success'
                      : az?.status === 'error'
                        ? 'error'
                        : 'neutral'
                  }
                  label={az?.status === 'signed_in' ? 'Signed in' : 'Not signed in'}
                  isPulsing={az?.status === 'pending'}
                />
                <Heading level={3}>Azure Machine Learning</Heading>
              </HStack>
              <Text color="secondary" display="block" textWrap="pretty">
                The planning agent trains feasibility models in your Azure ML workspace, or locally
                when none is connected. Only these coordinates are stored, never credentials.
              </Text>
              <TextInput
                label="Subscription ID"
                value={form.subscription_id}
                onChange={(v: string) => setForm((f) => ({ ...f, subscription_id: v.trim() }))}
              />
              <HStack gap={2}>
                <TextInput
                  label="Resource group"
                  value={form.resource_group}
                  onChange={(v: string) => setForm((f) => ({ ...f, resource_group: v.trim() }))}
                  width="100%"
                />
                <TextInput
                  label="Workspace"
                  value={form.workspace}
                  onChange={(v: string) => setForm((f) => ({ ...f, workspace: v.trim() }))}
                  width="100%"
                />
              </HStack>

              {az?.status === 'pending' && az.verification_uri && (
                <VStack gap={1}>
                  <Text display="block">
                    Open{' '}
                    <Link href={az.verification_uri} isExternalLink>
                      {az.verification_uri}
                    </Link>{' '}
                    and enter this code:
                  </Text>
                  <Text type="code" size="xl" weight="semibold">
                    {az.user_code}
                  </Text>
                </VStack>
              )}
              {az?.status === 'signed_in' && (
                <Text display="block">Signed in{az.account ? ` as ${az.account}` : ''}.</Text>
              )}
              {az?.message && az.status !== 'pending' && (
                <Text color="secondary" display="block" role="status" textWrap="pretty">
                  {az.message}
                </Text>
              )}
              {error && (
                <Text color="secondary" display="block" role="alert">
                  {error}
                </Text>
              )}

              <HStack gap={2} wrap="wrap">
                <Button
                  label="Sign in to Azure ML"
                  variant="primary"
                  isDisabled={!valid || az?.status === 'unavailable'}
                  isLoading={busy || az?.status === 'pending'}
                  onClick={() =>
                    void run(async () => {
                      await api.saveAzure(form);
                      await api.azureLogin();
                    })
                  }
                />
                <Button
                  label="Save workspace"
                  variant="secondary"
                  isDisabled={!valid}
                  onClick={() => void run(() => api.saveAzure(form))}
                />
                {az?.configured && (
                  <Button
                    label="Disconnect"
                    variant="ghost"
                    onClick={() =>
                      void run(async () => {
                        await api.forgetAzure();
                        setForm(EMPTY);
                      })
                    }
                  />
                )}
              </HStack>
            </VStack>
          </>
        )}
      </VStack>
    </Dialog>
  );
}
