import { useState } from 'react';
import { googleLogout, useGoogleLogin } from '@react-oauth/google';
import { createUser, getUserByEmail } from '../services/userService';

export const useAuth = () => {
  const [user, setUser] = useState(() => {
    const storedUser = localStorage.getItem('user');
    return storedUser ? JSON.parse(storedUser) : null;
  });


  const initUser = {
    onSuccess: async (tokenResponse) => {
      try {
        // Store the access_token in localStorage
        localStorage.setItem('access_token', tokenResponse.access_token);
  
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
        localStorage.setItem('user', JSON.stringify(data));
  
        try {
          const existingUser = await getUserByEmail(data.email);
          if (!existingUser) {
            // Create user if they don't exist in the backend
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

  const logOut = () => {
    googleLogout();
    setUser(null);
    localStorage.removeItem('user');
    localStorage.removeItem('access_token');
  };

  return { user, login, logOut };
};
