/**
 * Voice I/O for the assistant: record → Voxtral (or the browser's speech recognition as a
 * fallback) → text, plus spoken replies. Exposes a live 0–1 `level` for the orb: microphone
 * loudness while listening, a speech envelope while speaking.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api/client';

export type VoiceState = 'idle' | 'listening' | 'thinking' | 'speaking';

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

const MAX_RECORD_MS = 12000;

export function useVoice(
  handle: (text: string, onProgress?: (msg: string) => void) => Promise<string>,
) {
  const [state, setState] = useState<VoiceState>('idle');
  const [message, setMessage] = useState<string | null>(null);
  const [engine, setEngine] = useState<'voxtral' | 'browser' | null>(null);
  const level = useRef(0);
  const stopRef = useRef<(() => void) | null>(null);
  const handleRef = useRef(handle);
  handleRef.current = handle;

  useEffect(() => {
    const canRecord = 'MediaRecorder' in window && !!navigator.mediaDevices;
    api
      .assistantStatus()
      .then((s) =>
        setEngine(s.mistral && canRecord ? 'voxtral' : recognitionCtor() ? 'browser' : null),
      )
      .catch(() => setEngine(recognitionCtor() ? 'browser' : null));
  }, []);

  const speak = useCallback((text: string) => {
    if (!('speechSynthesis' in window) || !text) {
      setState('idle');
      return;
    }
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = 'en-GB';
    let raf = 0;
    const t0 = performance.now();
    // speechSynthesis exposes no amplitude: approximate a syllable envelope, bumped on word boundaries
    const tick = () => {
      const t = (performance.now() - t0) / 1000;
      level.current = Math.max(level.current * 0.9, 0.35 + 0.25 * Math.abs(Math.sin(t * 9)));
      raf = requestAnimationFrame(tick);
    };
    u.onstart = () => {
      setState('speaking');
      raf = requestAnimationFrame(tick);
    };
    u.onboundary = () => {
      level.current = 0.9;
    };
    u.onend = u.onerror = () => {
      cancelAnimationFrame(raf);
      level.current = 0;
      setState('idle');
    };
    window.speechSynthesis.speak(u);
  }, []);

  const process = useCallback(
    async (text: string) => {
      if (!text.trim()) {
        setMessage('I didn’t hear anything.');
        setState('idle');
        return;
      }
      setState('thinking');
      try {
        const reply = await handleRef.current(text, (m) => setMessage(m));
        setMessage(reply);
        speak(reply);
      } catch (e) {
        setMessage(e instanceof Error ? e.message : 'Something went wrong.');
        setState('idle');
      }
    },
    [speak],
  );

  const startVoxtral = useCallback(async () => {
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setMessage('Microphone access was blocked.');
      return;
    }
    const ctx = new AudioContext();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const buf = new Uint8Array(analyser.fftSize);
    let raf = 0;
    const meter = () => {
      analyser.getByteTimeDomainData(buf);
      let sum = 0;
      for (const v of buf) sum += ((v - 128) / 128) ** 2;
      const rms = Math.sqrt(sum / buf.length);
      level.current = Math.min(1, level.current * 0.6 + rms * 5 * 0.4);
      raf = requestAnimationFrame(meter);
    };
    raf = requestAnimationFrame(meter);

    const rec = new MediaRecorder(stream);
    const chunks: Blob[] = [];
    rec.ondataavailable = (e) => {
      if (e.data.size) chunks.push(e.data);
    };
    const limit = window.setTimeout(() => rec.state === 'recording' && rec.stop(), MAX_RECORD_MS);
    rec.onstop = async () => {
      window.clearTimeout(limit);
      cancelAnimationFrame(raf);
      stream.getTracks().forEach((t) => t.stop());
      void ctx.close();
      level.current = 0;
      stopRef.current = null;
      setState('thinking');
      try {
        const { text } = await api.transcribe(
          new Blob(chunks, { type: rec.mimeType || 'audio/webm' }),
        );
        await process(text);
      } catch (e) {
        setMessage(e instanceof Error ? e.message : 'Transcription failed.');
        setState('idle');
      }
    };
    stopRef.current = () => rec.state === 'recording' && rec.stop();
    rec.start();
    setState('listening');
  }, [process]);

  const startBrowser = useCallback(() => {
    const Ctor = recognitionCtor();
    if (!Ctor) return;
    const rec = new Ctor();
    rec.lang = 'en-GB';
    rec.interimResults = true;
    rec.continuous = false;
    let finalText = '';
    rec.onresult = (e) => {
      const parts = Array.from(e.results);
      finalText = parts.map((r) => r[0]?.transcript ?? '').join(' ');
      level.current = 0.6; // no mic level from this API: show activity on each result
      setMessage(finalText);
    };
    rec.onend = () => {
      stopRef.current = null;
      level.current = 0;
      void process(finalText);
    };
    rec.onerror = () => {
      stopRef.current = null;
      setState('idle');
    };
    stopRef.current = () => rec.stop();
    rec.start();
    setState('listening');
  }, [process]);

  const start = useCallback(() => {
    if (state === 'speaking') window.speechSynthesis.cancel();
    if (state === 'listening' || state === 'thinking') return;
    setMessage(null);
    if (engine === 'voxtral') void startVoxtral();
    else if (engine === 'browser') startBrowser();
    else
      setMessage('Voice needs a microphone and either a Mistral key on the server or Chrome/Edge.');
  }, [engine, state, startVoxtral, startBrowser]);

  const stop = useCallback(() => stopRef.current?.(), []);

  return { state, level, message, engine, start, stop, speak, setMessage };
}
