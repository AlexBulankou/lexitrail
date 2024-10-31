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

    if (!removeWordAtIndex && filteredToShow.length <= maxWordsToShow) {
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


  // Common function to handle state updates and async recall state updates
  const updateWordState = (index, updateCallback, maxWordsToShow, removeWordAtIndex = false) => {
    setToShow(prevToShow => {
      const updatedWords = [...prevToShow];
      const currentWord = updatedWords[index];

      // Apply the specific update logic for the word
      updateCallback(currentWord, updatedWords);

      // Reorder the list based on inclusion or memorization logic
      const filteredToShow = updateWordListAfterAction(index, maxWordsToShow, updatedWords, removeWordAtIndex);
      console.log(`Now showing ${filteredToShow.map(item => item.word_index)}...`);
      return filteredToShow;
    });
  };

  // Toggle exclusion state asynchronously
  const toggleExclusion = (index) => {
    const currentWord = toShow[index];
    const newInclusionState = !currentWord.is_included;

    console.log(`Toggling exclusion for word ID ${currentWord.word_id}. New state: ${newInclusionState}`);
    setTotalToShow(totalToShow - 1);

    updateWordState(index, (word, updatedWords) => {
      updatedWords[index] = { ...word, is_included: newInclusionState };
    }, 0, true);

    // Async call to update the backend
    updateUserWordRecall(userId, currentWord.word_id, currentWord.recall_state, false, newInclusionState)
      .catch((error) => console.error('Error updating exclusion state:', error));
  };

  // Handle correct memorization asynchronously with functional state update
  const handleMemorized = (index, maxWordsToShow) => {
    const currentWord = toShow[index];
    const newRecallState = updateRecallState(currentWord.recall_state, true);

    if (!incorrectAttempts[currentWord.word]) {
      setFirstTimeCorrect([...firstTimeCorrect, currentWord]);
    }
    setCorrectlyMemorized(prevSet => new Set(prevSet.add(currentWord.word)));

    console.log(`Updating recall state to backend for word ID ${currentWord.word_id}. New state: ${newRecallState}`);

    updateWordState(index, (word, updatedWords) => {
      updatedWords[index] = { ...word, recall_state: newRecallState };
    }, maxWordsToShow, true);

    // Async call to update the backend
    updateUserWordRecall(userId, currentWord.word_id, newRecallState, true, currentWord.is_included)
      .catch((error) => console.error('Error updating recall state for memorized word:', error));
  };

  // Handle incorrect memorization asynchronously
  const handleNotMemorized = (index, maxWordsToShow) => {
    const currentWord = toShow[index];
    const newRecallState = updateRecallState(currentWord.recall_state, false);

    setIncorrectAttempts(prev => ({
      ...prev,
      [currentWord.word]: (prev[currentWord.word] || 0) + 1,
    }));

    console.log(`Updating recall state to backend for word ID ${currentWord.word_id}. New state: ${newRecallState}`);

    updateWordState(index, (word, updatedWords) => {
      updatedWords[index] = { ...word, recall_state: newRecallState };
    }, maxWordsToShow, false);

    // Async call to update the backend
    updateUserWordRecall(userId, currentWord.word_id, newRecallState, false, currentWord.is_included)
      .catch((error) => console.error('Error updating recall state for not memorized word:', error));
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
