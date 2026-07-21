// FEAT-1 (ITP #21): localStorage persistence + record/read glue for the daily
// streak. Pure streak math lives in utils/streak.js; this layer holds the
// browser-specific bits (today's date, storage, a change event for the badge).
import {
  emptyState,
  advance,
  currentStreak,
  todayProgress,
  goalMet,
  DEFAULT_GOAL,
} from '../utils/streak';

const STORAGE_KEY = 'lexitrail.streak.v1';
export const STREAK_EVENT = 'lexitrail:streak-updated';
export const GOAL = DEFAULT_GOAL;

// Local-calendar YYYY-MM-DD (streaks follow the learner's local day).
export function todayISO(d = new Date()) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export function getState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return emptyState();
    const parsed = JSON.parse(raw);
    return { ...emptyState(), ...parsed };
  } catch (e) {
    return emptyState();
  }
}

function saveState(state) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch (e) {
    /* storage full / disabled — streak is best-effort, never blocks practice */
  }
}

// Record one practice event for today. Best-effort + never throws, so a wiring
// call in the review handlers can't break answering a card.
export function recordPractice(today = todayISO()) {
  try {
    const next = advance(getState(), today);
    saveState(next);
    if (typeof window !== 'undefined' && window.dispatchEvent) {
      window.dispatchEvent(new CustomEvent(STREAK_EVENT, { detail: next }));
    }
    return next;
  } catch (e) {
    return getState();
  }
}

// Display snapshot for the badge.
export function getSnapshot(today = todayISO()) {
  const s = getState();
  return {
    streak: currentStreak(s, today),
    today: todayProgress(s, today),
    goal: GOAL,
    met: goalMet(s, today, GOAL),
  };
}
