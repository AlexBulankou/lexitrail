import { useState, useEffect, useCallback } from 'react';
import { getWordsByWordset } from '../services/wordsService';
import { getUserWordsByWordset, updateUserWordRecall } from '../services/userService';
import { formatDistanceToNow } from 'date-fns';

// Function to abstract recall state logic
const updateRecallState = (currentRecallState, isCorrect) => {
  if (isCorrect) {
    // Decrement recall state if correct, but never below 0
    return Math.max(0, currentRecallState - 1);
  } else {
    // Increment recall state if incorrect
    return currentRecallState + 1;
  }
};

export const useWordsetLoader = (wordsetId, userId) => {
  const [toShow, setToShow] = useState([]);
  const [loading, setLoading] = useState(true);
  const [firstTimeCorrect, setFirstTimeCorrect] = useState([]);
  const [incorrectAttempts, setIncorrectAttempts] = useState({});
  const [correctlyMemorized, setCorrectlyMemorized] = useState(new Set());
  const [timeElapsed, setTimeElapsed] = useState(0);

  const loadWordsForWordset = useCallback(async () => {
    setLoading(true);
    try {
      const response = await getWordsByWordset(wordsetId);
      const loadedWords = response.data;

      // Fetch userword metadata (recall history, exclusion state) for each word
      const userwordsResponse = await getUserWordsByWordset(userId, wordsetId);
      const userWordsMetadata = userwordsResponse.data;

      const convertedWords = loadedWords.map((word) => {
        const userWord = userWordsMetadata.find(uw => uw.word_id === word.word_id);
        return {
          word: word.word,
          meaning: `${word.def1}\n${word.def2}`,
          word_id: word.word_id,
          wordset_id: word.wordset_id,
          is_included: userWord ? userWord.is_included : true,
          recall_state: userWord ? userWord.recall_state : 0,
          recall_history: userWord ? userWord.recall_histories.map(hist => ({
            ...hist,
            recall_time: formatDistanceToNow(new Date(hist.recall_time), { addSuffix: true })
          })) : [],
        };
      });

      setToShow(convertedWords);
      setLoading(false);
    } catch (error) {
      setLoading(false);
      console.error('Error loading words or userword metadata:', error);
    }
  }, [wordsetId, userId]);

  // Call loadWordsForWordset when wordsetId or userId changes
  useEffect(() => {
    if (wordsetId && userId) {
      loadWordsForWordset();
    }
  }, [wordsetId, userId, loadWordsForWordset]);

  // Handle exclusion/inclusion
  const toggleExclusion = async (index) => {
    const currentWord = toShow[index];
    const newInclusionState = !currentWord.is_included;

    // Update the inclusion state in the backend
    await updateUserWordRecall(userId, currentWord.word_id, currentWord.recall_state, false, newInclusionState);

    // Update the local state
    const updatedWords = [...toShow];
    updatedWords[index].is_included = newInclusionState;
    setToShow(updatedWords);
  };

  // Handle correct memorization
  const handleMemorized = async (index, maxWordsToShow) => {
    const currentWord = toShow[index];
    const newRecallState = updateRecallState(currentWord.recall_state, true);

    if (!incorrectAttempts[currentWord.word]) {
      setFirstTimeCorrect([...firstTimeCorrect, currentWord]);
    }

    setCorrectlyMemorized(prevSet => new Set(prevSet.add(currentWord.word)));

    // Call backend to update recall state
    await updateUserWordRecall(userId, currentWord.word_id, newRecallState, true, currentWord.is_included);

    // Update local state
    const updatedWords = [...toShow];
    updatedWords[index].recall_state = newRecallState;
    const filteredToShow = updatedWords.filter((_, i) => i !== index);

    const availableIndexes = filteredToShow.length > maxWordsToShow ?
      filteredToShow.slice(maxWordsToShow) : filteredToShow;
    const randomWordIndex = availableIndexes.length > 0 ?
      Math.floor(Math.random() * availableIndexes.length) + maxWordsToShow :
      filteredToShow.length - 1;

    const newWord = filteredToShow[randomWordIndex];
    filteredToShow.splice(randomWordIndex, 1);
    filteredToShow.splice(index, 0, newWord);

    setToShow(filteredToShow);
  };

  // Handle incorrect memorization
  const handleNotMemorized = async (index, maxWordsToShow) => {
    const currentWord = toShow[index];
    const newRecallState = updateRecallState(currentWord.recall_state, false);

    setIncorrectAttempts(prev => ({
      ...prev,
      [currentWord.word]: (prev[currentWord.word] || 0) + 1,
    }));

    // Call backend to update recall state
    await updateUserWordRecall(userId, currentWord.word_id, newRecallState, false, currentWord.is_included);

    // Update local state
    const updatedWords = [...toShow];
    updatedWords[index].recall_state = newRecallState;

    const availableIndexes = toShow.length > maxWordsToShow ?
      toShow.slice(maxWordsToShow) : toShow;
    const randomIndex = availableIndexes.length > 0 ?
      Math.floor(Math.random() * availableIndexes.length) + maxWordsToShow : index;

    const newToShow = [...toShow];
    [newToShow[index], newToShow[randomIndex]] = [newToShow[randomIndex], newToShow[index]];

    setToShow(newToShow);
  };

  useEffect(() => {
    if (!loading) {
      const timer = setInterval(() => setTimeElapsed(prev => prev + 1), 1000);
      if (toShow.length === 0) {
        clearInterval(timer);
      }
      return () => clearInterval(timer);
    }
  }, [toShow.length, loading]);

  return {
    toShow,
    loading,
    firstTimeCorrect,
    incorrectAttempts,
    correctlyMemorized,
    timeElapsed,
    loadWordsForWordset,
    toggleExclusion,
    handleMemorized,
    handleNotMemorized,
  };
};
