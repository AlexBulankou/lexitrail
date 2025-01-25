import { createContext, useContext, useState, useCallback } from 'react';
import { googleLogout, useGoogleLogin } from '@react-oauth/google';
import { createUser, getUserByEmail } from '../services/userService';
import { generateUniqueString } from '../utils/stringUtils';
import defaultAvatar from '../styles/assets/default-avatar.svg';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(() => {
    const storedUser = sessionStorage.getItem('user');
    return storedUser ? JSON.parse(storedUser) : null;
  });

  const initUser = {
    onSuccess: async (tokenResponse) => {
      try {
        sessionStorage.setItem('access_token', tokenResponse.access_token);
        
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
        sessionStorage.setItem('user', JSON.stringify(data));
  
        try {
          const existingUser = await getUserByEmail(data.email);
          if (!existingUser) {
            await createUser(data.email);
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
    sessionStorage.setItem('user', JSON.stringify(demoUser));
    sessionStorage.setItem('access_token', demoToken);

    try {
      await createUser(demoEmail);
    } catch (error) {
      console.error('Error creating demo user:', error);
    }
  }, []);

  const logOut = useCallback(() => {
    googleLogout();
    setUser(null);
    sessionStorage.removeItem('user');
    sessionStorage.removeItem('access_token');
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