import { useState } from 'react';
import { googleLogout, useGoogleLogin } from '@react-oauth/google';
import { createUser, getUserByEmail } from '../services/userService'; // Import both create and get functions

export const useAuth = () => {
  const [user, setUser] = useState(() => {
    const storedUser = localStorage.getItem('user');
    return storedUser ? JSON.parse(storedUser) : null;
  });


  const initUser = {
    onSuccess: async (tokenResponse) => {
      try {
        // Fetch user info from Google
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
          // Check if the user exists in the backend
          const existingUser = await getUserByEmail(data.email);
  
          if (existingUser) {
            // User exists, retrieve any additional information if needed
            console.log("User already exists, retrieve additional information");
          }
        } catch (error) {
          // This block handles errors in the getUserByEmail call, including 404s
          if (error.response && error.response.status === 404) {
            // If user doesn't exist, create the user
            console.log(`User ${data.email} not found in backend, creating user`);
            await createUser(data.email);
          } else {
            // Handle other errors (e.g., network issues)
            console.error('Error fetching user from backend:', error);
          }
        }
  
      } catch (error) {
        // Handle errors with fetching user info from Google
        console.error('Error during Google login:', error);
      }
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
