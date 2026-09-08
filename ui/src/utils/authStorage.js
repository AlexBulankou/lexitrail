// lexitrail#185 — where the signed-in session lives, and for how long.
//
// THE DEFECT. `AuthContext` wrote `user` and `access_token` to sessionStorage
// only, which dies with the tab. A member who practiced yesterday reopens
// lexitrail.com and lands on the signed-out marketing page — no streak, no due
// reviews. GA4 shows the signature: 84 `login_to_google_click` from ~3 users
// across 58 distinct days in 90d, i.e. one person re-authenticating nearly
// daily.
//
// 🔴 THE OBVIOUS FIX IS WORSE THAN THE BUG, WHICH IS WHY THIS IS A MODULE.
//
// Swapping sessionStorage for localStorage and stopping there restores a
// session whose access token has since EXPIRED. `useGoogleLogin` runs the
// implicit flow: the token lives ~1h and there is NO refresh token to renew it
// with. So the naive swap produces a UI that says "signed in", renders the
// Today home, and 401s on every request behind it — strictly worse than an
// honest sign-in prompt, and harder to diagnose because the failure is in the
// network tab rather than on the screen.
//
// So every read here is EXPIRY-CHECKED, and an expired session is cleared and
// reported as signed-out rather than returned. `null` from `loadSession()`
// means "no usable session", never "no stored session" — those are different
// facts and only one of them should reach the UI.
//
// ⚠️ WHAT THIS DOES NOT DO. It does not get a member who returns TOMORROW
// signed in — nothing can, without silent re-auth, because the token is dead by
// then. #185's AC says "reopen the browser *within the auth lifetime*", which is
// exactly this. The rest is lexitrail#199 (Google silent re-auth), and the two
// are deliberately separate: this half is a storage change with a bounded blast
// radius, that half touches the sign-in flow.
//
// 🔴 GUESTS MOVED TO localStorage — lexitrail#348, zz1 RULING A (2026-09-05).
// This paragraph used to say the opposite and is CORRECTED rather than deleted,
// because the reasoning it carried is still the live objection and a reader who
// meets only the new behaviour would re-derive it as a defect.
//
// It read: guests stay per-tab, since "persisting it across browser sessions
// would accumulate orphan accounts and would also let a shared machine hand one
// visitor's practice data to the next."
//
// The first half was BACKWARDS and #348 measured it: sessionStorage is per-TAB,
// so a second tab finds no `user`, hits the login wall, and mints ANOTHER
// `<random>@lexitrail.demo` row. Per-tab storage is what accumulates orphans;
// one identity per browser is what stops it.
//
// ⚠️ The second half stands and is the accepted cost, not an oversight: on a
// SHARED machine the next visitor now inherits the previous visitor's guest
// practice data. Weighed and accepted — a guest row holds Chinese-vocabulary
// recall state and no personal data, and the retention gain (a returning
// visitor keeps their progress) was zz1's stated basis. If that trade is ever
// revisited, this is the sentence to revisit; it is not a thing nobody thought
// about.
//
// #185 deliberately scoped guests OUT ("guest behaviour unchanged") and named
// this issue as where the trade would be decided. It has been.

const USER_KEY = 'user';
const TOKEN_KEY = 'access_token';
const EXPIRES_KEY = 'access_token_expires_at';

// A guest token is `UNAUTH_USER:<demo email>` and carries no expiry — the
// backend accepts it on shape, not on time. Real Google tokens are opaque.
export const isGuestToken = (token) => typeof token === 'string' && token.startsWith('UNAUTH_USER:');

const safeParse = (raw) => {
  try {
    return raw ? JSON.parse(raw) : null;
  } catch (_) {
    return null;  // a malformed blob is no session, not a crash on load
  }
};

/** Clear BOTH stores. Used on sign-out and on finding an expired session.
 *
 * Both, always: a member who signed in, then used the app as a guest in
 * another tab, has rows in each. Clearing only the one we happened to read
 * leaves the other to be picked up on the next load as if it were current.
 */
export const clearSession = () => {
  [window.localStorage, window.sessionStorage].forEach((store) => {
    [USER_KEY, TOKEN_KEY, EXPIRES_KEY].forEach((k) => store.removeItem(k));
  });
};

/** Persist a signed-in member across browser sessions.
 *
 * `expiresInSeconds` comes from Google's `tokenResponse.expires_in`. When it is
 * missing we store NO expiry and `loadSession` then refuses the session on the
 * next load — failing toward a sign-in prompt rather than toward a dead token,
 * because only one of those two is recoverable by the user.
 */
export const saveMemberSession = (user, token, expiresInSeconds, now = Date.now()) => {
  clearSession();
  window.localStorage.setItem(USER_KEY, JSON.stringify(user));
  window.localStorage.setItem(TOKEN_KEY, token);
  if (Number.isFinite(expiresInSeconds)) {
    window.localStorage.setItem(EXPIRES_KEY, String(now + expiresInSeconds * 1000));
  }
};

/** Persist a guest per BROWSER (#348). Falls back to per-tab if storage throws.
 *
 * The try/catch is zz1's explicit rail on the ruling, and it is not defensive
 * noise: a private window can throw on `localStorage` access outright, and the
 * failure mode without it is a crash during sign-in rather than a degraded
 * guest. Falling back to `sessionStorage` restores exactly the pre-#348
 * behaviour — one identity per tab — which is worse than the new behaviour and
 * far better than not signing in at all.
 *
 * ⚠️ The inner write is guarded too. A browser that refuses `localStorage`
 * usually refuses `sessionStorage` as well, so an unguarded fallback turns one
 * throw into another throw from a different line — the same crash, harder to
 * read.
 */
export const saveGuestSession = (user, token) => {
  clearSession();
  try {
    window.localStorage.setItem(USER_KEY, JSON.stringify(user));
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch (_) {
    try {
      window.sessionStorage.setItem(USER_KEY, JSON.stringify(user));
      window.sessionStorage.setItem(TOKEN_KEY, token);
    } catch (__) {
      // Both stores refused. The caller already has the identity in React
      // state, so this session works and simply does not survive a reload.
    }
  }
};

/** The usable session, or null. Never returns an expired member session.
 *
 * Order matters: sessionStorage wins over localStorage. Post-#348 a guest is
 * normally written to localStorage, so this branch now covers two narrower
 * cases and is still load-bearing for both — a tab that was already open when
 * #348 deployed, and a browser where the localStorage write threw and
 * `saveGuestSession` fell back to per-tab.
 */
export const loadSession = (now = Date.now()) => {
  const guestUser = safeParse(window.sessionStorage.getItem(USER_KEY));
  const guestToken = window.sessionStorage.getItem(TOKEN_KEY);
  // lexitrail#185 follow-up (hc2@'s review Q on PR #200): gated on the token
  // actually BEING guest-shaped, not merely on sessionStorage having something
  // in it. Without the gate this branch means "trust whatever is in
  // sessionStorage", and the one thing that can put a NON-guest token there is
  // a pre-#185 member session in a tab that was already open when this
  // deployed -- which would then be returned with NO expiry check, the exact
  // shape the rest of this module exists to refuse.
  //
  // ⚠️ The trade is deliberate and it is not free: a member in such a tab is
  // signed OUT on the next render instead of riding their old session to its
  // natural expiry. That is one click, and it is the honest failure -- the
  // alternative is a signed-in UI over a token that 401s, which is the one
  // failure a user cannot diagnose or recover from. Transient either way: the
  // legacy rows exist only until that tab closes.
  if (guestUser && isGuestToken(guestToken)) return { user: guestUser, token: guestToken };

  const user = safeParse(window.localStorage.getItem(USER_KEY));
  const token = window.localStorage.getItem(TOKEN_KEY);
  const expiresAt = Number(window.localStorage.getItem(EXPIRES_KEY));
  if (!user || !token) return null;

  // lexitrail#348: a guest now lives HERE, and carries no expiry — the backend
  // accepts its token on SHAPE, not time. Without this the expiry gate below
  // sees an unstamped session, clears it, and signs every guest out on their
  // first reload: the move to localStorage would have made guests strictly
  // worse than the per-tab behaviour it replaced.
  //
  // 🔴 Gated on `isGuestToken`, NOT on "no expiry". Those look interchangeable
  // here and are not: an unstamped MEMBER session is exactly what this module
  // exists to refuse (a UI that says signed-in over a token that 401s), so a
  // bypass keyed on the absent expiry would re-open that hole while looking
  // like the same fix. `test_a_member_row_with_no_expiry_is_STILL_refused` is
  // the control on that distinction.
  if (isGuestToken(token)) return { user, token };

  if (!Number.isFinite(expiresAt) || expiresAt <= now) {
    // Expired or unstamped. Clear it so the next read is not asked the same
    // question, and report signed-out.
    clearSession();
    return null;
  }
  return { user, token };
};

/** The token the API layer should send, or null. Same expiry rule. */
export const loadAccessToken = (now = Date.now()) => loadSession(now)?.token ?? null;
