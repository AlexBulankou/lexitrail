// FEAT-3 (ITP #21): audio pronunciation via the browser-native Web Speech API.
// Zero-cost v1 — no paid TTS. speechSynthesis + a zh-CN utterance; the browser
// supplies the Mandarin voice. Feature-detected so unsupported browsers simply
// don't render the control (see SpeakButton).

// Learner-friendly default: a touch slower than natural so tones are audible.
export const DEFAULT_RATE = 0.85;
const ZH_LANG = 'zh-CN';

// True when the current browser exposes the Web Speech synthesis API.
export function isSpeechSupported() {
  return typeof window !== 'undefined'
    && typeof window.speechSynthesis !== 'undefined'
    && typeof window.SpeechSynthesisUtterance !== 'undefined';
}

// Pick a Mandarin voice when the browser lists one (voices load async, so an
// empty list early on is fine — the utterance's lang still routes correctly).
function pickChineseVoice() {
  try {
    const voices = window.speechSynthesis.getVoices() || [];
    return voices.find((v) => (v.lang || '').toLowerCase().startsWith('zh')) || null;
  } catch (e) {
    return null;
  }
}

// Speak `text` in Mandarin. Cancels any in-flight utterance first so rapid
// clicks (or moving between cards) don't queue overlapping audio. Returns true
// when speech was dispatched, false when unsupported or given empty text.
export function speakChinese(text, { rate = DEFAULT_RATE } = {}) {
  if (!isSpeechSupported()) return false;
  const value = (text || '').trim();
  if (!value) return false;

  const synth = window.speechSynthesis;
  synth.cancel();

  const utterance = new window.SpeechSynthesisUtterance(value);
  utterance.lang = ZH_LANG;
  utterance.rate = rate;
  const voice = pickChineseVoice();
  if (voice) utterance.voice = voice;

  synth.speak(utterance);
  return true;
}
