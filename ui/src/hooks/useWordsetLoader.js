import { useState, useEffect, useCallback } from 'react';
import { getWordsByWordset } from '../services/wordsService';
import { getUserWordsByWordset, updateUserWordRecall } from '../services/userService';
import { formatDistanceToNow } from 'date-fns'; // Importing the date formatting function

export const useWordsetLoader = (wordsetId, userId) => { // Make sure you pass userId in the component using this hook
  const [toShow, setToShow] = useState([]);
  const [loading, setLoading] = useState(true);
  const [firstTimeCorrect, setFirstTimeCorrect] = useState([]);
  const [incorrectAttempts, setIncorrectAttempts] = useState({});
  const [correctlyMemorized, setCorrectlyMemorized] = useState(new Set());
  const [timeElapsed, setTimeElapsed] = useState(0);
  
  const formatRecallTime = (recallTime) => {
    const recallDate = new Date(recallTime);
    return formatDistanceToNow(recallDate, { addSuffix: true });
  };

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
          recall_history: userWord 
            ? userWord.recall_histories.map((recall) => ({
                ...recall,
                relative_recall_time: formatRecallTime(recall.recall_time) // Format recall time
              }))
            : [],
        };
      });

      setToShow(convertedWords);
      setLoading(false);
    } catch (error) {
      setLoading(false);
      console.error('Error loading words or userword metadata:', error);
    }
  }, [wordsetId, userId]);
  


  // Handle exclusion/inclusion
  const toggleExclusion = async (index) => {
    const currentWord = toShow[index];
    const newInclusionState = !currentWord.is_included;

    // Update the inclusion state in the backend
    await updateUserWordRecall(userId, currentWord.word_id, 0, false, newInclusionState);
    
    // Update the local state
    const updatedWords = [...toShow];
    updatedWords[index].is_included = newInclusionState;
    setToShow(updatedWords);
  };


  const handleMemorized = (index, maxWordsToShow) => {
    const currentWord = toShow[index];
    
    if (!incorrectAttempts[currentWord.word]) {
      setFirstTimeCorrect([...firstTimeCorrect, currentWord]);
    }

    setCorrectlyMemorized(prevSet => new Set(prevSet.add(currentWord.word)));
    const filteredToShow = toShow.filter((_, i) => i !== index);
    
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

  const handleNotMemorized = (index, maxWordsToShow) => {
    const currentWord = toShow[index];
    
    setIncorrectAttempts(prev => ({
      ...prev,
      [currentWord.word]: (prev[currentWord.word] || 0) + 1,
    }));

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
