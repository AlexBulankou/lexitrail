import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:5001'; // Base URL for Flask backend

// Get the access token from localStorage
const getAccessToken = () => localStorage.getItem('access_token');

// Function to handle any GET request
export const getData = async (endpoint) => {
  try {
    console.log(`Requesting: ${API_BASE_URL}${endpoint}`);
    const accessToken = getAccessToken(); // Use the access token
    const response = await axios.get(`${API_BASE_URL}${endpoint}`, {
      headers: {
        Authorization: `Bearer ${accessToken}`, // Use access token for backend authentication
      },
    });
    return response.data;
  } catch (error) {
    // Handle 404 by returning null, which indicates the resource does not exist
    if (error.response && error.response.status === 404) {
      console.error(`GET ${endpoint} failed: 404 Not Found`);
      return null;
    } else {
      console.error(`GET ${endpoint} failed:`, error);
      throw error; // Re-throw the error for other types of failures
    }
  }
};

// Function to handle any POST request
export const postData = async (endpoint, data) => {
  try {
    const accessToken = getAccessToken(); // Use the access token
    const response = await axios.post(`${API_BASE_URL}${endpoint}`, data, {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    });
    return response.data;
  } catch (error) {
    console.error(`POST ${endpoint} failed:`, error);
    throw error;
  }
};

// Function to handle any PUT request
export const putData = async (endpoint, data) => {
  try {
    const accessToken = getAccessToken(); // Use the access token
    const response = await axios.put(`${API_BASE_URL}${endpoint}`, data, {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    });
    return response.data;
  } catch (error) {
    console.error(`PUT ${endpoint} failed:`, error);
    throw error;
  }
};

// Function to handle any DELETE request
export const deleteData = async (endpoint) => {
  try {
    const accessToken = getAccessToken(); // Use the access token
    const response = await axios.delete(`${API_BASE_URL}${endpoint}`, {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    });
    return response.data;
  } catch (error) {
    console.error(`DELETE ${endpoint} failed:`, error);
    throw error;
  }
};
