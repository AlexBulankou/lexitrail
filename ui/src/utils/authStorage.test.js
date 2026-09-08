// lexitrail#185 — the storage half of "a member is signed out on every browser close".
//
// 🔴 THE TEST THAT MATTERS IS THE EXPIRY ONE. The naive fix for #185 is
// sessionStorage -> localStorage and nothing else, which passes any test that
// only checks "does the session come back". It also restores a session whose
// Google token died an hour ago, producing a signed-in UI over a token that
// 401s on every call. So the round-trip tests below are the easy half and the
// expired/unstamped ones are the point.
import {
  loadSession, loadAccessToken, saveMemberSession, saveGuestSession,
  clearSession, isGuestToken,
} from './authStorage';

const MEMBER = { email: 'a@b.co', name: 'A' };
const GUEST = { email: 'xk39f@lexitrail.demo', name: 'Demo User' };
const T0 = 1_700_000_000_000;
const HOUR = 3600 * 1000;

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe('member sessions survive a browser close', () => {
  test('a fresh member session round-trips out of localStorage', () => {
    saveMemberSession(MEMBER, 'tok', 3600, T0);
    // sessionStorage is what dies on close; prove we did not use it.
    expect(window.sessionStorage.getItem('user')).toBeNull();
    expect(loadSession(T0 + 60_000)).toEqual({ user: MEMBER, token: 'tok' });
  });

  test('the API layer sees the same token, via the same expiry rule', () => {
    saveMemberSession(MEMBER, 'tok', 3600, T0);
    expect(loadAccessToken(T0 + 60_000)).toBe('tok');
  });
});

describe('an EXPIRED session is signed-out, not restored', () => {
  test('🔴 the bug shape: past its expiry, loadSession refuses it', () => {
    saveMemberSession(MEMBER, 'tok', 3600, T0);
    // One hour and one second later -- a member returning "tomorrow" is this,
    // only further out. The naive localStorage swap returns MEMBER here.
    expect(loadSession(T0 + HOUR + 1000)).toBeNull();
  });

  test('and CLEARS it, so the next read is not asked the same question', () => {
    saveMemberSession(MEMBER, 'tok', 3600, T0);
    loadSession(T0 + HOUR + 1000);
    expect(window.localStorage.getItem('user')).toBeNull();
    expect(window.localStorage.getItem('access_token')).toBeNull();
  });

  test('the API layer refuses it too -- one rule, not two', () => {
    saveMemberSession(MEMBER, 'tok', 3600, T0);
    expect(loadAccessToken(T0 + HOUR + 1000)).toBeNull();
  });

  test('exactly AT the expiry instant is already expired', () => {
    // A boundary stated rather than left to chance: `expiresAt <= now`.
    //
    // 🔴 THE ORDER OF THESE TWO ASSERTIONS IS LOAD-BEARING, and I got it
    // backwards first: reading an EXPIRED session CLEARS it, so asserting the
    // expired case first makes the still-valid case fail with `null` -- a red
    // that looks like an off-by-one in the module and is an artifact of the
    // test. Probe the live side before the destructive one.
    saveMemberSession(MEMBER, 'tok', 3600, T0);
    expect(loadSession(T0 + HOUR - 1)).toEqual({ user: MEMBER, token: 'tok' });
    expect(loadSession(T0 + HOUR)).toBeNull();
  });

  test('a session with NO expiry stamp is refused, not trusted', () => {
    // Google omitted expires_in. Failing toward a sign-in prompt is recoverable
    // by the user; failing toward a dead token is not.
    saveMemberSession(MEMBER, 'tok', undefined, T0);
    expect(loadSession(T0 + 1000)).toBeNull();
  });
});

describe('a guest is per-BROWSER, not per-tab (#348, zz1 RULING A)', () => {
  // 🔴 This block asserted the OPPOSITE until #348 ("a guest is stored
  // tab-scoped, never in localStorage"). Rewritten rather than deleted-and-
  // replaced so the inversion is visible in the diff: #185 deliberately left
  // guests alone and named #348 as where the trade would be decided.
  const GTOK = 'UNAUTH_USER:xk39f@lexitrail.demo';

  test('a guest is stored per-browser, in localStorage', () => {
    saveGuestSession(GUEST, GTOK);
    expect(window.localStorage.getItem('user')).not.toBeNull();
    expect(loadSession(T0)).toEqual({ user: GUEST, token: GTOK });
  });

  test('🔴 A SECOND TAB FINDS THE SAME GUEST — the whole point of #348', () => {
    // The defect, as a fixture. sessionStorage is per-tab, so the second tab
    // saw nothing, hit the login wall and minted another @lexitrail.demo row.
    // A new tab is modelled by clearing sessionStorage ONLY: localStorage is
    // origin-shared and survives, which is exactly the asymmetry under test.
    saveGuestSession(GUEST, GTOK);
    window.sessionStorage.clear();
    expect(loadSession(T0)).toEqual({ user: GUEST, token: GTOK });
  });

  test('🔴 a guest carries NO expiry and must survive the expiry gate', () => {
    // The load-bearing one. Moving guests into localStorage puts them behind
    // the gate that refuses unstamped sessions -- so without the isGuestToken
    // bypass in loadSession, every guest is signed out on their first reload
    // and #348 makes guests strictly WORSE than the per-tab behaviour it
    // replaced. A thousand hours later, still valid.
    saveGuestSession(GUEST, GTOK);
    expect(loadSession(T0 + 1000 * HOUR)).toEqual({ user: GUEST, token: GTOK });
  });

  test('🔴 CONTROL: a member row with NO expiry is STILL refused', () => {
    // The bypass above must key on the TOKEN SHAPE, not on the expiry being
    // absent. Keyed on the absence instead, this row would be returned -- a
    // signed-in UI over a token that 401s, which is the one failure this whole
    // module exists to prevent. Same input shape as the test above; only the
    // token differs.
    window.localStorage.setItem('user', JSON.stringify(MEMBER));
    window.localStorage.setItem('access_token', 'ya29.a0AfRealGoogleToken');
    expect(loadSession(T0)).toBeNull();
  });

  test('a guest started in THIS tab still wins over a stale member row', () => {
    // The legacy path: a tab open across the #348 deploy, or a browser where
    // the localStorage write threw. sessionStorage still wins.
    window.localStorage.setItem('user', JSON.stringify(MEMBER));
    window.localStorage.setItem('access_token', 'stale');
    window.localStorage.setItem('access_token_expires_at', String(T0 + HOUR));
    window.sessionStorage.setItem('user', JSON.stringify(GUEST));
    window.sessionStorage.setItem('access_token', GTOK);
    expect(loadSession(T0)?.user).toEqual(GUEST);
  });

  // zz1's explicit rail on the ruling: a private window can throw on storage
  // access outright, and a crash during sign-in is not an acceptable degraded
  // mode. Two arms, because they exercise DIFFERENT catches and the second one
  // is the arm I only wrote after the first accidentally produced it.
  //
  // ⚠️ The mock has to replace the localStorage INSTANCE, not patch
  // `Storage.prototype.setItem`. jsdom gives both stores the SAME prototype, so
  // a prototype spy breaks sessionStorage too and the "falls back" arm silently
  // becomes the "both refused" arm — passing its `not.toThrow()` while
  // asserting nothing about the fallback. That is how I first wrote it.
  const withBrokenLocalStorage = (fn) => {
    const real = window.localStorage;
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      value: { getItem: () => null, removeItem: () => {},
               setItem: () => { throw new DOMException('QuotaExceededError'); } },
    });
    try { fn(); } finally {
      Object.defineProperty(window, 'localStorage', { configurable: true, value: real });
    }
  };

  test('storage-blocked: a throwing localStorage falls back to PER-TAB, not a crash', () => {
    withBrokenLocalStorage(() => {
      expect(() => saveGuestSession(GUEST, GTOK)).not.toThrow();
      expect(window.sessionStorage.getItem('user')).not.toBeNull();
      expect(loadSession(T0)).toEqual({ user: GUEST, token: GTOK });
    });
  });

  test('BOTH stores refused: still no crash, and no session survives the reload', () => {
    // The honest end state. React state carries the identity for this page
    // view; nothing persists. Asserting the null explicitly so a future change
    // that "fixes" it by writing somewhere else has to say so here.
    const spy = jest.spyOn(Storage.prototype, 'setItem')
      .mockImplementation(() => { throw new DOMException('QuotaExceededError'); });
    try {
      expect(() => saveGuestSession(GUEST, GTOK)).not.toThrow();
    } finally {
      spy.mockRestore();
    }
    expect(loadSession(T0)).toBeNull();
  });

  test('isGuestToken discriminates, in both directions', () => {
    expect(isGuestToken('UNAUTH_USER:a@lexitrail.demo')).toBe(true);
    expect(isGuestToken('ya29.a0Af...')).toBe(false);
    expect(isGuestToken(null)).toBe(false);
  });
});

describe('the guest branch is gated on the TOKEN, not on sessionStorage being non-empty (PR #200 review)', () => {
  test('🔴 a pre-#185 MEMBER session left in sessionStorage is not read back as a guest', () => {
    // The deploy transient: a tab open across the deploy still holds the old
    // sessionStorage-only member session. Ungated, loadSession returns it --
    // and returns it via the branch that applies NO expiry check, so a real
    // Google token would be trusted indefinitely.
    window.sessionStorage.setItem('user', JSON.stringify(MEMBER));
    window.sessionStorage.setItem('access_token', 'ya29.a0AfLegacyRealGoogleToken');
    expect(loadSession(T0)).toBeNull();
  });

  test('CONTROL: the same shape WITH a guest token is still accepted', () => {
    // Without this, the assertion above passes equally well against a branch
    // that rejects everything -- which would sign every guest out.
    window.sessionStorage.setItem('user', JSON.stringify(GUEST));
    window.sessionStorage.setItem('access_token', 'UNAUTH_USER:xk39f@lexitrail.demo');
    expect(loadSession(T0)).toEqual({
      user: GUEST, token: 'UNAUTH_USER:xk39f@lexitrail.demo' });
  });

  test('a legacy member row does not shadow a VALID localStorage session either', () => {
    // The ordering test elsewhere proves sessionStorage wins. That is correct
    // for a guest and wrong for this leftover, so the gate has to make the
    // localStorage session reachable past it.
    saveMemberSession(MEMBER, 'tok', 3600, T0);
    window.sessionStorage.setItem('user', JSON.stringify(MEMBER));
    window.sessionStorage.setItem('access_token', 'ya29.a0AfLegacyRealGoogleToken');
    expect(loadSession(T0 + 60_000)).toEqual({ user: MEMBER, token: 'tok' });
  });
});

describe('clearing and malformed state', () => {
  test('clearSession clears BOTH stores, not just the one we read', () => {
    saveMemberSession(MEMBER, 'tok', 3600, T0);
    window.sessionStorage.setItem('user', JSON.stringify(GUEST));
    window.sessionStorage.setItem('access_token', 'UNAUTH_USER:x@lexitrail.demo');
    clearSession();
    expect(loadSession(T0)).toBeNull();
    expect(window.sessionStorage.getItem('user')).toBeNull();
    expect(window.localStorage.getItem('user')).toBeNull();
  });

  test('a malformed blob is no session, not a crash on app load', () => {
    window.localStorage.setItem('user', '{not json');
    window.localStorage.setItem('access_token', 'tok');
    window.localStorage.setItem('access_token_expires_at', String(T0 + HOUR));
    expect(() => loadSession(T0)).not.toThrow();
    expect(loadSession(T0)).toBeNull();
  });

  test('a token with no user is not a session', () => {
    window.localStorage.setItem('access_token', 'tok');
    expect(loadSession(T0)).toBeNull();
  });
});

describe('the OTHER reader is wired (#185)', () => {
  // `apiService.getAccessToken` read `sessionStorage` directly. Moving member
  // sessions to localStorage without changing it would leave every API call
  // tokenless -- a total outage from a change that looks contained to auth.
  //
  // 🔴 A NEGATIVE SOURCE ASSERTION, and the direction is chosen deliberately.
  // A comment that merely MENTIONS sessionStorage cannot make this pass
  // (it matches `.getItem(`, a call); it could only make it FAIL, which is the
  // recoverable direction -- someone investigates a red. The reverse guard
  // ("does it import authStorage") is satisfiable by prose, so it is not used.
  const fs = require('fs');
  const path = require('path');

  test('apiService reads no browser storage directly', () => {
    const src = fs.readFileSync(
      path.join(__dirname, '..', 'services', 'apiService.js'), 'utf8');
    const direct = src.match(/(session|local)Storage\s*\.\s*getItem\s*\(/g) || [];
    expect(direct).toEqual([]);
  });

  test('CONTROL: the pattern does find a direct read where one exists', () => {
    // Without this, the assertion above passes just as well against a regex
    // that matches nothing at all -- and a guard that cannot fire is not a
    // guard. streakStore.js genuinely reads localStorage directly.
    const src = fs.readFileSync(
      path.join(__dirname, '..', 'services', 'streakStore.js'), 'utf8');
    const direct = src.match(/(session|local)Storage\s*\.\s*getItem\s*\(/g) || [];
    expect(direct.length).toBeGreaterThan(0);
  });
});
