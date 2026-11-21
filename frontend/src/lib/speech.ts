/**
 * Spoken replies: Voxtral TTS from the API (natural voice, tone picked per reply), played through
 * an analyser so the orb follows the real loudness. Falls back to the browser's voices.
 */
import { api } from '../api/client';

export interface SpeakHandlers {
  onStart?: (voice: string) => void;
  onLevel?: (level: number) => void;
  onEnd?: () => void;
}

let current: { stop: () => void } | null = null;

export function stopSpeaking() {
  current?.stop();
  current = null;
  if ('speechSynthesis' in window) window.speechSynthesis.cancel();
}

function browserSpeak(text: string, h: SpeakHandlers) {
  if (!('speechSynthesis' in window)) return h.onEnd?.();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = 'en-GB';
  u.onstart = () => h.onStart?.('browser');
  u.onboundary = () => h.onLevel?.(0.9);
  u.onend = u.onerror = () => h.onEnd?.();
  window.speechSynthesis.speak(u);
}

/** Speak `text`. Resolves once playback has started (or failed over). */
export async function speakReply(text: string, h: SpeakHandlers, useVoxtral: boolean) {
  stopSpeaking();
  if (!text.trim()) return h.onEnd?.();
  if (!useVoxtral) return browserSpeak(text, h);
  try {
    const { audio, voice } = await api.speak(text);
    const url = URL.createObjectURL(audio);
    const el = new Audio(url);
    const ctx = new AudioContext();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    ctx.createMediaElementSource(el).connect(analyser);
    analyser.connect(ctx.destination);
    const buf = new Uint8Array(analyser.fftSize);
    let raf = 0;
    const meter = () => {
      analyser.getByteTimeDomainData(buf);
      let sum = 0;
      for (const v of buf) sum += ((v - 128) / 128) ** 2;
      h.onLevel?.(Math.min(1, Math.sqrt(sum / buf.length) * 4));
      raf = requestAnimationFrame(meter);
    };
    const finish = () => {
      cancelAnimationFrame(raf);
      URL.revokeObjectURL(url);
      void ctx.close();
      if (current?.stop === stop) current = null;
      h.onEnd?.();
    };
    const stop = () => {
      el.pause();
      finish();
    };
    el.onplay = () => {
      h.onStart?.(voice);
      raf = requestAnimationFrame(meter);
    };
    el.onended = finish;
    el.onerror = finish;
    current = { stop };
    await el.play();
  } catch {
    browserSpeak(text, h); // no key, network, or autoplay blocked
  }
}
