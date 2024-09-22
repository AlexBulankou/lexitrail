import { useState, useEffect, useCallback } from 'react';
import { getWordsByWordset } from '../services/wordsService';
import { getUserWordsByWordset, updateUserWordRecall } from '../services/userService';
import { formatDistanceToNow } from 'date-fns';

// Function to abstract recall state logic
const updateRecallState = (currentRecallState, isCorrect) => {
  if (isCorrect) {
    console.log(`Correct recall! Current recall state: ${currentRecallState}, New recall state: ${Math.max(0, currentRecallState - 1)}`);
    return Math.max(0, currentRecallState - 1);
  } else {
    console.log(`Incorrect recall! Current recall state: ${currentRecallState}, New recall state: ${currentRecallState + 1}`);
    return currentRecallState + 1;
  }
};

export const useWordsetLoader = (wordsetId, userId, showExcluded) => {
  const [toShow, setToShow] = useState([]);
  const [loading, setLoading] = useState(true);
  const [firstTimeCorrect, setFirstTimeCorrect] = useState([]);
  const [incorrectAttempts, setIncorrectAttempts] = useState({});
  const [correctlyMemorized, setCorrectlyMemorized] = useState(new Set());
  const [timeElapsed, setTimeElapsed] = useState(0);

  const loadWordsForWordset = useCallback(async () => {
    setLoading(true);
    try {
      console.log('Loading words for wordset:', wordsetId, 'Show Excluded:', showExcluded);

      // Fetch words from the wordset
      const response = await getWordsByWordset(wordsetId);
      const loadedWords = response.data;

      // Fetch userword metadata (recall history, exclusion state) for each word
      const userwordsResponse = await getUserWordsByWordset(userId, wordsetId);
      const userWordsMetadata = userwordsResponse.data;

      const convertedWords = loadedWords
        .map((word) => {
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
        })
        // Filter based on inclusion/exclusion state
        .filter(word => showExcluded ? !word.is_included : word.is_included);

      setToShow(convertedWords);
      setLoading(false);
    } catch (error) {
      setLoading(false);
      console.error('Error loading words or userword metadata:', error);
    }
  }, [wordsetId, userId, showExcluded]);

  useEffect(() => {
    if (wordsetId && userId) {
      loadWordsForWordset();
    }
  }, [loadWordsForWordset]);

  // Reusable function to update word list after an action (e.g., exclude, memorized, not memorized)
  const updateWordListAfterAction = (index, maxWordsToShow, updatedWords) => {
    // Filter out the word at the specified index
    const filteredToShow = updatedWords.filter((_, i) => i !== index);

    // Calculate available indexes for random word replacement
    const availableIndexes = filteredToShow.length > maxWordsToShow ?
      filteredToShow.slice(maxWordsToShow) : filteredToShow;

    const randomWordIndex = availableIndexes.length > 0 ?
      Math.floor(Math.random() * availableIndexes.length) + maxWordsToShow :
      filteredToShow.length - 1;

    // Replace the removed word with a randomly selected word and keep the order intact
    const newWord = filteredToShow[randomWordIndex];
    filteredToShow.splice(randomWordIndex, 1);
    filteredToShow.splice(index, 0, newWord);

    return filteredToShow;
  };


  const toggleExclusion = async (index, maxWordsToShow) => {
    const currentWord = toShow[index];
    const newInclusionState = !currentWord.is_included;
  
    try {
      console.log(`Toggling exclusion for word ID ${currentWord.word_id}. New state: ${newInclusionState}`);
      
      // Update the exclusion state on the backend
      await updateUserWordRecall(userId, currentWord.word_id, currentWord.recall_state, false, newInclusionState);
  
      // Update the word's inclusion state locally
      const updatedWords = [...toShow];
      updatedWords[index].is_included = newInclusionState;
  
      // Filter out the word after exclusion if it's no longer part of the current filter set
      const filteredToShow = updatedWords.filter(word => word.is_included === !newInclusionState);
  
      // Rebuild the list with proper order
      const availableIndexes = filteredToShow.length > maxWordsToShow ?
        filteredToShow.slice(maxWordsToShow) : filteredToShow;
  
      const randomWordIndex = availableIndexes.length > 0 ?
        Math.floor(Math.random() * availableIndexes.length) + maxWordsToShow :
        filteredToShow.length - 1;
  
      // Replace the removed word with a randomly selected word, keeping the order intact
      const newWord = filteredToShow[randomWordIndex];
      filteredToShow.splice(randomWordIndex, 1);
      filteredToShow.splice(index, 0, newWord);
  
      setToShow(filteredToShow);
    } catch (error) {
      console.error('Error updating exclusion state:', error);
    }
  };
  
  
  

  // Handle correct memorization
  const handleMemorized = async (index, maxWordsToShow) => {
    const currentWord = toShow[index];
    const newRecallState = updateRecallState(currentWord.recall_state, true);

    if (!incorrectAttempts[currentWord.word]) {
      setFirstTimeCorrect([...firstTimeCorrect, currentWord]);
    }

    setCorrectlyMemorized(prevSet => new Set(prevSet.add(currentWord.word)));

    console.log(`Updating recall state to backend for word ID ${currentWord.word_id}. New state: ${newRecallState}`);
    await updateUserWordRecall(userId, currentWord.word_id, newRecallState, true, currentWord.is_included);

    const updatedWords = [...toShow];
    updatedWords[index].recall_state = newRecallState;

    // Update the local state using the common function
    const filteredToShow = updateWordListAfterAction(index, maxWordsToShow, updatedWords);
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

    console.log(`Updating recall state to backend for word ID ${currentWord.word_id}. New state: ${newRecallState}`);
    await updateUserWordRecall(userId, currentWord.word_id, newRecallState, false, currentWord.is_included);

    const updatedWords = [...toShow];
    updatedWords[index].recall_state = newRecallState;

    // Update the local state using the common function
    const filteredToShow = updateWordListAfterAction(index, maxWordsToShow, updatedWords);
    setToShow(filteredToShow);
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
    toggleExclusion,
    handleMemorized,
    handleNotMemorized,
  };
};
