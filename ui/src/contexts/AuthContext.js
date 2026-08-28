import { createContext, useContext, useState, useCallback } from 'react';
import { googleLogout, useGoogleLogin } from '@react-oauth/google';
import { loadSession, clearSession } from '../utils/authStorage';
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