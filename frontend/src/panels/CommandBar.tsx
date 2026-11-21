import { HStack } from '@astryxdesign/core/HStack';
import { Icon } from '@astryxdesign/core/Icon';
import { IconButton } from '@astryxdesign/core/IconButton';
import { Text } from '@astryxdesign/core/Text';
import { TextInput } from '@astryxdesign/core/TextInput';
import { VStack } from '@astryxdesign/core/VStack';
import { Mic, MicOff, SendHorizontal } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { api } from '../api/client';

// Minimal Web Speech API typing (Chrome/Edge/Safari expose it with a webkit prefix).
interface SpeechResultEvent {
  results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }>;
}
interface Recognition {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((e: SpeechResultEvent) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  start: () => void;
  stop: () => void;
}
type RecognitionCtor = new () => Recognition;

function recognitionCtor(): RecognitionCtor | null {
  const w = window as unknown as Record<string, unknown>;
  return (w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null) as RecognitionCtor | null;
}

interface Props {
  onSubmit: (text: string, spoken: boolean) => Promise<string>;
}

export function speak(text: string) {
  if (!('speechSynthesis' in window)) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = 'en-GB';
  window.speechSynthesis.speak(u);
}

export function CommandBar({ onSubmit }: Props) {
  const [text, setText] = useState('');
  const [reply, setReply] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const recRef = useRef<Recognition | null>(null);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const [voxtral, setVoxtral] = useState<string | null>(null);
  const Ctor = recognitionCtor();
  const canRecord =
    typeof window !== 'undefined' && 'MediaRecorder' in window && !!navigator.mediaDevices;

  useEffect(() => {
    api
      .assistantStatus()
      .then((s) => setVoxtral(s.mistral ? (s.voxtral_model ?? 'Voxtral') : null))
      .catch(() => setVoxtral(null));
  }, []);

  /** Voxtral path: record a short clip, send it to the API, act on the transcript. */
  const toggleRecording = async () => {
    if (listening) {
      mediaRef.current?.stop();
      return;
    }
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setReply('Microphone access was blocked.');
      return;
    }
    const rec = new MediaRecorder(stream);
    const chunks: Blob[] = [];
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    rec.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      setListening(false);
      window.clearTimeout(limit);
      const blob = new Blob(chunks, { type: rec.mimeType || 'audio/webm' });
      setBusy(true);
      try {
        const { text: heard } = await api.transcribe(blob);
        setText(heard);
        setBusy(false);
        if (heard) await submit(heard, true);
        else setReply('I didn’t hear anything.');
      } catch (e) {
        setBusy(false);
        setReply(e instanceof Error ? e.message : 'Transcription failed.');
      }
    };
    mediaRef.current = rec;
    rec.start();
    setListening(true);
    // voice commands are short: stop after 12 s
    const limit = window.setTimeout(() => rec.state === 'recording' && rec.stop(), 12000);
  };

  const submit = async (value: string, spoken: boolean) => {
    const q = value.trim();
    if (!q || busy) return;
    setBusy(true);
    try {
      const r = await onSubmit(q, spoken);
      setReply(r);
      setText('');
      if (spoken) speak(r);
    } catch (e) {
      setReply(e instanceof Error ? e.message : 'Something went wrong.');
    } finally {
      setBusy(false);
    }
  };

  const toggleMic = () => {
    if (!Ctor) return;
    if (listening) {
      recRef.current?.stop();
      return;
    }
    const rec = new Ctor();
    rec.lang = 'en-GB';
    rec.interimResults = true;
    rec.continuous = false;
    let finalText = '';
    rec.onresult = (e) => {
      const parts = Array.from(e.results);
      const t = parts.map((r) => r[0]?.transcript ?? '').join(' ');
      setText(t);
      if (parts.every((r) => r.isFinal)) finalText = t;
    };
    rec.onend = () => {
      setListening(false);
      if (finalText) void submit(finalText, true);
    };
    rec.onerror = () => setListening(false);
    recRef.current = rec;
    setListening(true);
    rec.start();
  };

  useEffect(() => () => recRef.current?.stop(), []);

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
            if (e.key === 'Enter') void submit(text, false);
          }}
          width="100%"
        />
        {((voxtral && canRecord) || Ctor) && (
          <IconButton
            label={listening ? 'Stop listening' : 'Speak a command'}
            tooltip={voxtral ? `Voice by Mistral ${voxtral}` : 'Voice by your browser'}
            icon={<Icon icon={listening ? MicOff : Mic} size="sm" />}
            variant={listening ? 'primary' : 'secondary'}
            onClick={() => (voxtral && canRecord ? void toggleRecording() : toggleMic())}
          />
        )}
        <IconButton
          label="Send command"
          icon={<Icon icon={SendHorizontal} size="sm" />}
          variant="secondary"
          isLoading={busy}
          onClick={() => void submit(text, false)}
        />
      </HStack>
      <Text type="supporting" color="secondary" display="block" role="status" maxLines={2}>
        {listening ? 'Listening… click the mic again to stop.' : (reply ?? '')}
      </Text>
    </VStack>
  );
}
