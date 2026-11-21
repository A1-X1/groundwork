/**
 * Voice Lab (#voice-lab): test Voxtral speech-to-text and the command parser end to end,
 * with timings and raw JSON. Uses the same API endpoints as the app.
 */
import { Banner } from '@astryxdesign/core/Banner';
import { Button } from '@astryxdesign/core/Button';
import { CodeBlock } from '@astryxdesign/core/CodeBlock';
import { FileInput } from '@astryxdesign/core/FileInput';
import { Heading } from '@astryxdesign/core/Heading';
import { HStack } from '@astryxdesign/core/HStack';
import { Link } from '@astryxdesign/core/Link';
import { MetadataList, MetadataListItem } from '@astryxdesign/core/MetadataList';
import { Switch } from '@astryxdesign/core/Switch';
import { Text } from '@astryxdesign/core/Text';
import { TextInput } from '@astryxdesign/core/TextInput';
import { VStack } from '@astryxdesign/core/VStack';
import { useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import type { AssistantResponse } from '../api/types';
import { VoiceOrb } from '../map/VoiceOrb';
import type { VoiceState } from '../state/useVoice';
import { Logo } from './Logo';

interface Run {
  heard: string;
  transcribeMs: number | null;
  parseMs: number;
  audioKb: number | null;
  result: AssistantResponse;
}

export function VoiceLab() {
  const [status, setStatus] = useState<{ mistral: boolean; voxtral_model: string | null } | null>(
    null,
  );
  const [state, setState] = useState<VoiceState>('idle');
  const [message, setMessage] = useState<string | null>(null);
  const [text, setText] = useState('');
  const [speakReplies, setSpeakReplies] = useState(true);
  const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const level = useRef(0);
  const stopRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    api
      .assistantStatus()
      .then(setStatus)
      .catch((e: unknown) => setError(String((e as Error).message)));
  }, []);

  const speak = (t: string) => {
    if (!speakReplies || !('speechSynthesis' in window)) return setState('idle');
    const u = new SpeechSynthesisUtterance(t);
    u.lang = 'en-GB';
    u.onstart = () => setState('speaking');
    u.onboundary = () => (level.current = 0.9);
    u.onend = u.onerror = () => {
      level.current = 0;
      setState('idle');
    };
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
  };

  const parse = async (heard: string, transcribeMs: number | null, audioKb: number | null) => {
    setState('thinking');
    const t0 = performance.now();
    const result = await api.assistant(heard, {});
    const run = { heard, transcribeMs, parseMs: performance.now() - t0, audioKb, result };
    setRuns((r) => [run, ...r].slice(0, 10));
    setMessage(result.reply);
    speak(result.reply);
  };

  const transcribe = async (blob: Blob) => {
    setError(null);
    setState('thinking');
    try {
      const t0 = performance.now();
      const { text: heard } = await api.transcribe(blob);
      const ms = performance.now() - t0;
      await parse(heard || '(nothing heard)', ms, Math.round(blob.size / 1024));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Transcription failed.');
      setState('idle');
    }
  };

  const start = async () => {
    if (state === 'listening') return;
    setError(null);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError('Microphone access was blocked. Allow it in the browser, or upload a clip below.');
      return;
    }
    const ctx = new AudioContext();
    const an = ctx.createAnalyser();
    an.fftSize = 512;
    ctx.createMediaStreamSource(stream).connect(an);
    const buf = new Uint8Array(an.fftSize);
    let raf = 0;
    const meter = () => {
      an.getByteTimeDomainData(buf);
      let sum = 0;
      for (const v of buf) sum += ((v - 128) / 128) ** 2;
      level.current = Math.min(1, level.current * 0.6 + Math.sqrt(sum / buf.length) * 2);
      raf = requestAnimationFrame(meter);
    };
    raf = requestAnimationFrame(meter);
    const rec = new MediaRecorder(stream);
    const chunks: Blob[] = [];
    rec.ondataavailable = (e) => {
      if (e.data.size) chunks.push(e.data);
    };
    rec.onstop = () => {
      cancelAnimationFrame(raf);
      stream.getTracks().forEach((t) => t.stop());
      void ctx.close();
      level.current = 0;
      void transcribe(new Blob(chunks, { type: rec.mimeType || 'audio/webm' }));
    };
    stopRef.current = () => rec.state === 'recording' && rec.stop();
    rec.start();
    setState('listening');
    window.setTimeout(() => stopRef.current?.(), 12000);
  };

  const ready = status?.mistral;

  return (
    <VStack height="100%" isScrollable align="center" paddingInline={6} paddingBlock={8}>
      <VStack gap={8} width="100%" maxWidth={760}>
        <VStack gap={2}>
          <HStack gap={2} align="center">
            <Logo size="md" />
            <Text color="secondary">Voice Lab</Text>
          </HStack>
          <Heading level={1} textWrap="balance">
            Test Voxtral voice commands
          </Heading>
          <Text color="secondary" display="block" textWrap="pretty">
            Speak a command, Voxtral transcribes it, and the assistant turns it into map commands.
            Nothing here changes the map. <Link href="#">Back to Groundwork</Link>
          </Text>
        </VStack>

        {status && !ready && (
          <Banner
            status="warning"
            title="No Mistral key on the server"
            description="Add MISTRAL_API_KEY to the repo's .env (or use Connections in the app) and restart `make dev`. Typed commands still work with the offline parser."
            collapsible={false}
          />
        )}
        {error && (
          <Banner status="error" title="Something failed" description={error} collapsible={false} />
        )}

        <HStack gap={8} align="center" wrap="wrap">
          <VoiceOrb
            state={state}
            level={level}
            message={message}
            isAvailable={!!ready}
            onStart={() => void start()}
            onStop={() => stopRef.current?.()}
          />
          <VStack gap={3} style={{ flex: 1, minWidth: 260 }}>
            <MetadataList>
              <MetadataListItem label="Speech-to-text">
                <Text>{ready ? (status?.voxtral_model ?? 'Voxtral') : 'not configured'}</Text>
              </MetadataListItem>
              <MetadataListItem label="Mode">
                <Text>Tap to talk (up to 12 s), or hold</Text>
              </MetadataListItem>
            </MetadataList>
            <FileInput
              label="Or upload a recording"
              accept="audio/*"
              value={file}
              onChange={(files: File[] | File | null) => {
                const f = (Array.isArray(files) ? files[0] : files) ?? null;
                setFile(f);
                if (f) void transcribe(f);
              }}
              isDisabled={!ready}
            />
            <Switch label="Speak replies" value={speakReplies} onChange={setSpeakReplies} />
          </VStack>
        </HStack>

        <HStack gap={2} align="end">
          <TextInput
            label="Or type a command (skips Voxtral)"
            placeholder="fly to Tokyo and show the thermal view"
            value={text}
            onChange={(v: string) => setText(v)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && text.trim()) void parse(text.trim(), null, null);
            }}
            width="100%"
          />
          <Button
            label="Parse"
            width={96}
            variant="secondary"
            isDisabled={!text.trim()}
            onClick={() => void parse(text.trim(), null, null)}
          />
        </HStack>

        <VStack gap={6}>
          {runs.map((r, i) => (
            <VStack key={runs.length - i} gap={3} className="gw-stagger">
              <Heading level={3} textWrap="pretty">
                “{r.heard}”
              </Heading>
              <MetadataList columns="multi">
                <MetadataListItem label="Voxtral">
                  <Text hasTabularNumbers>
                    {r.transcribeMs == null ? 'typed' : `${Math.round(r.transcribeMs)} ms`}
                  </Text>
                </MetadataListItem>
                <MetadataListItem label="Audio">
                  <Text hasTabularNumbers>{r.audioKb == null ? '—' : `${r.audioKb} KB`}</Text>
                </MetadataListItem>
                <MetadataListItem label="Parser">
                  <Text hasTabularNumbers>
                    {r.result.source} · {Math.round(r.parseMs)} ms
                  </Text>
                </MetadataListItem>
              </MetadataList>
              <Text display="block">{r.result.reply}</Text>
              <CodeBlock code={JSON.stringify(r.result.commands, null, 2)} language="json" />
            </VStack>
          ))}
        </VStack>
      </VStack>
    </VStack>
  );
}
