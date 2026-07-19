import { getData } from './apiService';

// SUG-2: cache hints per user+word for the session so repeat views (revisits,
// toggling hints off/on) don't re-issue a generate/fetch request.
const hintCache = new Map();
const cacheKey = (userId, wordId) => `${userId}:${wordId}`;

// Fetch hint for a given user and word
export const getHint = async (userId, wordId) => {
  const key = cacheKey(userId, wordId);
  if (hintCache.has(key)) {
    return hintCache.get(key);
  }
  const response = await getData(`/hint/generate_hint?user_id=${userId}&word_id=${wordId}`);
  hintCache.set(key, response);
  return response;
};

// Regenerate hint for a given user and word (bypasses + refreshes the cache)
export const regenerateHint = async (userId, wordId) => {
  const response = await getData(`/hint/generate_hint?user_id=${userId}&word_id=${wordId}&force_regenerate=true`);
  hintCache.set(cacheKey(userId, wordId), response);
  return response;
};
