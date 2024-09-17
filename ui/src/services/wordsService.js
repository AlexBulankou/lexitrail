import { getData } from './apiService';

// Fetch all wordsets
export const getWordsets = async () => {
  return await getData('/wordsets');
};

// Fetch words for a given wordset
export const getWordsByWordset = async (wordsetId) => {
  return await getData(`/wordsets/${wordsetId}/words`);
};


