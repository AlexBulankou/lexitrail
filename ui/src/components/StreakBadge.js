import React from 'react';
import { useStreakSnapshot } from '../hooks/useStreakSnapshot';
import '../styles/StreakBadge.css';

// FEAT-1 (ITP #21): compact streak + daily-goal indicator for the nav bar.
// Reads the streak snapshot and refreshes when a practice event fires.
const StreakBadge = () => {
  // issue-107: this subscribe/refresh glue moved to `useStreakSnapshot` when
  // the Today home became its second consumer. Behaviour is unchanged — the
  // hook is this code, verbatim, including the focus listener for an overnight
  // day rollover. Sharing it is what stops the badge and the headline
  // underneath it from disagreeing about the streak on the same page.
  const snap = useStreakSnapshot();

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
