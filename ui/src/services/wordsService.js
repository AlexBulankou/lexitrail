import { getWords } from '../words.js';

export const fetchWords = () => {
  return getWords()
    .then(loadedWords => loadedWords)
    .catch(error => {
      console.error('Failed to load words:', error);
      throw error;
    });
};
