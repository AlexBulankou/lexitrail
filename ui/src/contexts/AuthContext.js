import { createContext, useContext, useState, useCallback } from 'react';
import { googleLogout, useGoogleLogin } from '@react-oauth/google';
import { createUser, getUserByEmail, migrateUser } from '../services/userService';
import { generateUniqueString } from '../utils/stringUtils';
import defaultAvatar from '../styles/assets/default-avatar.svg';
import { loadSession, saveMemberSession, saveGuestSession, clearSession } from '../utils/authStorage';

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
        // Written AFTER the userinfo call succeeds, so a failed exchange leaves
        // no half-session behind. `expires_in` is Google's, in seconds; when it
        // is absent authStorage stores no expiry and refuses the session on the
        // next load -- toward a sign-in prompt, not toward a dead token.
        saveMemberSession(data, tokenResponse.access_token, Number(tokenResponse.expires_in));
  
        try {
          const existingUser = await getUserByEmail(data.email);
          if (!existingUser) {
            await createUser(data.email);
          }
          // Now authenticated as the real member: fold in the guest session's
          // progress (uses the new Google token, so it migrates into this user).
          if (demoEmailToMigrate && demoEmailToMigrate !== data.email) {
            await migrateUser(demoEmailToMigrate);
          }
        } catch (error) {
          console.error('Error handling user in backend:', error);
        }
  
      } catch (error) {
        console.error('Error during Google login:', error);
      }
    },
    onError: (error) => console.log('Login Failed:', error)
  };

  const login = useGoogleLogin(initUser);

  const tryWithoutSignin = useCallback(async () => {
    const uniqueString = generateUniqueString(5);
    const demoEmail = `${uniqueString}@lexitrail.demo`;
    const demoToken = `UNAUTH_USER:${demoEmail}`;
    
    const demoUser = {
      email: demoEmail,
      name: 'Demo User',
      picture: defaultAvatar
    };
    
    setUser(demoUser);
    // Guests stay tab-scoped (#185 AC3). Persisting a throwaway
    // <random>@lexitrail.demo identity would accumulate orphan rows and would
    // hand one visitor's practice data to the next on a shared machine.
    saveGuestSession(demoUser, demoToken);

    try {
      await createUser(demoEmail);
    } catch (error) {
      console.error('Error creating demo user:', error);
    }
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