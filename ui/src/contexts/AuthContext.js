import { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import { googleLogout, useGoogleLogin } from '@react-oauth/google';
import { loadSession, clearSession } from '../utils/authStorage';
import {
  attemptSilentTokenGrant, forgetSignedInBefore, hasSignedInBefore,
} from '../utils/silentReauth';
import { completeGoogleSignIn, startGuestSession } from '../utils/authFlows';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  // lexitrail#185: a member session now survives a browser close, but ONLY
  // while its Google token is still valid. `loadSession` returns null for an
  // expired one and clears it -- restoring an expired session would render the
  // signed-in UI over a token that 401s on every request.
  const [user, setUser] = useState(() => loadSession()?.user ?? null);

  const initUser = {
    onSuccess: async (tokenResponse) => {
      try {
        // Capture any in-progress guest session before it is overwritten, so its
        // practice data can be migrated onto the real account after sign-in.
        let demoEmailToMigrate = null;
        try {
          const priorUser = loadSession()?.user ?? null;
          if (priorUser?.email?.endsWith('@lexitrail.demo')) {
            demoEmailToMigrate = priorUser.email;
          }
        } catch (_) { /* ignore malformed prior session */ }

        const response = await fetch(`https://www.googleapis.com/oauth2/v3/userinfo?access_token=${tokenResponse.access_token}`, {
          method: 'GET',
          headers: {
            Authorization: `Bearer ${tokenResponse.access_token}`,
            Accept: 'application/json'
          }
        });
  
        if (!response.ok) {
          throw new Error('Failed to retrieve user info from Google');
        }
  
        const data = await response.json();
        setUser(data);
        // The session write, GA4 events and backend user-creation/migrate
        // calls all live in completeGoogleSignIn now (lexitrail#195) --
        // same ordering, same try/catch, this call site is unchanged in
        // behavior from the inline version it replaces.
        await completeGoogleSignIn(data, tokenResponse, { demoEmailToMigrate });

      } catch (error) {
        console.error('Error during Google login:', error);
      }
    },
    onError: (error) => console.log('Login Failed:', error)
  };

  const login = useGoogleLogin(initUser);

  // lexitrail#199: a member returning the NEXT DAY has a cleared session (their
  // ~1h implicit-flow token expired and `loadSession` refused it), but has not
  // signed out. Try to re-obtain a token with no UI before rendering them a
  // signed-out page.
  //
  // 🔴 Gated on `hasSignedInBefore()`, NOT on "no user": a first-time visitor
  // and a guest must see no prompt, no error and no change from today (#199
  // AC2/AC3). The hint is written only by `completeGoogleSignIn`, which a guest
  // never reaches, so AC3 holds by construction rather than by a guard here.
  const silentTried = useRef(false);
  useEffect(() => {
    // Once per mount. StrictMode double-invokes effects in development, and a
    // second token request would be a second popup-less grant attempt against
    // Google for no reason.
    if (silentTried.current || user || !hasSignedInBefore()) return;
    silentTried.current = true;
    let cancelled = false;
    (async () => {
      const grant = await attemptSilentTokenGrant({
        google: window.google,
        clientId: window.config?.GOOGLE_CLIENT_ID,
      });
      // `null` is the ordinary outcome, not a fault: consent revoked, several
      // signed-in accounts, third-party cookies blocked. Fall through to the
      // signed-out page exactly as today, silently.
      if (!grant || cancelled) return;
      try {
        const response = await fetch(
          `https://www.googleapis.com/oauth2/v3/userinfo?access_token=${grant.access_token}`,
          { method: 'GET', headers: {
            Authorization: `Bearer ${grant.access_token}`, Accept: 'application/json' } });
        if (!response.ok) return;   // a token we cannot identify is not a session
        const data = await response.json();
        if (cancelled) return;
        setUser(data);
        // No `demoEmailToMigrate`: this path runs only when there is no current
        // session at all, so there is no in-progress guest to migrate. Passing
        // one would migrate whatever stale guest row happened to be lying about.
        await completeGoogleSignIn(data, grant, { method: 'google_silent' });
      } catch (_) {
        // Same swallow as the clicked path. A failed silent attempt must not
        // surface an error to a user who did not ask for anything.
      }
    })();
    return () => { cancelled = true; };
  }, [user]);

  const tryWithoutSignin = useCallback(async () => {
    // lexitrail#195: startGuestSession does the storage write + GA4 event
    // synchronously (same as the inline code it replaces) and returns the
    // in-flight backend createUser call rather than awaiting it internally,
    // so setUser below still fires immediately -- not delayed by the network,
    // exactly as before.
    const { demoUser, backendCreate } = startGuestSession();
    setUser(demoUser);
    await backendCreate;
  }, []);

  const logOut = useCallback(() => {
    googleLogout();
    setUser(null);
    clearSession();
    // lexitrail#199: an EXPLICIT sign-out is a decision, unlike an expired
    // token. Forgetting the hint is what stops the next load silently signing
    // this member back in and undoing the thing they just asked for.
    forgetSignedInBefore();
  }, []);

  return (
    <AuthContext.Provider value={{ user, login, logOut, tryWithoutSignin }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}; 