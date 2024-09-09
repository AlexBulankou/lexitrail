import { useState, useEffect } from 'react';
import { googleLogout, useGoogleLogin } from '@react-oauth/google';

export const useAuth = () => {
  const [user, setUser] = useState(() => {
    // Retrieve the user from localStorage if available
    const storedUser = localStorage.getItem('user');
    return storedUser ? JSON.parse(storedUser) : null;
  });

  const initUser = {
    onSuccess: (tokenResponse) => {
      fetch(`https://www.googleapis.com/oauth2/v3/userinfo?access_token=${tokenResponse.access_token}`, {
        method: 'GET',
        headers: {
          Authorization: `Bearer ${tokenResponse.access_token}`,
          Accept: 'application/json'
        }
      })
        .then((response) => {
          if (!response.ok) {
            throw new Error('Network response was not ok');
          }
          return response.json();
        })
        .then((data) => {
          setUser(data);
          // Store the user data in localStorage
          localStorage.setItem('user', JSON.stringify(data));
        })
        .catch((error) => console.log(error));
    },
    onError: (error) => console.log('Login Failed:', error)
  };

  const login = useGoogleLogin(initUser);

  const logOut = () => {
    googleLogout();
    setUser(null);
    localStorage.removeItem('user'); // Remove the user data from localStorage
  };

  return { user, login, logOut };
};
