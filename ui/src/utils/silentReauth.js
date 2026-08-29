// lexitrail#199 — re-obtain a Google access token WITHOUT a click, for a member
// returning after their old token expired.
//
// #185 made a member session survive a browser CLOSE. It cannot make one
// survive OVERNIGHT and no storage change can: `useGoogleLogin` runs the
// IMPLICIT flow, the access token lives ~1h, and there is no refresh token to
// renew it with. The returning-tomorrow case — which is what #185's evidence is
// actually about — needs the token re-ACQUIRED, not stored longer.
//
// 🔴 THE NAIVE VERSION IS WORSE THAN DOING NOTHING, and it is worth naming
// because it is the tempting one: keeping the old token past its expiry
// produces a UI that says "signed in" over a token that 401s on every request.
// `authStorage.loadSession` already refuses an expired session precisely so
// this module has somewhere honest to hook in. Nothing here extends a token's
// welcome; it either gets a NEW one or reports nothing.
//
// ## Why the GIS token client and not `useGoogleLogin({ prompt: 'none' })`
//
// `useGoogleLogin` opens a popup, and a popup with no user gesture behind it is
// blocked by every browser that matters — so the one thing this feature must do
// (run on load, with no click) is the one thing that path cannot do.
//
// ⚠️ And NOT One Tap (`google.accounts.id`) either, which is the other obvious
// candidate: it returns an ID token (a JWT identifying the user), and what this
// app needs is an ACCESS token to call `googleapis.com/oauth2/v3/userinfo` and
// the backend. Two different credentials with similar names; substituting one
// would authenticate the user and still leave every request unauthorized.
//
// `google.accounts.oauth2.initTokenClient` with `prompt: ''` is the path that
// yields an access token and may complete with no UI when consent already
// exists. When it cannot, it fails — and failing is the correct outcome here.

const SIGNED_IN_BEFORE_KEY = 'lexitrail.has_signed_in_before';

/** Record that THIS BROWSER has completed a real Google sign-in.
 *
 * Deliberately NOT one of `authStorage`'s keys, and deliberately not cleared by
 * `clearSession()`. Those keys are the session; this is a fact about the
 * browser that must OUTLIVE the session — the whole point is to know, after the
 * token expired and the session was cleared, that a silent attempt is worth
 * making. Storing it alongside the session would erase it at exactly the moment
 * it becomes useful.
 */
export const markSignedInBefore = () => {
  try {
    window.localStorage.setItem(SIGNED_IN_BEFORE_KEY, '1');
  } catch (_) { /* private mode / storage disabled — degrade to today's flow */ }
};

/** True if a real sign-in has happened in this browser before. */
export const hasSignedInBefore = () => {
  try {
    return window.localStorage.getItem(SIGNED_IN_BEFORE_KEY) === '1';
  } catch (_) {
    return false;   // unreadable storage means "do not attempt", never "attempt"
  }
};

/** Forget the hint. Called on EXPLICIT sign-out only.
 *
 * 🔴 The asymmetry with `clearSession` is the point. An expired token is not a
 * decision — the member wants to stay signed in and the clock disagreed — so
 * the hint survives and the next load tries silently. Clicking "sign out" IS a
 * decision, and silently signing that member back in on their next visit would
 * defeat it. Same storage, opposite meanings, which is why they are separate
 * calls rather than one "clear everything".
 */
export const forgetSignedInBefore = () => {
  try {
    window.localStorage.removeItem(SIGNED_IN_BEFORE_KEY);
  } catch (_) { /* nothing we can do, and nothing depends on it succeeding */ }
};

/** Attempt a no-UI token acquisition. Resolves to `{ access_token, expires_in }`
 * or to `null`. NEVER rejects, and never writes storage.
 *
 * Returning `null` rather than throwing is deliberate: a failed silent attempt
 * (consent revoked, several signed-in accounts, third-party cookies blocked) is
 * not an error the user should see. It means "fall through to the signed-out
 * page exactly as today", which is a normal outcome, not a fault.
 *
 * 🔴 It does not touch `authStorage`. AC4 is that a failed attempt leaves NO
 * session behind, and the cheapest way to guarantee that is for the acquiring
 * step to have no power to write one — the caller writes, once, on success.
 * An attempt that half-writes is the regression to fear here.
 */
export const attemptSilentTokenGrant = ({ google, clientId, scope } = {}) =>
  new Promise((resolve) => {
    const oauth2 = google?.accounts?.oauth2;
    if (!oauth2?.initTokenClient || !clientId) {
      // The GIS script has not loaded, or there is no client id. Not an error:
      // indistinguishable to the user from "silent re-auth did not work".
      resolve(null);
      return;
    }
    let settled = false;
    const done = (value) => {
      if (settled) return;      // GIS may invoke both callbacks on some paths
      settled = true;
      resolve(value);
    };
    try {
      const client = oauth2.initTokenClient({
        client_id: clientId,
        scope: scope || 'openid profile email',
        // '' means "no prompt at all" — the request succeeds only if consent
        // already exists for this client and exactly one account is signed in.
        // 'none' is the `google.accounts.id` spelling; the token client takes
        // the empty string, and passing the wrong one prompts.
        prompt: '',
        callback: (response) => {
          if (response?.access_token) {
            done({
              access_token: response.access_token,
              expires_in: Number(response.expires_in),
            });
          } else {
            done(null);
          }
        },
        error_callback: () => done(null),
      });
      client.requestAccessToken();
    } catch (_) {
      done(null);   // any GIS-side throw is a failed attempt, not a crash on load
    }
  });
