import React from 'react';
import '../styles/OnboardingOverlay.css';

const OnboardingOverlay = ({ mode, onDismiss }) => {
  const isTest = mode === 'TEST';

  return (
    <div className="onboarding-overlay" role="dialog" aria-modal="true" aria-label="How to play">
      <div className="onboarding-card">
        <h2 className="onboarding-title">How it works</h2>
        <ul className="onboarding-list">
          <li><span className="onboarding-icon" aria-hidden="true">🔄</span> Tap a card to flip it and see the meaning.</li>
          {isTest ? (
            <li><span className="onboarding-icon" aria-hidden="true">🔤</span> Pick the answer that matches the word.</li>
          ) : (
            <>
              <li><span className="onboarding-icon" aria-hidden="true">✔️</span> Mark a word <strong>correct</strong> when you remember it.</li>
              <li><span className="onboarding-icon" aria-hidden="true">❌</span> Mark it <strong>missed</strong> to keep practicing it.</li>
              <li><span className="onboarding-icon" aria-hidden="true">🚫</span> <strong>Exclude</strong> hides words you already know well.</li>
            </>
          )}
          <li><span className="onboarding-icon" aria-hidden="true">💡</span> <strong>Show / Hide Hints</strong> toggles picture hints.</li>
        </ul>
        <button className="onboarding-button" onClick={onDismiss} autoFocus>Got it</button>
      </div>
    </div>
  );
};

export default OnboardingOverlay;
