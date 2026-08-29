// lexitrail#199 — tests for the silent re-auth primitives.
//
// AC1 ("close the browser, return the next day, land signed in") is NOT
// testable here and is not testable anywhere in this repo: it needs a real
// Google consent, a real browser and a real tomorrow. The e2e suite seeds only
// GUEST sessions (`UNAUTH_USER:` tokens) and has no authenticated path at all.
// That is stated rather than papered over -- a test named for AC1 that mocked
// the grant would assert this file's own mock, not the behaviour.
//
// What IS pinned here is everything that decides whether AC1's mechanism is
// SAFE: AC2 (no change for a user who never signed in), AC4 (a failed attempt
// leaves no session), and the storage semantics that separate an expired
// session from a deliberate sign-out.

import {
  attemptSilentTokenGrant,
  forgetSignedInBefore,
  hasSignedInBefore,
  markSignedInBefore,
} from './silentReauth';

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
});

// ── The hint ────────────────────────────────────────────────────────────────

describe('the signed-in-before hint', () => {
  test('is false before any sign-in — AC2', () => {
    expect(hasSignedInBefore()).toBe(false);
  });

  test('is true after a real sign-in records it', () => {
    markSignedInBefore();
    expect(hasSignedInBefore()).toBe(true);
  });

  test('SURVIVES a session clear, which is the whole point', () => {
    // The hint exists to be read AFTER the token expired and the session was
    // cleared. Storing it with the session would erase it exactly when it
    // becomes useful, so this pins that it is not one of authStorage's keys.
    markSignedInBefore();
    ['user', 'access_token', 'access_token_expires_at'].forEach((k) => {
      window.localStorage.removeItem(k);
      window.sessionStorage.removeItem(k);
    });
    expect(hasSignedInBefore()).toBe(true);
  });

  test('an EXPLICIT sign-out forgets it — the asymmetry with expiry', () => {
    // 🔴 The load-bearing distinction. An expired token is not a decision; the
    // member wants to stay signed in and the clock disagreed. Clicking "sign
    // out" IS a decision, and silently signing them back in would defeat it.
    markSignedInBefore();
    forgetSignedInBefore();
    expect(hasSignedInBefore()).toBe(false);
  });

  test('unreadable storage reports NO hint, never a hint', () => {
    // Fail direction: an unreadable store must not produce an attempt. The
    // safe answer to "has this browser signed in?" when we cannot look is no.
    const spy = jest.spyOn(window.localStorage.__proto__, 'getItem')
      .mockImplementation(() => { throw new Error('SecurityError'); });
    expect(hasSignedInBefore()).toBe(false);
    spy.mockRestore();
  });
});

// ── The grant ───────────────────────────────────────────────────────────────

const googleWith = (behaviour) => ({
  accounts: {
    oauth2: {
      initTokenClient: (cfg) => ({
        requestAccessToken: () => behaviour(cfg),
      }),
    },
  },
});

describe('attemptSilentTokenGrant', () => {
  test('resolves the token on success', async () => {
    const google = googleWith((cfg) =>
      cfg.callback({ access_token: 'tok', expires_in: '3599' }));
    await expect(attemptSilentTokenGrant({ google, clientId: 'cid' }))
      .resolves.toEqual({ access_token: 'tok', expires_in: 3599 });
  });

  test('requests with prompt: "" — the empty string, not "none"', () => {
    // These are different spellings for different GIS surfaces: '' is the token
    // client's "no prompt", 'none' belongs to google.accounts.id. Passing the
    // wrong one PROMPTS, which is the one thing this feature must never do --
    // and it would look like it worked for anyone already signed in.
    let seen = null;
    const google = googleWith((cfg) => { seen = cfg; cfg.callback({}); });
    attemptSilentTokenGrant({ google, clientId: 'cid' });
    expect(seen.prompt).toBe('');
    expect(seen.client_id).toBe('cid');
  });

  test('resolves NULL when the grant fails — never rejects', async () => {
    const google = googleWith((cfg) => cfg.error_callback({ type: 'popup_failed' }));
    await expect(attemptSilentTokenGrant({ google, clientId: 'cid' }))
      .resolves.toBeNull();
  });

  test('resolves NULL on a response with no access token', async () => {
    const google = googleWith((cfg) => cfg.callback({ error: 'consent_required' }));
    await expect(attemptSilentTokenGrant({ google, clientId: 'cid' }))
      .resolves.toBeNull();
  });

  test('resolves NULL when the GIS script has not loaded', async () => {
    await expect(attemptSilentTokenGrant({ google: undefined, clientId: 'cid' }))
      .resolves.toBeNull();
    await expect(attemptSilentTokenGrant({ google: {}, clientId: 'cid' }))
      .resolves.toBeNull();
  });

  test('resolves NULL when there is no client id', async () => {
    const google = googleWith((cfg) => cfg.callback({ access_token: 'tok' }));
    await expect(attemptSilentTokenGrant({ google, clientId: undefined }))
      .resolves.toBeNull();
  });

  test('resolves NULL when GIS throws', async () => {
    const google = { accounts: { oauth2: { initTokenClient: () => {
      throw new Error('boom');
    } } } };
    await expect(attemptSilentTokenGrant({ google, clientId: 'cid' }))
      .resolves.toBeNull();
  });

  test('settles ONCE even if GIS invokes both callbacks', async () => {
    // Belt-and-braces on a real GIS behaviour: some paths fire the error
    // callback after a callback. A second resolve is a no-op in a Promise, but
    // pinning it stops a future refactor moving the write in here.
    const google = googleWith((cfg) => {
      cfg.callback({ access_token: 'first', expires_in: 10 });
      cfg.error_callback({ type: 'late' });
    });
    await expect(attemptSilentTokenGrant({ google, clientId: 'cid' }))
      .resolves.toEqual({ access_token: 'first', expires_in: 10 });
  });

  test('🔴 AC4: a FAILED attempt writes NOTHING to storage', async () => {
    // The regression to fear is a half-write -- a session recorded for a grant
    // that never happened. The cheapest guarantee is that this function has no
    // power to write one at all, so the assertion is over BOTH stores in full
    // rather than over the session keys we happen to remember.
    markSignedInBefore();
    const before = JSON.stringify({
      local: { ...window.localStorage }, session: { ...window.sessionStorage },
    });
    const google = googleWith((cfg) => cfg.error_callback({ type: 'failed' }));
    await attemptSilentTokenGrant({ google, clientId: 'cid' });
    expect(JSON.stringify({
      local: { ...window.localStorage }, session: { ...window.sessionStorage },
    })).toBe(before);
  });

  test('🔴 and a SUCCESSFUL attempt writes nothing either — the caller writes', async () => {
    // The control for the test above. If this function wrote on success, the
    // failure test would still pass, and the two paths would differ in a way
    // no test could see. Writing is the caller's job, once, on success.
    const before = JSON.stringify({
      local: { ...window.localStorage }, session: { ...window.sessionStorage },
    });
    const google = googleWith((cfg) => cfg.callback({ access_token: 't', expires_in: 60 }));
    await attemptSilentTokenGrant({ google, clientId: 'cid' });
    expect(JSON.stringify({
      local: { ...window.localStorage }, session: { ...window.sessionStorage },
    })).toBe(before);
  });
});
