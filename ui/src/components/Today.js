import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useDueToday } from '../hooks/useDueToday';
import { useStreakSnapshot } from '../hooks/useStreakSnapshot';
import { pickStartSet } from '../utils/srs';
import '../styles/Today.css';

// issue-107 (RD-3, sub-issue 1 of 3 of #50) — the Today home.
//
// The habit anchor: today's due count, the streak, and ONE Start. Replaces the
// wordset list as the signed-in landing surface, per the decision page
// (`docs/mocks/lt-redesign-decisions.html`): "opening the app has an obvious
// next action instead of a wordset list."
//
// The wordset list is NOT deleted — it is one nav click away, and RD-2 (#108)
// is the issue that reshapes the list itself. This screen only changes what
// you land on.
const Today = ({ userId }) => {
  const navigate = useNavigate();
  const { status, total, sets, reload } = useDueToday(userId);
  const streak = useStreakSnapshot();

  const startSet = pickStartSet(sets);

  const start = () => {
    if (!startSet) return;
    // Mirrors Wordsets.handleWordsetClick's analytics so the two entry points
    // into a due session are comparable — the whole question RD-3 has to
    // answer later is whether landing on Today starts more sessions than
    // landing on the list did, and that is unanswerable if only one is
    // instrumented. Guarded because `gtag` is absent under test and in any
    // build without the analytics snippet; Wordsets calls it bare.
    if (typeof window.gtag === 'function') {
      window.gtag('event', 'wordset_click', {
        event_category: 'game_start',
        event_label: 'due_today',
        wordset_id: startSet.wordsetId,
        start_surface: 'today_home',
      });
    }
    navigate(`/game/${startSet.wordsetId}/DUE_TODAY`);
  };

  if (status === 'loading') {
    return (
      <div className="today" role="status" aria-live="polite">
        <p className="today-status">Checking today's reviews…</p>
      </div>
    );
  }

  // An explicit error, never a silent zero. `useDueToday` rejects rather than
  // resolving to 0 for exactly this reason: "0 due" and "we could not ask" look
  // identical to a learner, and one of them wrongly says you are finished.
  if (status === 'error') {
    return (
      <div className="today">
        <p className="today-status today-error" role="alert">
          Couldn't load today's reviews.
        </p>
        <button type="button" className="today-start" onClick={reload}>
          Try again
        </button>
        <Link to="/wordsets" className="today-secondary">
          Or pick a word set
        </Link>
      </div>
    );
  }

  const streakLine =
    streak.streak > 0
      ? `${streak.streak}-day streak · ${streak.today}/${streak.goal} words today`
      : `${streak.today}/${streak.goal} words today`;

  if (total === 0) {
    return (
      <div className="today">
        <p className="today-headline today-done">All caught up</p>
        <p className="today-sub">Nothing is due right now. Come back tomorrow.</p>
        <p className="today-streak" role="status">{streakLine}</p>
        <Link to="/wordsets" className="today-secondary">
          Practice anyway
        </Link>
      </div>
    );
  }

  return (
    <div className="today">
      <p className="today-headline">
        <span className="today-count">{total}</span>{' '}
        {total === 1 ? 'review due today' : 'reviews due today'}
      </p>
      <p className="today-streak" role="status">{streakLine}</p>
      <button type="button" className="today-start" onClick={start}>
        Start
      </button>
      {/* Naming the set the button opens, because it opens ONE. With reviews
          waiting in several sets, a bare "Start" would silently pick for you
          and the count above (all sets) would not match the session (one set).
          Saying which one is the honest version of a single Start action. */}
      {startSet && (
        <p className="today-target">
          {startSet.due} of them in {startSet.description || 'this set'}
        </p>
      )}
      <Link to="/wordsets" className="today-secondary">
        Choose a different set
      </Link>
    </div>
  );
};

export default Today;
