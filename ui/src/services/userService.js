import { getData, postData, putData, deleteData } from './apiService';

// Create a new user
export const createUser = async (email) => {
  const data = { email };
  return await postData('/users', data);
};

// Get all users
export const getAllUsers = async () => {
  return await getData('/users');
};

// Get a user by email
export const getUserByEmail = async (email) => {
  return await getData(`/users/${email}`);
};

// Update a user's email
export const updateUserEmail = async (email, newEmail) => {
  const data = { email: newEmail };
  return await putData(`/users/${email}`, data);
};

// Delete a user
export const deleteUser = async (email) => {
  return await deleteData(`/users/${email}`);
};

// Fetch userwords for a given user and wordset
export const getUserWordsByWordset = async (userId, wordsetId) => {
  return await getData(`/userwords/query?user_id=${userId}&wordset_id=${wordsetId}`);
};

// Update recall state for a word
export const updateUserWordRecall = async (userId, wordId, recallState, recall, isIncluded) => {
  const data = { recall_state: recallState, recall, is_included: isIncluded };
  return await putData(`/userwords/${userId}/${wordId}/recall`, data);
};
