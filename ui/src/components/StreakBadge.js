import React, { useState, useEffect } from 'react';
import { getSnapshot, STREAK_EVENT } from '../services/streakStore';
import '../styles/StreakBadge.css';

// FEAT-1 (ITP #21): compact streak + daily-goal indicator for the nav bar.
// Reads the streak snapshot and refreshes when a practice event fires.
const StreakBadge = () => {
  const [snap, setSnap] = useState(() => getSnapshot());

  useEffect(() => {
    const refresh = () => setSnap(getSnapshot());
    window.addEventListener(STREAK_EVENT, refresh);
    // Also refresh on focus (a new calendar day may have started).
    window.addEventListener('focus', refresh);
    return () => {
      window.removeEventListener(STREAK_EVENT, refresh);
      window.removeEventListener('focus', refresh);
    };
  }, []);

  // Nothing to celebrate yet — don't clutter the bar with a 0-day streak.
  if (snap.streak === 0 && snap.today === 0) return null;

  const label = `${snap.streak}-day streak, ${snap.today} of ${snap.goal} words today`;

  return (
    <div
      className={`streak-badge ${snap.met ? 'goal-met' : ''}`}
      role="status"
      aria-label={label}
      title={label}
    >
      <span className="streak-flame" aria-hidden="true">🔥</span>
      <span className="streak-count">{snap.streak}</span>
      <span className="streak-goal" aria-hidden="true">
        {snap.met ? '✓' : `${snap.today}/${snap.goal}`}
      </span>
    </div>
  );
};

export default StreakBadge;
