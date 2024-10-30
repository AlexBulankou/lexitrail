import { useState, useEffect, useCallback } from 'react';
import { getWordsByWordset } from '../services/wordsService';
import { getUserWordsByWordset, updateUserWordRecall } from '../services/userService';
import { formatDistanceToNow, max } from 'date-fns';

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
  const [totalToShow, setTotalToShow] = useState(0);

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

      var wordIndex = 0;
      const convertedWords = loadedWords
        .map((word) => {
          const userWord = userWordsMetadata.find(uw => uw.word_id === word.word_id);
          return {
            word: word.word,
            word_index: wordIndex++,
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
        .filter(word => showExcluded ? !word.is_included : word.is_included)
        // Sort by recall_state in descending order
        .sort((a, b) => b.recall_state - a.recall_state);

      setToShow(convertedWords);
      setTotalToShow(convertedWords.length);
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
  const updateWordListAfterAction = (index, maxWordsToShow, updatedWords, removeWordAtIndex) => {
    // Filter out the word at the specified index
    // console.log(`#Inside updateWordListAfterAction#. index=${index}, maxWordsToShow=${maxWordsToShow}, updatedWords=${updatedWords.map(item => item.word_index)}`);

    var filteredToShow = updatedWords;

    if (!removeWordAtIndex && filteredToShow.length <= maxWordsToShow){
      return filteredToShow;
    }


    if (removeWordAtIndex) {
      filteredToShow = updatedWords.filter((_, i) => i !== index);
    } else {
      // move to the end of the array
      const [itemAtIndex] = filteredToShow.splice(index, 1);
      filteredToShow.push(itemAtIndex);
    }

    const nextWordIndex = filteredToShow.length > maxWordsToShow ? maxWordsToShow : filteredToShow.length - 1;

    // console.log(`Now nextWordIndex=${nextWordIndex}, filteredToShow=${filteredToShow.map(item => item.word_index)}`);

    if (filteredToShow.length == 0) {
      return filteredToShow;
    }

    // Replace the removed word with a randomly selected word and keep the order intact
    const newWord = filteredToShow[nextWordIndex];
    filteredToShow.splice(nextWordIndex, 1);
    filteredToShow.splice(index, 0, newWord);

    // console.log(`before return: newWord=${newWord.word_index}, filteredToShow=${filteredToShow.map(item => item.word_index)}`);

    return filteredToShow;
  };


  const toggleExclusion = async (index) => {
    const currentWord = toShow[index];
    const newInclusionState = !currentWord.is_included;

    try {
      console.log(`Toggling exclusion for word ID ${currentWord.word_id}. New state: ${newInclusionState}`);

      // Update the inclusion state in the backend
      await updateUserWordRecall(userId, currentWord.word_id, currentWord.recall_state, false, newInclusionState);

      // Remove the word from the current list based on the current filter (included or excluded)
      const updatedWords = toShow.filter((_, i) => i !== index);

      // Update the local state to reflect the change
      setToShow(updatedWords);
      setTotalToShow(totalToShow - 1);

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
    const filteredToShow = updateWordListAfterAction(index, maxWordsToShow, updatedWords, true);
    // console.log(`Now showing ${filteredToShow.map(item => item.word_index)}...`);
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
    const filteredToShow = updateWordListAfterAction(index, maxWordsToShow, updatedWords, false);
    // console.log(`Now showing ${filteredToShow.map(item => item.word_index)}...`);
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
    totalToShow,
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
