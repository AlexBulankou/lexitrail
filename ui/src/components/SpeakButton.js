import React from 'react';
import { isSpeechSupported, speakChinese } from '../utils/speak';
import '../styles/SpeakButton.css';

// FEAT-3 (ITP #21): a small "play pronunciation" control shown next to a
// Chinese word. Uses the browser-native Web Speech API (zero-cost). Renders
// nothing on browsers without speech synthesis, so it never shows a dead button.
const SpeakButton = ({ text, size = 'md' }) => {
  if (!isSpeechSupported() || !(text || '').trim()) return null;

  const handleClick = (e) => {
    // Cards flip on click; don't let the pronunciation control flip the card.
    e.stopPropagation();
    speakChinese(text);
  };

  return (
    <button
      type="button"
      className={`speak-button speak-button-${size}`}
      onClick={handleClick}
      aria-label={`Play pronunciation of ${text}`}
      title="Play pronunciation"
    >
      <span aria-hidden="true">🔊</span>
    </button>
  );
};

export default SpeakButton;
