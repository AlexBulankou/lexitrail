import { useState, useEffect } from 'react';
import { getSnapshot, STREAK_EVENT } from '../services/streakStore';

// The live streak snapshot, refreshed the way StreakBadge already did it.
//
// issue-107: extracted rather than copied. The Today home is the SECOND
// consumer of this glue, and two copies of "when does the streak re-read"
// is how the nav badge and the home screen end up showing different numbers
// on the same page — the badge refreshing on a practice event while the
// headline underneath it keeps yesterday's streak.
//
// Both listeners are load-bearing and neither is redundant:
//   STREAK_EVENT — a practice answer advanced the streak in this tab.
//   focus        — the calendar day may have rolled over while the tab sat
//                  open overnight, which fires no event at all. A habit
//                  screen left open is exactly the case that hits this.
export const useStreakSnapshot = () => {
  const [snap, setSnap] = useState(() => getSnapshot());

  useEffect(() => {
    const refresh = () => setSnap(getSnapshot());
    window.addEventListener(STREAK_EVENT, refresh);
    window.addEventListener('focus', refresh);
    return () => {
      window.removeEventListener(STREAK_EVENT, refresh);
      window.removeEventListener('focus', refresh);
    };
  }, []);

  return snap;
};

export default useStreakSnapshot;
