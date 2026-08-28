// lexitrail#195: the post-auth work (backend user creation + GA4 events),
// split out of AuthContext so it's testable without @testing-library/react
// -- this repo has none installed (see useDueToday.js's docstring for why:
// no Cloud Build trigger to run it in). AuthContext calls these and awaits
// them at the exact point the original inline code did, so this is a pure
// extraction -- no change in ordering or error handling, just an importable
// seam for the part worth pinning: does the right GA4 event fire, exactly
// once, with the right method param.
import { createUser, getUserByEmail, migrateUser } from '../services/userService';
import { generateUniqueString } from './stringUtils';
import defaultAvatar from '../styles/assets/default-avatar.svg';
import { saveMemberSession, saveGuestSession } from './authStorage';
import { trackEvent } from './analytics';

// Runs after Google userinfo has already succeeded and `setUser` has already
// fired (both happen in AuthContext, synchronously, before this is called).
// Mirrors the original onSuccess body exactly: same session write, same
// try/catch around the backend calls, so a backend or migrate failure is
// swallowed here exactly as it always was -- this function never throws.
export const completeGoogleSignIn = async (data, tokenResponse, { demoEmailToMigrate } = {}) => {
  saveMemberSession(data, tokenResponse.access_token, Number(tokenResponse.expires_in));
  // Fires on AUTH success (storage write), not on the backend calls below --
  // those are best-effort and independently try/caught, so a backend hiccup
  // must not make a real sign-in read as unmeasured.
  trackEvent('login', { method: 'google' });

  try {
    const existingUser = await getUserByEmail(data.email);
    if (!existingUser) {
      await createUser(data.email);
      // Fires only the first time this email gets a backend row --
      // `existingUser` is the funnel's "new account created" signal, not
      // just "auth succeeded" (the `login` event above already covers that).
      trackEvent('sign_up', { method: 'google' });
    }
    // Now authenticated as the real member: fold in the guest session's
    // progress (uses the new Google token, so it migrates into this user).
    if (demoEmailToMigrate && demoEmailToMigrate !== data.email) {
      await migrateUser(demoEmailToMigrate);
    }
  } catch (error) {
    console.error('Error handling user in backend:', error);
  }
};

// The demo/guest identity is always freshly generated, so unlike Google
// there's no existing-vs-new branch -- `login` is the whole signal. No
// `sign_up` here: lexitrail#195's Proposal scopes that event to
// method=google, since a demo row isn't the acquisition signal the funnel
// is measuring.
//
// Returns `{ demoUser, backendCreate }` rather than awaiting the backend
// call itself: the original code called `setUser(demoUser)` synchronously,
// immediately, BEFORE awaiting `createUser` -- the guest sees themselves
// signed in without waiting on the network. Awaiting inside this function
// would delay that call site's `setUser` by however long `createUser` takes
// (up to the API layer's 20s timeout, lexitrail#52). `backendCreate` lets
// the caller (or a test) still await completion without changing that.
export const startGuestSession = () => {
  const uniqueString = generateUniqueString(5);
  const demoEmail = `${uniqueString}@lexitrail.demo`;
  const demoToken = `UNAUTH_USER:${demoEmail}`;
  const demoUser = { email: demoEmail, name: 'Demo User', picture: defaultAvatar };

  // Guests stay tab-scoped (#185 AC3). Persisting a throwaway
  // <random>@lexitrail.demo identity would accumulate orphan rows and would
  // hand one visitor's practice data to the next on a shared machine.
  saveGuestSession(demoUser, demoToken);
  trackEvent('login', { method: 'demo' });

  const backendCreate = (async () => {
    try {
      await createUser(demoEmail);
    } catch (error) {
      console.error('Error creating demo user:', error);
    }
  })();

  return { demoUser, backendCreate };
};
