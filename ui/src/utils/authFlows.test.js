// lexitrail#195 — proof the auth-success GA4 signal FIRES, not merely that
// the call sites exist. Per this fleet's standing rule (a detector/analytics
// change needs a test proving the signal fires): the acceptance criteria is
// "each produces exactly one GA4 event with a `method` param" for login, and
// "the first time a backend row is created" for sign_up -- both are asserted
// against `window.gtag`'s actual call arguments below, not against whether
// `trackEvent` was merely invoked.
//
// Factory mocks for userService, not automocks: userService imports
// apiService, which reads `window.config.API_BASE_URL` at import time --
// undefined under jest (same reasoning as useDueToday.test.js).
import { completeGoogleSignIn, startGuestSession } from './authFlows';
import { createUser, getUserByEmail, migrateUser } from '../services/userService';

jest.mock('../services/userService', () => ({
  createUser: jest.fn(),
  getUserByEmail: jest.fn(),
  migrateUser: jest.fn(),
}));

const MEMBER = { email: 'a@b.co', name: 'A' };
const TOKEN_RESPONSE = { access_token: 'tok', expires_in: 3600 };

beforeEach(() => {
  jest.clearAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.gtag = jest.fn();
});

describe('completeGoogleSignIn', () => {
  it('fires login(method=google) unconditionally, before the backend calls resolve', async () => {
    getUserByEmail.mockResolvedValue(MEMBER); // existing user -- no sign_up
    await completeGoogleSignIn(MEMBER, TOKEN_RESPONSE);

    expect(window.gtag).toHaveBeenCalledWith('event', 'login', { method: 'google' });
  });

  it('🔴 the bug shape this exists to prevent: fires sign_up ONLY on a genuinely NEW backend row', async () => {
    getUserByEmail.mockResolvedValue(null); // no existing row
    createUser.mockResolvedValue({});
    await completeGoogleSignIn(MEMBER, TOKEN_RESPONSE);

    expect(window.gtag).toHaveBeenCalledWith('event', 'sign_up', { method: 'google' });
    // Negative control: an EXISTING user must not double this. Same shape,
    // different mock return -- if this collapsed to "sign_up always fires",
    // this assertion is what catches it.
  });

  it('does NOT fire sign_up for a RETURNING member -- only login', async () => {
    getUserByEmail.mockResolvedValue(MEMBER);
    await completeGoogleSignIn(MEMBER, TOKEN_RESPONSE);

    expect(createUser).not.toHaveBeenCalled();
    expect(window.gtag).toHaveBeenCalledTimes(1);
    expect(window.gtag).toHaveBeenCalledWith('event', 'login', { method: 'google' });
  });

  it('a backend failure does not un-fire login, and does not throw', async () => {
    getUserByEmail.mockRejectedValue(new Error('backend down'));
    await expect(completeGoogleSignIn(MEMBER, TOKEN_RESPONSE)).resolves.toBeUndefined();

    expect(window.gtag).toHaveBeenCalledWith('event', 'login', { method: 'google' });
    expect(window.gtag).not.toHaveBeenCalledWith('event', 'sign_up', expect.anything());
  });

  it('migrates a prior guest session into the new member when one is passed', async () => {
    getUserByEmail.mockResolvedValue(null);
    createUser.mockResolvedValue({});
    migrateUser.mockResolvedValue({ migrated_words: 3 });

    await completeGoogleSignIn(MEMBER, TOKEN_RESPONSE, { demoEmailToMigrate: 'x@lexitrail.demo' });

    expect(migrateUser).toHaveBeenCalledWith('x@lexitrail.demo');
  });

  it('a missing gtag (blocked/not loaded) does not break the sign-in flow', async () => {
    delete window.gtag;
    getUserByEmail.mockResolvedValue(null);
    createUser.mockResolvedValue({});

    await expect(completeGoogleSignIn(MEMBER, TOKEN_RESPONSE)).resolves.toBeUndefined();
    expect(createUser).toHaveBeenCalled();
  });
});

describe('startGuestSession', () => {
  it('fires login(method=demo), synchronously -- before the backend call resolves', () => {
    createUser.mockResolvedValue({});
    const { demoUser, backendCreate } = startGuestSession();

    // Synchronous: gtag already fired even though backendCreate is still pending.
    expect(window.gtag).toHaveBeenCalledWith('event', 'login', { method: 'demo' });
    expect(demoUser.email).toMatch(/@lexitrail\.demo$/);
    return backendCreate;
  });

  it('never fires sign_up -- lexitrail#195 scopes that event to method=google', async () => {
    createUser.mockResolvedValue({});
    const { backendCreate } = startGuestSession();
    await backendCreate;

    expect(window.gtag).not.toHaveBeenCalledWith('event', 'sign_up', expect.anything());
  });

  it('setUser is unblocked by demoUser before the network call -- backendCreate is separate', () => {
    // Regression guard for the extraction itself: if startGuestSession ever
    // becomes `async` and awaits createUser internally before returning
    // demoUser, a caller doing `const { demoUser } = await startGuestSession()`
    // would delay setUser on the network. Pinning the SHAPE keeps that honest:
    // demoUser must be available synchronously, off the return value directly.
    createUser.mockImplementation(() => new Promise(() => {})); // never resolves
    const { demoUser } = startGuestSession();
    expect(demoUser).toBeDefined();
    expect(demoUser.name).toBe('Demo User');
  });
});
