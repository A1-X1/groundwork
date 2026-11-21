import { Button } from '@astryxdesign/core/Button';
import { Dialog, DialogHeader } from '@astryxdesign/core/Dialog';
import { HStack } from '@astryxdesign/core/HStack';
import { Link } from '@astryxdesign/core/Link';
import { Skeleton } from '@astryxdesign/core/Skeleton';
import { StatusDot } from '@astryxdesign/core/StatusDot';
import { Text } from '@astryxdesign/core/Text';
import { TextInput } from '@astryxdesign/core/TextInput';
import { VStack } from '@astryxdesign/core/VStack';
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { api } from '../api/client';
import type { AzureConfig, Connections } from '../api/types';
import { MicrosoftLogo, MistralLogo } from './BrandLogos';

interface Props {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  /** Shown when the planning agent asked for a connection before continuing. */
  reason?: string | null;
}

const EMPTY: AzureConfig = { subscription_id: '', resource_group: '', workspace: '' };

function Row({
  logo,
  name,
  connected,
  pending,
  detail,
  children,
}: {
  logo: ReactNode;
  name: string;
  connected: boolean;
  pending?: boolean;
  detail: string;
  children: ReactNode;
}) {
  return (
    <VStack gap={3}>
      <HStack gap={3} align="center">
        {logo}
        <VStack gap={0.5}>
          <HStack gap={2} align="center">
            <Text weight="semibold">{name}</Text>
            <StatusDot
              variant={connected ? 'success' : 'neutral'}
              label={connected ? 'Connected' : 'Not connected'}
              isPulsing={pending}
            />
          </HStack>
          <Text type="supporting" color="secondary" textWrap="pretty">
            {detail}
          </Text>
        </VStack>
      </HStack>
      {children}
    </VStack>
  );
}

export function ConnectionsDialog({ isOpen, onOpenChange, reason }: Props) {
  const [conn, setConn] = useState<Connections | null>(null);
  const [form, setForm] = useState<AzureConfig>(EMPTY);
  const [key, setKey] = useState('');
  const [open, setOpen] = useState<'mistral' | 'azure' | null>(null);
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
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong.');
      return false;
    } finally {
      setBusy(false);
    }
  };

  const az = conn?.azure_ml;
  const valid = form.subscription_id && form.resource_group && form.workspace;

  return (
    <Dialog isOpen={isOpen} onOpenChange={onOpenChange} width={480} purpose="form">
      <DialogHeader title="Connections" onOpenChange={onOpenChange} />
      <VStack gap={8} padding={4} paddingBlockEnd={6}>
        {reason && (
          <Text display="block" textWrap="pretty">
            {reason}
          </Text>
        )}
        {!conn ? (
          <Skeleton height={220} />
        ) : (
          <>
            <Row
              logo={<MistralLogo size={28} />}
              name="Mistral AI"
              connected={conn.mistral.configured}
              detail={
                conn.mistral.configured
                  ? `${conn.mistral.chat_model} for commands · ${conn.mistral.voxtral_model} for voice`
                  : 'Voice, commands and the planning agent'
              }
            >
              {conn.mistral.configured ? (
                <Button
                  label="Disconnect Mistral"
                  variant="ghost"
                  size="sm"
                  onClick={() => void run(() => api.forgetMistral())}
                />
              ) : open === 'mistral' ? (
                <VStack gap={2}>
                  <TextInput
                    label="Mistral API key"
                    type="password"
                    autoComplete="off"
                    value={key}
                    onChange={(v: string) => setKey(v)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && key.trim()) {
                        void run(() => api.saveMistral(key.trim())).then((ok) => ok && setKey(''));
                      }
                    }}
                    hasAutoFocus
                  />
                  <Text type="supporting" color="secondary" display="block">
                    Create one at{' '}
                    <Link href="https://console.mistral.ai/api-keys" isExternalLink>
                      console.mistral.ai
                    </Link>
                    . It's kept on the Groundwork server only.
                  </Text>
                  <HStack gap={2}>
                    <Button
                      label="Save key"
                      variant="primary"
                      isDisabled={!key.trim()}
                      isLoading={busy}
                      onClick={() =>
                        void run(() => api.saveMistral(key.trim())).then((ok) => ok && setKey(''))
                      }
                    />
                    <Button label="Cancel" variant="ghost" onClick={() => setOpen(null)} />
                  </HStack>
                </VStack>
              ) : (
                <Button
                  label="Connect with Mistral"
                  variant="secondary"
                  size="lg"
                  width="100%"
                  icon={<MistralLogo />}
                  onClick={() => setOpen('mistral')}
                />
              )}
            </Row>

            <Row
              logo={<MicrosoftLogo size={26} />}
              name="Azure Machine Learning"
              connected={az?.status === 'signed_in'}
              pending={az?.status === 'pending'}
              detail={
                az?.status === 'signed_in'
                  ? `Signed in${az.account ? ` as ${az.account}` : ''} · ${az.config?.workspace ?? ''}`
                  : 'Trains feasibility models; local training is used until you connect'
              }
            >
              {az?.status === 'pending' && az.verification_uri ? (
                <VStack gap={1}>
                  <Text display="block">
                    Open{' '}
                    <Link href={az.verification_uri} isExternalLink>
                      {az.verification_uri}
                    </Link>{' '}
                    and enter:
                  </Text>
                  <Text type="code" size="xl" weight="semibold">
                    {az.user_code}
                  </Text>
                </VStack>
              ) : az?.status === 'signed_in' ? (
                <Button
                  label="Disconnect Azure"
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    void run(async () => {
                      await api.forgetAzure();
                      setForm(EMPTY);
                    })
                  }
                />
              ) : open === 'azure' ? (
                <VStack gap={3}>
                  <TextInput
                    label="Subscription ID"
                    value={form.subscription_id}
                    onChange={(v: string) => setForm((f) => ({ ...f, subscription_id: v.trim() }))}
                    hasAutoFocus
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
                  <HStack gap={2}>
                    <Button
                      label="Continue to Microsoft"
                      variant="primary"
                      isDisabled={!valid || az?.status === 'unavailable'}
                      isLoading={busy}
                      onClick={() =>
                        void run(async () => {
                          await api.saveAzure(form);
                          await api.azureLogin();
                        })
                      }
                    />
                    <Button label="Cancel" variant="ghost" onClick={() => setOpen(null)} />
                  </HStack>
                </VStack>
              ) : (
                <Button
                  label="Sign in with Microsoft"
                  variant="secondary"
                  size="lg"
                  width="100%"
                  icon={<MicrosoftLogo />}
                  onClick={() => setOpen('azure')}
                />
              )}
              {az?.message && az.status !== 'pending' && az.status !== 'signed_in' && (
                <Text type="supporting" color="secondary" display="block" role="status">
                  {az.message}
                </Text>
              )}
            </Row>

            {error && (
              <Text color="secondary" display="block" role="alert">
                {error}
              </Text>
            )}
          </>
        )}
      </VStack>
    </Dialog>
  );
}
