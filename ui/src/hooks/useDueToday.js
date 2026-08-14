import { useState, useEffect, useCallback } from 'react';
import { getWordsets } from '../services/wordsService';
import { getUserWordsByWordset } from '../services/userService';
import { dueByWordset, totalDue } from '../utils/srs';

// issue-107: the cross-wordset "due today" number the Today home is built on.
//
// The practice loop's `useWordsetLoader` answers this for ONE wordset, because
// a session has a wordsetId. A Today home is cross-wordset by definition, so it
// needs the same question asked across every set the learner can see.
//
// Client-side fan-out on purpose (#107 recommendation (a)): `getWordsets()`
// already hides the test/HSK7 sets so N is small, and a backend endpoint would
// make this issue undeployable for reasons unrelated to its merits — lexitrail
// has no Cloud Build trigger, so backend deploys are the blocked half (#77)
// while the UI ships today.
//
// Note this reads ONLY the userwords rows, not the word rows: `is_included`,
// `recall_state` and `recall_history` all live on the userword, so the due
// count needs no `getWordsByWordset` call. That halves the fan-out.
// The fetch + aggregate, as a plain async function.
//
// Separated from the hook deliberately: this repo has no React testing library
// (all ten existing suites are pure logic), and the part worth pinning is the
// aggregation and the failure mode, not React's state plumbing. Adding
// `@testing-library/react` to test a five-line `useEffect` would buy a
// dependency I cannot exercise in CI — lexitrail has no Cloud Build trigger
// (#77) — in exchange for coverage of the least interesting half.
//
// Same shape as `dueAcrossWordsets` taking already-fetched lists: keep the
// logic pure and let the thin wrapper be obviously correct by inspection.
export const loadDueToday = async (userId) => {
  const wordsetsResponse = await getWordsets();
  const wordsets = (wordsetsResponse && wordsetsResponse.data) || [];

  const entries = await Promise.all(
    wordsets.map(async (ws) => {
      const userwords = await getUserWordsByWordset(userId, ws.wordset_id);
      return {
        wordsetId: ws.wordset_id,
        description: ws.description,
        words: (userwords && userwords.data) || [],
      };
    })
  );

  // One clock for the whole aggregation — see `dueByWordset`. The fan-out
  // above is concurrent and its responses arrive in any order, so binding the
  // clock per response would be binding it in arrival order.
  //
  // Returns the per-set breakdown AND the total derived from it, rather than a
  // bare total: Today's single Start action has to open ONE wordset, because
  // the practice route is `/game/:wordsetId/:mode`. Deriving the total from the
  // same array Start chooses from is what keeps the headline number and the
  // session it opens from disagreeing.
  const sets = dueByWordset(entries);
  return { total: totalDue(sets), sets };
};

export const useDueToday = (userId) => {
  const [state, setState] = useState({ status: 'loading', total: 0, sets: [] });
  // Bumping this re-runs the effect. The error path below is otherwise
  // terminal — a learner whose first load hit a flaky network would have no
  // way back to their reviews short of a full page reload.
  const [attempt, setAttempt] = useState(0);
  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    // Signed out: there is no due set, and that is a real answer rather than a
    // failure — 'idle' so the caller can render a signed-out home instead of an
    // error or a spinner that never resolves.
    if (!userId) {
      setState({ status: 'idle', total: 0, sets: [] });
      return undefined;
    }

    let cancelled = false;
    // Re-entering 'loading' on retry, so the retry has visible feedback rather
    // than looking like a dead button while the fan-out is in flight.
    setState((prev) => (prev.status === 'loading' ? prev : { ...prev, status: 'loading' }));

    loadDueToday(userId)
      .then(({ total, sets }) => {
        if (!cancelled) setState({ status: 'ready', total, sets });
      })
      .catch(() => {
        // Fail to an explicit error rather than to 0. A silent 0 is
        // indistinguishable from "you are all caught up" — it would tell a
        // learner with reviews waiting that there is nothing to do, which is
        // the one wrong answer this screen must never give.
        if (!cancelled) setState({ status: 'error', total: 0, sets: [] });
      });

    return () => {
      cancelled = true;
    };
  }, [userId, attempt]);

  return { ...state, reload };
};
