/**
 * issue-256 — AuthContext's WIRING, mounted.
 *
 * Two race/wiring defects landed in this file (#185/#200 and #199/#254) and both
 * were caught by hc2@ reading the diff. Reading worked twice and is not a
 * mechanism; a pure-function test cannot reach either, because the defect is in
 * how two async paths interleave rather than in any value one of them computes.
 *
 * #254's fix is a `signInSettled` useRef checkpoint that the clicked path and the
 * silent path both pass through, each re-checking it AFTER its own await — the
 * profile fetch being the widest part of the race. This pins that the checkpoint
 * actually holds when both paths complete.
 *
 * AC2 is asserted on `trackEvent('login')` itself, not on a proxy: the real
 * `completeGoogleSignIn` runs and it is the one place that fires the event.
 */
import { render, screen, waitFor, act } from '@testing-library/react';
import { AuthProvider, useAuth } from './AuthContext';

let capturedOnSuccess = null;

jest.mock('@react-oauth/google', () => ({
  googleLogout: jest.fn(),
  useGoogleLogin: (opts) => { capturedOnSuccess = opts.onSuccess; return jest.fn(); },
}));

const silentGrant = { access_token: 'silent-tok', expires_in: 3600 };
let grantResolver;
jest.mock('../utils/silentReauth', () => ({
  hasSignedInBefore: () => true,
  markSignedInBefore: jest.fn(),
  forgetSignedInBefore: jest.fn(),
  attemptSilentTokenGrant: () => new Promise((r) => { grantResolver = r; }),
}));

jest.mock('../utils/authStorage', () => ({
  loadSession: () => null,
  clearSession: jest.fn(),
  saveMemberSession: jest.fn(),
  saveGuestSession: jest.fn(),
}));

jest.mock('../utils/analytics', () => ({ trackEvent: jest.fn() }));
jest.mock('../services/userService', () => ({
  getUserByEmail: jest.fn().mockResolvedValue({ id: 1 }),
  createUser: jest.fn().mockResolvedValue({}),
  migrateUser: jest.fn().mockResolvedValue({}),
}));
jest.mock('../utils/perfMark', () => ({ markOnce: jest.fn(), AUTH_SETTLED_MARK: 'auth' }));

const { trackEvent } = require('../utils/analytics');

const Probe = () => { const { user } = useAuth(); return <div>{user ? user.email : 'anon'}</div>; };
const mountProvider = () => render(<AuthProvider><Probe /></AuthProvider>);

const loginEvents = () => trackEvent.mock.calls.filter((c) => c[0] === 'login');

beforeEach(() => {
  jest.clearAllMocks();
  capturedOnSuccess = null;
  grantResolver = null;
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ email: 'member@example.com', name: 'Member' }),
  });
});

// ---------------------------------------------------------------------------
// AC2 — the race. Both paths complete; the event must fire exactly ONCE.
// ---------------------------------------------------------------------------

test('a silent grant and a clicked sign-in both completing fire login exactly ONCE', async () => {
  mountProvider();
  await waitFor(() => expect(capturedOnSuccess).toBeInstanceOf(Function));

  // Both paths in flight, then both allowed to finish — the shape #254 describes.
  await act(async () => {
    const clicked = capturedOnSuccess({ access_token: 'clicked-tok', expires_in: 3600 });
    grantResolver(silentGrant);
    await clicked;
  });

  await waitFor(() => expect(screen.getByText('member@example.com')).toBeInTheDocument());
  await waitFor(() => expect(loginEvents().length).toBeGreaterThan(0));

  expect(loginEvents()).toHaveLength(1);
});

// ---------------------------------------------------------------------------
// AC3 — the control. Without it, AC2 is satisfied by a mock that never fires.
// ---------------------------------------------------------------------------

test('CONTROL: only the CLICKED path completing still fires login exactly once', async () => {
  mountProvider();
  await waitFor(() => expect(capturedOnSuccess).toBeInstanceOf(Function));

  await act(async () => {
    grantResolver(null);                  // silent path declines, the ordinary outcome
    await capturedOnSuccess({ access_token: 'clicked-tok', expires_in: 3600 });
  });

  await waitFor(() => expect(loginEvents()).toHaveLength(1));
  expect(loginEvents()[0][1]).toMatchObject({ method: 'google' });
});

test('CONTROL: only the SILENT path completing fires login exactly once, as google_silent', async () => {
  mountProvider();
  await waitFor(() => expect(capturedOnSuccess).toBeInstanceOf(Function));

  await act(async () => { grantResolver(silentGrant); });

  await waitFor(() => expect(loginEvents()).toHaveLength(1));
  expect(loginEvents()[0][1]).toMatchObject({ method: 'google_silent' });
});
