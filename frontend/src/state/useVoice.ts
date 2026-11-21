/**
 * Voice I/O for the assistant: record → Voxtral (or the browser's speech recognition as a
 * fallback) → text, plus spoken replies. Exposes a live 0–1 `level` for the orb: microphone
 * loudness while listening, a speech envelope while speaking.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import { speakReply, stopSpeaking } from '../lib/speech';

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
  const [muted, setMuted] = useState(false);
  const mutedRef = useRef(false);
  mutedRef.current = muted;
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

  const handsFreeOnRef = useRef(false);
  const engineRef = useRef(engine);
  engineRef.current = engine;
  const speak = useCallback((text: string) => {
    if (!text || mutedRef.current) {
      setState('idle');
      return;
    }
    void speakReply(
      text,
      {
        onStart: () => setState('speaking'),
        onLevel: (l) => {
          level.current = l;
        },
        onEnd: () => {
          level.current = 0;
          setState(handsFreeOnRef.current ? 'listening' : 'idle');
        },
      },
      engineRef.current === 'voxtral',
    );
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

  /** One-shot recording that waits for stop (kept for the Voice Lab-style flows). */
  const startOnce = useCallback(() => {
    if (state === 'speaking') stopSpeaking();
    if (state === 'listening' || state === 'thinking') return;
    setMessage(null);
    if (engine === 'voxtral') void startVoxtral();
    else if (engine === 'browser') startBrowser();
    else
      setMessage('Voice needs a microphone and either a Mistral key on the server or Chrome/Edge.');
  }, [engine, state, startVoxtral, startBrowser]);
  void startOnce;

  // ---- hands-free: always-on listening with voice-activity detection ----------------------
  const [handsFree, setHandsFree] = useState(false);
  handsFreeOnRef.current = handsFree;
  // stop: mic off, drop anything half-heard. submit: mic off, but send what was heard so far.
  const handsFreeRef = useRef<{ stop: () => void; submit: () => void } | null>(null);
  const stateRef = useRef(state);
  stateRef.current = state;

  /** Voxtral path: mic stays open; record from speech onset until ~800 ms of silence. */
  const startHandsFreeVoxtral = useCallback(async () => {
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
    } catch {
      setMessage('Microphone access was blocked.');
      setHandsFree(false);
      return;
    }
    const ctx = new AudioContext();
    const an = ctx.createAnalyser();
    an.fftSize = 1024;
    ctx.createMediaStreamSource(stream).connect(an);
    const buf = new Uint8Array(an.fftSize);
    // Thresholds follow the room: a running noise floor (quiet mics with noise suppression
    // sit far below fixed thresholds, so speech was never detected or never ended).
    let floor = 0.004;
    const startAt = () => Math.max(0.012, floor * 3.2); // RMS that counts as speech
    const stopAt = () => Math.max(0.007, floor * 1.8); // RMS below this counts as silence
    const SILENCE_MS = 800; // pause that ends an utterance and sends it
    const MIN_SPEECH_MS = 400; // shorter blips (a cough, a click) are ignored
    let rec: MediaRecorder | null = null;
    let chunks: Blob[] = [];
    let speechAt = 0;
    let speechMs = 0;
    let lastFrame = 0;
    let quietSince = 0;
    let raf = 0;
    let alive = true;

    const finishUtterance = () => {
      const r = rec;
      rec = null;
      if (!r) return;
      const long = speechMs >= MIN_SPEECH_MS;
      r.onstop = () => {
        if (!long || !alive) return;
        const blob = new Blob(chunks, { type: r.mimeType || 'audio/webm' });
        setState('thinking');
        api
          .transcribe(blob)
          .then(({ text }) => (text.trim() ? process(text) : setState('listening')))
          .catch((e: unknown) => {
            setMessage(e instanceof Error ? e.message : 'Transcription failed.');
            setState('listening');
          });
      };
      r.stop();
    };

    const loop = () => {
      if (!alive) return;
      an.getByteTimeDomainData(buf);
      let sum = 0;
      for (const v of buf) sum += ((v - 128) / 128) ** 2;
      const rms = Math.sqrt(sum / buf.length);
      const now = performance.now();
      const dt = lastFrame ? now - lastFrame : 0;
      lastFrame = now;
      // Learn the noise floor only between utterances (slowly up, quickly down).
      if (!rec) floor = rms < floor ? floor * 0.9 + rms * 0.1 : floor * 0.995 + rms * 0.005;
      // Only listen while idle-listening: never while thinking or speaking (no self-hearing).
      const ready = stateRef.current === 'listening' || stateRef.current === 'idle';
      if (ready && stateRef.current === 'idle') setState('listening');
      if (ready) {
        level.current = Math.min(1, level.current * 0.6 + rms * 5 * 0.4);
        if (!rec && rms > startAt()) {
          chunks = [];
          rec = new MediaRecorder(stream);
          rec.ondataavailable = (e) => {
            if (e.data.size) chunks.push(e.data);
          };
          rec.start();
          speechAt = now;
          speechMs = 0;
          quietSince = 0;
        } else if (rec) {
          if (rms >= stopAt()) speechMs += dt;
          if (rms < stopAt()) {
            quietSince ||= now;
            if (now - quietSince > SILENCE_MS) finishUtterance();
          } else quietSince = 0;
          if (now - speechAt > 15000) finishUtterance(); // cap one utterance at 15 s
        }
      }
      raf = requestAnimationFrame(loop);
    };
    setState('listening');
    raf = requestAnimationFrame(loop);
    const teardown = () => {
      alive = false;
      cancelAnimationFrame(raf);
      stream.getTracks().forEach((t) => t.stop());
      void ctx.close();
      level.current = 0;
    };
    handsFreeRef.current = {
      stop: () => {
        teardown();
        if (rec && rec.state === 'recording') rec.stop();
      },
      submit: () => {
        // Stop listening now and send the current utterance without waiting for a pause.
        const r = rec;
        rec = null;
        if (!r || r.state !== 'recording') {
          teardown();
          setMessage('I didn’t hear anything.');
          setState('idle');
          return;
        }
        r.onstop = () => {
          teardown();
          const blob = new Blob(chunks, { type: r.mimeType || 'audio/webm' });
          setState('thinking');
          api
            .transcribe(blob)
            .then(({ text }) => process(text))
            .catch((e: unknown) => {
              setMessage(e instanceof Error ? e.message : 'Transcription failed.');
              setState('idle');
            });
        };
        r.stop();
      },
    };
  }, [process]);

  /** Browser path: continuous recognition, paused while thinking/speaking. */
  const startHandsFreeBrowser = useCallback(() => {
    const Ctor = recognitionCtor();
    if (!Ctor) return;
    let alive = true;
    let rec: Recognition | null = null;
    let submitting = false;
    const listen = () => {
      if (!alive) return;
      if (stateRef.current === 'thinking' || stateRef.current === 'speaking') {
        window.setTimeout(listen, 300);
        return;
      }
      rec = new Ctor();
      rec.lang = 'en-GB';
      rec.continuous = true;
      rec.interimResults = false;
      rec.onresult = (e) => {
        const last = e.results[e.results.length - 1];
        const text = last?.[0]?.transcript ?? '';
        if (last?.isFinal && text.trim()) {
          submitting = false;
          rec?.stop();
          void process(text);
        }
      };
      rec.onend = () => {
        if (submitting) {
          // Submitted but the recogniser had nothing final to give.
          submitting = false;
          setMessage('I didn’t hear anything.');
          setState('idle');
          return;
        }
        window.setTimeout(listen, 250);
      };
      rec.onerror = () => undefined;
      setState('listening');
      rec.start();
    };
    listen();
    handsFreeRef.current = {
      stop: () => {
        alive = false;
        rec?.stop();
      },
      submit: () => {
        // Stopping the recogniser flushes what it heard as a final result, which onresult sends.
        alive = false;
        submitting = true;
        rec?.stop();
      },
    };
  }, [process]);

  const toggleHandsFree = useCallback(() => {
    if (handsFreeRef.current) {
      handsFreeRef.current.stop();
      handsFreeRef.current = null;
      setHandsFree(false);
      if (stateRef.current === 'listening') setState('idle');
      return;
    }
    if (!engine) {
      setMessage('Voice needs a microphone and either a Mistral key on the server or Chrome/Edge.');
      return;
    }
    setHandsFree(true);
    setMessage(null);
    if (engine === 'voxtral') void startHandsFreeVoxtral();
    else startHandsFreeBrowser();
  }, [engine, startHandsFreeVoxtral, startHandsFreeBrowser]);

  useEffect(() => () => handsFreeRef.current?.stop(), []);

  /** Optional: stop taking voice input now and process what has been heard so far. */
  const submit = useCallback(() => {
    const h = handsFreeRef.current;
    if (!h) return;
    handsFreeRef.current = null;
    handsFreeOnRef.current = false; // the reply ends in idle, not back to listening
    setHandsFree(false);
    h.submit();
  }, []);

  // The mic toggle is the main control: start = mic on (each utterance sends itself when you
  // pause), stop = mic off. The optional Send button (submit) ends input early and sends it.
  const start = useCallback(() => {
    if (stateRef.current === 'speaking') stopSpeaking();
    if (!handsFreeRef.current) toggleHandsFree();
  }, [toggleHandsFree]);
  const stop = useCallback(() => {
    if (handsFreeRef.current) toggleHandsFree();
    else stopRef.current?.();
  }, [toggleHandsFree]);

  const toggleMute = useCallback(() => {
    setMuted((m) => {
      if (!m) stopSpeaking();
      return !m;
    });
  }, []);

  return {
    state,
    level,
    message,
    engine,
    start,
    stop,
    speak,
    setMessage,
    muted,
    toggleMute,
    handsFree,
    toggleHandsFree,
    submit,
  };
}
