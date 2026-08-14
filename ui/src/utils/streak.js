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


// Which modes credit the daily streak (lexitrail#112).
//
// Measured on live code: the recall handlers are gated on exactly one mode
// (`WordCard.js`: `mode === GameMode.TEST ? undefined : handleCardClick`) and
// neither `handleMemorized` nor `handleNotMemorized` checks the mode at all.
// So reviewing a card in SHOW_EXCLUDED credited the streak — for words the
// learner had explicitly removed from their practice set.
//
// The streak is a claim about a HABIT, and the habit is the practice set. A
// number that counts words you opted out of overstates it, and the overstated
// number is the one shown next to a goal the learner is trying to meet.
//
// 🔴 A WHITELIST, and TEST IS DELIBERATELY IN IT. TEST credits the streak
// today; keeping it is *unchanged behaviour*, not an oversight, and it belongs
// in the list explicitly so nobody later reads its presence as an accident and
// "tidies" it out. What the whitelist buys is the other direction: a mode added
// later has to opt IN, because a new browse-shaped view silently inflating the
// streak is the failure that cannot be seen from here.
//
// 🔴 What this does NOT decide, and deliberately: whether SHOW_EXCLUDED should
// still move `recall_state` or append recall history. Both are backend writes
// through one call, and splitting them needs a backend change that cannot ship
// (lexitrail#77 — no Cloud Build trigger, no backend image since 2026-07-22).
// #112 stays open for that half rather than being closed by this one.
export const STREAK_CREDIT_MODES = ['PRACTICE', 'DUE_TODAY', 'TEST'];

export const creditsStreak = (mode) => STREAK_CREDIT_MODES.includes(mode);
