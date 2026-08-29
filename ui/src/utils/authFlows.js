// lexitrail#195: the post-auth work (backend user creation + GA4 events),
// split out of AuthContext so it's testable without @testing-library/react
// -- this repo has none installed (see useDueToday.js's docstring for why:
// no Cloud Build trigger to run it in). Error handling is unchanged from the
// inline code both functions replace.
//
// completeGoogleSignIn's ordering IS identical: AuthContext still calls
// setUser(data) first, then awaits this, exactly where the inline code did.
//
// startGuestSession's is NOT (lexitrail#225 review, hcl@ Q2 -- the original
// wording here claimed "no change in ordering" and that was wrong for this
// half). Before: setUser(demoUser) -> saveGuestSession -> await createUser.
// Now: saveGuestSession + trackEvent happen INSIDE this function, before the
// call site's setUser. Believed harmless-to-better (a component reading
// session storage off the setUser re-render now finds it already written),
// but it is a real reordering and the old comment described it as none --
// exactly the kind of claim a later bisect would trust and shouldn't have to.
import { createUser, getUserByEmail, migrateUser } from '../services/userService';
import { generateUniqueString } from './stringUtils';
import defaultAvatar from '../styles/assets/default-avatar.svg';
import { saveMemberSession, saveGuestSession } from './authStorage';
import { markSignedInBefore } from './silentReauth';
import { trackEvent } from './analytics';

// Runs after Google userinfo has already succeeded and `setUser` has already
// fired (both happen in AuthContext, synchronously, before this is called).
// Mirrors the original onSuccess body exactly: same session write, same
// try/catch around the backend calls, so a backend or migrate failure is
// swallowed here exactly as it always was -- this function never throws.
export const completeGoogleSignIn = async (data, tokenResponse, { demoEmailToMigrate, method = 'google' } = {}) => {
  saveMemberSession(data, tokenResponse.access_token, Number(tokenResponse.expires_in));
  // lexitrail#199: record that THIS BROWSER has completed a real sign-in, so a
  // later load can attempt a silent token grant once this token expires. Set
  // here rather than in AuthContext because this is the one place that runs on
  // every successful member sign-in and nowhere else -- a guest never reaches
  // it, which is #199 AC3 by construction rather than by a guard.
  markSignedInBefore();
  // Fires on AUTH success (storage write), not on the backend calls below --
  // those are best-effort and independently try/caught, so a backend hiccup
  // must not make a real sign-in read as unmeasured.
  //
  // #199: `method` distinguishes a clicked sign-in from a silent re-auth. They
  // are both logins and both belong in this event, but #199's whole success
  // measure is that clicked sign-ins become RARER -- folding silent ones in
  // under the same label would hide exactly the movement it exists to show.
  trackEvent('login', { method });

  try {
    const existingUser = await getUserByEmail(data.email);
    if (!existingUser) {
      await createUser(data.email);
      // Fires only the first time this email gets a backend row --
      // `existingUser` is the funnel's "new account created" signal, not
      // just "auth succeeded" (the `login` event above already covers that).
      //
      // lexitrail#225 review (hcl@, Q1): this makes sign_up a function of
      // TABLE STATE, not of an event that happened once. If `users` is ever
      // recreated (lexitrail#222 -- the retired terraform root's unconditional
      // DROP TABLE), every returning member re-triggers this branch on their
      // next sign-in and sign_up fires again for accounts that are months
      // old, silently inflating the acquisition number this event exists to
      // make trustworthy. Low reachability today (that root isn't applied),
      // but worth knowing here: a future restore/migration's sign_up spike
      // should read as "the table was recreated," not as growth.
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
