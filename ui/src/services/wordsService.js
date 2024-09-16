//import { getWords } from '../words.js';

// src/services/wordsService.js
import { getData } from './apiService';

/*
export const fetchWords = () => {
  return getWords()
    .then(loadedWords => loadedWords)
    .catch(error => {
      console.error('Failed to load words:', error);
      throw error;
    });
};
*/

// Fetch all wordsets
export const getWordsets = async () => {
  return await getData('/wordsets');
};

// Fetch words for a given wordset
export const getWordsByWordset = async (wordsetId) => {
  return await getData(`/wordsets/${wordsetId}/words`);
};


