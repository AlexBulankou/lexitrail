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

  // Helper function to shuffle an array
  const shuffleArray = (array) => {
    for (let i = array.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [array[i], array[j]] = [array[j], array[i]];
    }
    return array;
  };

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
              original_recall_time: new Date(hist.recall_time), // Original Date for sorting
              recall_time: formatDistanceToNow(new Date(hist.recall_time), { addSuffix: true }) // Human-readable format
            })) : [],
          };
        })
        // Filter based on inclusion/exclusion state
        .filter(word => showExcluded ? !word.is_included : word.is_included);

      // Shuffle words before sorting
      const shuffledWords = shuffleArray(convertedWords);

      // Sort by recall_state descending, and last recall time ascending (oldest first)
      const finalSortedWords = shuffledWords.sort((a, b) => {
        // Primary: recall_state descending
        if (b.recall_state !== a.recall_state) {
          return b.recall_state - a.recall_state;
        }

        // Secondary: last recall time ascending, treating missing recall history as "oldest"
        const aLastRecall = a.recall_history.length > 0 ? a.recall_history[0].original_recall_time : new Date(0);
        const bLastRecall = b.recall_history.length > 0 ? b.recall_history[0].original_recall_time : new Date(0);

        return aLastRecall - bLastRecall;
      });


      // Log the final sorted list for validation
      /*
      console.log("Final sorted list of words:");
      finalSortedWords.forEach(word => {
        const lastRecallTime = word.recall_history.length > 0
          ? word.recall_history[word.recall_history.length - 1].original_recall_time
          : "No History";
        console.log(`Recall State: ${word.recall_state}, Last Recall Time: ${lastRecallTime}, Recall History Count: ${word.recall_history.length}`);
      });
      */

      setToShow(finalSortedWords);
      setTotalToShow(finalSortedWords.length);
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

    // Update firstTimeCorrect using functional update to avoid stale state
    setFirstTimeCorrect(prevFirstTimeCorrect => {
      if (!incorrectAttempts[currentWord.word]) {
        return [...prevFirstTimeCorrect, currentWord];
      }
      return prevFirstTimeCorrect;
    });

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

    // Use functional update to ensure latest state for incorrectAttempts
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
