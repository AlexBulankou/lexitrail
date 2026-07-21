// FEAT-1 (ITP #21): daily practice streaks + a daily goal. Pure logic here
// (unit-tested); localStorage persistence + the record/display glue live in
// services/streakStore.js so this stays deterministic and testable.
//
// State shape: { lastDay: 'YYYY-MM-DD'|null, streak: number, todayCount: number }

export const DEFAULT_GOAL = 10;

export function emptyState() {
  return { lastDay: null, streak: 0, todayCount: 0 };
}

// Whole-day difference b - a for 'YYYY-MM-DD' strings (UTC-safe: parsed at
// midnight UTC so DST never shifts the count). Returns null on unparseable.
export function daysBetween(a, b) {
  if (!a || !b) return null;
  const pa = Date.parse(`${a}T00:00:00Z`);
  const pb = Date.parse(`${b}T00:00:00Z`);
  if (Number.isNaN(pa) || Number.isNaN(pb)) return null;
  return Math.round((pb - pa) / 86400000);
}

// Fold one practice event (on day `today`) into the streak state.
//   same day    -> streak unchanged, todayCount + 1
//   next day    -> streak + 1, todayCount reset to 1
//   first / gap -> streak reset to 1, todayCount 1
export function advance(state, today) {
  const s = state || emptyState();
  if (!today) return s;
  const diff = daysBetween(s.lastDay, today);
  if (diff === 0) {
    return { lastDay: today, streak: s.streak || 1, todayCount: (s.todayCount || 0) + 1 };
  }
  if (diff === 1) {
    return { lastDay: today, streak: (s.streak || 0) + 1, todayCount: 1 };
  }
  // first practice ever (diff null), or a missed day (diff > 1 or negative)
  return { lastDay: today, streak: 1, todayCount: 1 };
}

// The streak is "current" only if the last practice was today or yesterday;
// otherwise it has lapsed and should read 0 for display.
export function currentStreak(state, today) {
  const s = state || emptyState();
  const diff = daysBetween(s.lastDay, today);
  if (diff === 0 || diff === 1) return s.streak || 0;
  return 0;
}

// Today's progress toward the goal (0 when the last practice wasn't today).
export function todayProgress(state, today) {
  const s = state || emptyState();
  return daysBetween(s.lastDay, today) === 0 ? (s.todayCount || 0) : 0;
}

export function goalMet(state, today, goal = DEFAULT_GOAL) {
  return todayProgress(state, today) >= goal;
}
