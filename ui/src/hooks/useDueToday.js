import { useState, useEffect, useCallback } from 'react';
import { getWordsets } from '../services/wordsService';
import { getUserWordsByWordset, getDueCounts } from '../services/userService';
import { dueByWordset, totalDue } from '../utils/srs';
import { userwordsKey } from '../utils/wordsetCache';

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
// Separated from the hook deliberately: the part worth pinning is the
// aggregation and the failure mode, and keeping it a plain async function means
// most of this file is testable without React at all.
//
// ⚠️ CORRECTED (issue-297 AC2). This comment used to say the repo "has no React
// testing library (all ten existing suites are pure logic)" and that the
// dependency "cannot be exercised in CI". Both were true when written and both
// are now FALSE — measured 2026-09-12: `@testing-library/react@14.3.1` is
// installed, `AuthContext.test.js` and `CardErrorBoundary.test.js` already mount
// components with it, `.github/workflows/ui-tests.yml` runs the suite on `ui/**`,
// and there are 42 suites, not ten. The hook IS testable; `useDueToday.test.js`
// exercises it with `renderHook`. Left as a correction rather than deleted: the
// stale version had already talked one reader (me) out of testing this hook.
//
// Same shape as `dueAcrossWordsets` taking already-fetched lists: keep the
// logic pure and let the thin wrapper be obviously correct by inspection.
// issue-335: publish each fan-out response so the practice loader can reuse it.
//
// Today fetches `/userwords/query` for EVERY wordset; opening one for practice
// then fetched the same rows again, because `useWordsetLoader`'s cache is keyed
// on its own MAPPED shape and nothing wrote the raw rows anywhere both could
// see. Passed in rather than imported so the pure `loadDueToday` stays
// testable without a window — the hook supplies the real shared cache.
//
// ⚠️ issue-384: only the FALLBACK path below populates this now. The fast path
// never fetches rows, so it has none to publish — opening a set for practice
// fetches its own, once, instead of reusing what Today happened to have warmed.
// That is a deliberate trade: the warm cost was being paid SEVEN times on every
// Today load to save ONE fetch on a session that may never start.
//
// DIRECTIONAL ON PURPOSE: Today WRITES and never READS. Today is the surface
// that has to reflect practice you just finished, so it must always ask the
// network; the loader is the consumer. Reading here would make the due count
// answer from before the session that changed it, which is the one wrong answer
// this screen must never give (see the error path below for the same argument).
// issue-384: the fan-out below is now the FALLBACK, not the path.
//
// It asked `/userwords/query` once per visible wordset, concurrently, and each
// response carried every word in that set with up to three recall-history rows
// — ~5,600 words and ~16,000 rows to render seven integers. Measured
// user-visible result: 10s+ and then "Couldn't load today's reviews", because a
// `Promise.all` fails whole when any one set is slow.
//
// `/userwords/due-counts` returns the seven integers. It is fast BY
// CONSTRUCTION rather than by tuning: its response does not grow with the size
// of a wordset, so this screen cannot drift back into the same shape.
//
// 🔴 THE FALLBACK IS SCOPED TO 404 ON PURPOSE, and that is the load-bearing
// half. The UI and the backend deploy from two separate triggers, so a UI that
// ships first would call an endpoint that does not exist yet; falling back
// keeps the screen working (slowly, as today) through that window. But falling
// back on ANY error would make a genuinely broken endpoint invisible forever —
// the screen would quietly do the slow thing and nobody would ever learn the
// fast path had stopped working. A 500, a timeout, or a bad payload must
// surface as the error this screen already knows how to show.
//
// ⏳ DELETE THIS FALLBACK once the backend is deployed and verified. It is
// transitional, and a transitional path with no expiry is how a codebase ends
// up with two live implementations of the same screen.
const isEndpointAbsent = (err) =>
  Boolean(err && err.response && err.response.status === 404);

// issue-297 AC2: `wordsets` is an OPTIONAL pre-resolved list. Passing it lets a
// caller that already holds the (user-INDEPENDENT) list skip a redundant GET —
// see `useDueToday` below, where the list has its own effect. Omitted, the
// behaviour is exactly as before, which is why every existing caller and all
// 22 `loadDueToday` assertions in the sister test file are untouched.
export const loadDueToday = async (userId, cache = null, wordsets = null) => {
  if (wordsets === null) {
    const wordsetsResponse = await getWordsets();
    wordsets = (wordsetsResponse && wordsetsResponse.data) || [];
  }

  try {
    const response = await getDueCounts(userId);
    const rows = (response && response.data) || [];
    const byId = new Map(rows.map((r) => [String(r.wordset_id), Number(r.due) || 0]));
    // Mapped over the VISIBLE wordsets, not over the response: the hide-list
    // for the internal `test`/`HSK7` sets lives in `getWordsets` and must stay
    // in one place. A set the server did not count has nothing due, which is
    // why a missing id defaults to 0 rather than being dropped — dropping it
    // would remove the set from `pickStartSet`'s input as well.
    const sets = wordsets.map((ws) => ({
      wordsetId: ws.wordset_id,
      description: ws.description,
      due: byId.get(String(ws.wordset_id)) || 0,
    }));
    return { total: totalDue(sets), sets };
  } catch (err) {
    if (!isEndpointAbsent(err)) throw err;
    if (typeof console !== 'undefined' && console.warn) {
      console.warn('[due-today] /userwords/due-counts is absent (404) — '
        + 'falling back to the per-wordset fan-out. This is the slow path.');
    }
  }

  const entries = await Promise.all(
    wordsets.map(async (ws) => {
      const userwords = await getUserWordsByWordset(userId, ws.wordset_id);
      if (cache) {
        cache[userwordsKey(userId, ws.wordset_id)] = (userwords && userwords.data) || [];
      }
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

// The window-scoped object `useWordsetLoader` already keeps its raw and view
// slots in. Resolved lazily rather than at module load so importing this file
// in a test (no `window`) stays free.
const sharedWordsetCache = () => {
  if (typeof window === 'undefined') return null;
  if (!window.userWordsetExcludedCache) window.userWordsetExcludedCache = {};
  return window.userWordsetExcludedCache;
};

export const useDueToday = (userId) => {
  const [state, setState] = useState({ status: 'loading', total: 0, sets: [] });
  // Bumping this re-runs the effect. The error path below is otherwise
  // terminal — a learner whose first load hit a flaky network would have no
  // way back to their reviews short of a full page reload.
  const [attempt, setAttempt] = useState(0);
  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  // issue-297 AC2: the wordset LIST does not depend on `userId`, so it gets its
  // OWN effect. Folded into the effect below it was refetched on every identity
  // change -- measured at two `GET /wordsets` per arrival where one suffices,
  // the second being this hook re-running after guest entry.
  //
  // Keyed on [attempt] rather than []: `reload` is a retry of the whole screen,
  // and a list fetch that failed must get a second chance too.
  //
  // Three states in one slot, and the third must not read as the first:
  //   null            -- not resolved yet; the effect below must WAIT, not render 0
  //   Error instance  -- the list fetch failed; that is this screen's error state
  //   array           -- resolved
  // A bare `[]` cannot express "not yet", and rendering 0 due while the list is
  // still in flight is the one wrong answer this screen must never give.
  const [wordsets, setWordsets] = useState(null);
  useEffect(() => {
    let cancelled = false;
    getWordsets()
      .then((res) => {
        if (!cancelled) setWordsets((res && res.data) || []);
      })
      .catch((err) => {
        if (!cancelled) {
          setWordsets(err instanceof Error ? err : new Error('wordsets fetch failed'));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  useEffect(() => {
    // Signed out: there is no due set, and that is a real answer rather than a
    // failure — 'idle' so the caller can render a signed-out home instead of an
    // error or a spinner that never resolves.
    if (!userId) {
      setState({ status: 'idle', total: 0, sets: [] });
      return undefined;
    }

    // The list is still in flight. Stay in 'loading' -- returning here without
    // touching state is deliberate: this effect re-runs when `wordsets` lands.
    if (wordsets === null) return undefined;
    // The list itself failed. Same error state as a failed fan-out, for the same
    // reason: a silent 0 would read as "you are all caught up".
    if (wordsets instanceof Error) {
      setState({ status: 'error', total: 0, sets: [] });
      return undefined;
    }

    let cancelled = false;
    // Re-entering 'loading' on retry, so the retry has visible feedback rather
    // than looking like a dead button while the fan-out is in flight.
    setState((prev) => (prev.status === 'loading' ? prev : { ...prev, status: 'loading' }));

    loadDueToday(userId, sharedWordsetCache(), wordsets)
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
  }, [userId, attempt, wordsets]);

  return { ...state, reload };
};
