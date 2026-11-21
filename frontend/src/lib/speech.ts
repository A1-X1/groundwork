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

export const VOICES = [
  { id: 'en_paul', label: 'Paul', description: 'American, warm; cheerful, happy, confident tones' },
  {
    id: 'gb_oliver',
    label: 'Oliver',
    description: 'British, expressive; curious and cheerful tones',
  },
  { id: 'gb_jane', label: 'Jane', description: 'British, clear; confident and curious tones' },
  {
    id: 'browser',
    label: 'Browser voice',
    description: 'Your system voice; works offline, no key',
  },
] as const;
export type VoiceId = (typeof VOICES)[number]['id'];
const VOICE_KEY = 'groundwork.voice';

export function getVoice(): VoiceId {
  try {
    const v = window.localStorage.getItem(VOICE_KEY);
    if (VOICES.some((x) => x.id === v)) return v as VoiceId;
  } catch {
    // storage unavailable
  }
  return 'en_paul';
}

export function setVoice(v: VoiceId) {
  try {
    window.localStorage.setItem(VOICE_KEY, v);
  } catch {
    // storage unavailable: this session only
  }
}

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
  const speaker = getVoice();
  if (!useVoxtral || speaker === 'browser') return browserSpeak(text, h);
  try {
    const { audio, voice } = await api.speak(text, speaker);
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
