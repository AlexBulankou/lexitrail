'use strict';
/**
 * Session generator / credential manager for authenticated sweeps.
 *
 * Secured logic (practice, test, due-today, excluded, completed) sits behind
 * `PrivateRoute`, so a harness that only loads `/` can never see most of the app.
 * This module gets us past that wall WITHOUT handling a real credential.
 *
 * PRIMARY PATH -- guest session, by clicking the real button.
 * `tryWithoutSignin()` (ui/src/contexts/AuthContext.js) mints a throwaway
 * `<random5>@lexitrail.demo` identity and stores `access_token =
 * "UNAUTH_USER:<email>"`. The Flask backend (backend/app/auth.py) accepts
 * `UNAUTH_USER:` tokens ONLY for the lexitrail.demo domain, so a guest can never
 * impersonate a member. This is a first-class product path, not a test backdoor.
 *
 * We CLICK the button rather than seeding storage directly, because seeding
 * reproduces what we *believe* the app stores -- and a bug in that belief (or a
 * change like lexitrail#348 moving guests from sessionStorage to localStorage)
 * would give us a harness that authenticates against a site the users don't have.
 * Clicking exercises the real flow, so it breaks when the real flow breaks.
 * `seedGuestSession` exists only as a documented fallback for when the button
 * itself is the thing under test.
 *
 * NEVER a real Google sign-in. Guardrail from docs/itp-playwright-usability.md 6:
 * no real account, no password typed, no token logged or committed. For member-only
 * surfaces, point UIBUG_STORAGE_STATE at a Playwright storageState JSON minted
 * out-of-band by a human; this module will load it and never print its contents.
 */

const fs = require('fs');

const GUEST_DOMAIN = '@lexitrail.demo';

/** Redact anything token-shaped so a thrown error or a log line can never carry one. */
const redact = (s) =>
  String(s).replace(/UNAUTH_USER:[^"'\s]+/g, 'UNAUTH_USER:<redacted>');

/**
 * Enter a guest session by clicking the product's own "Try without signing in".
 * Returns { ok, how, email } -- `email` is the demo identity (safe: it is not a
 * credential and carries no personal data), never the token.
 */
async function enterGuestSession(page, { timeout = 15000 } = {}) {
  // Two live entry points: the nav "Try" button and the PrivateRoute login card.
  // Prefer whichever is actually present so this works from any route.
  const candidates = [
    page.getByRole('button', { name: /try without signing in/i }),
    page.getByRole('button', { name: /^try$/i }),
    page.locator('button', { hasText: /try without signing in/i }),
  ];

  for (const loc of candidates) {
    const btn = loc.first();
    if (await btn.isVisible().catch(() => false)) {
      await btn.click();
      // The app re-renders in place; wait for the session to actually exist
      // rather than for a navigation that never happens.
      const ok = await page
        .waitForFunction(
          () => {
            const read = (s) => {
              try { return s.getItem('access_token'); } catch (_) { return null; }
            };
            return Boolean(read(localStorage) || read(sessionStorage));
          },
          null,
          { timeout }
        )
        .then(() => true)
        .catch(() => false);

      if (ok) {
        const email = await page.evaluate(() => {
          const read = (s) => {
            try { return JSON.parse(s.getItem('user') || 'null'); } catch (_) { return null; }
          };
          return (read(localStorage) || read(sessionStorage) || {}).email || null;
        });
        return { ok: true, how: 'clicked', email };
      }
      return { ok: false, how: 'clicked', email: null };
    }
  }
  return { ok: false, how: 'no-button-found', email: null };
}

/**
 * Fallback only. Mints a guest identity directly into storage, mirroring
 * startGuestSession() in ui/src/utils/authFlows.js. Use when the login card
 * itself is the thing under test -- otherwise prefer enterGuestSession, which
 * fails honestly when the real flow is broken.
 */
async function seedGuestSession(page) {
  const rnd = Math.random().toString(36).slice(2, 7);
  const email = `${rnd}${GUEST_DOMAIN}`;
  await page.addInitScript(
    ({ email }) => {
      try {
        localStorage.setItem('access_token', `UNAUTH_USER:${email}`);
        localStorage.setItem(
          'user',
          JSON.stringify({ email, name: 'Demo User', picture: '' })
        );
      } catch (_) { /* private mode -- caller sees ok:false via the wall */ }
    },
    { email }
  );
  return { ok: true, how: 'seeded', email };
}

/**
 * Member session for surfaces a guest cannot reach. Reads a storageState JSON
 * minted out-of-band; there is no password path here on purpose.
 */
function memberStorageState() {
  const p = process.env.UIBUG_STORAGE_STATE;
  if (!p) return undefined;
  if (!fs.existsSync(p)) {
    throw new Error(`[uibug] UIBUG_STORAGE_STATE points at a missing file: ${p}`);
  }
  return p; // handed to browser.newContext({ storageState }); contents never logged
}

/** Dismiss the onboarding overlay so it does not sit on top of every screenshot. */
async function dismissOnboarding(page) {
  const closers = [
    page.getByRole('button', { name: /got it|start|close|dismiss|ok/i }),
    page.locator('.onboarding-overlay button'),
    page.locator('[class*="onboarding"] button'),
  ];
  for (const loc of closers) {
    const btn = loc.first();
    if (await btn.isVisible().catch(() => false)) {
      await btn.click().catch(() => {});
      await page.waitForTimeout(300);
      return true;
    }
  }
  return false;
}

module.exports = {
  enterGuestSession,
  seedGuestSession,
  memberStorageState,
  dismissOnboarding,
  redact,
  GUEST_DOMAIN,
};
