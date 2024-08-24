import React, { useState, useEffect } from 'react';
import Game from './components/Game';
import Completed from './components/Completed';
import { getWords } from './words.js';
import './styles/Global.css';
import './styles/App.css';

const App = () => {
  const [toShow, setToShow] = useState([]);
  const [firstTimeCorrect, setFirstTimeCorrect] = useState([]);
  const [incorrectAttempts, setIncorrectAttempts] = useState({});
  const [correctlyMemorized, setCorrectlyMemorized] = useState(new Set());
  const [timeElapsed, setTimeElapsed] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getWords()
      .then((loadedWords) => {
        setLoading(false); // Mark loading as complete
        setToShow(loadedWords);
      })
      .catch((error) => {
        console.error('Failed to load words:', error);
        setLoading(false); // Ensure loading state is updated even if there's an error
      });
  }, []);

  useEffect(() => {
    if (!loading) {
      const timer = setInterval(() => setTimeElapsed(prev => prev + 1), 1000);
      if (toShow.length === 0) {
        clearInterval(timer);
      }
      return () => clearInterval(timer); // Cleanup on component unmount
    }
  }, [toShow.length, loading]);

  const handleMemorized = (index, maxWordsToShow) => {
    const currentWord = toShow[index];
    console.log(`handleMemorized: Correctly memorized word at index ${index}: ${currentWord.word}`);

    if (!incorrectAttempts[currentWord.word]) {
      setFirstTimeCorrect([...firstTimeCorrect, currentWord]);
    } else {
      setIncorrectAttempts(prev => ({
        ...prev,
        [currentWord.word]: prev[currentWord.word] || 0,
      }));
    }

    setCorrectlyMemorized(prevSet => new Set(prevSet.add(currentWord.word)));

    // Remove the memorized word
    const filteredToShow = toShow.filter((_, i) => i !== index);

    // Find the range of possible new words to insert
    const availableIndexes = filteredToShow.length > maxWordsToShow ?
      filteredToShow.slice(maxWordsToShow) :
      filteredToShow;

    // Select a random word from the available ones
    const randomWordIndex = availableIndexes.length > 0 ?
      Math.floor(Math.random() * availableIndexes.length) + maxWordsToShow :
      filteredToShow.length - 1; // Use the last element if not enough

    const newWord = filteredToShow[randomWordIndex];
    // Remove the selected word from its original place
    filteredToShow.splice(randomWordIndex, 1);

    // Insert the new word at the position of the memorized word
    filteredToShow.splice(index, 0, newWord);

    // Update the state with the modified list
    setToShow(filteredToShow);
  };

  const handleNotMemorized = (index, maxWordsToShow) => {
    const currentWord = toShow[index];
  console.log(`handleNotMemorized: Word not memorized at index ${index}: ${currentWord.word}`);

  setIncorrectAttempts(prev => ({
    ...prev,
    [currentWord.word]: (prev[currentWord.word] || 0) + 1,
  }));

  // Find the range of possible indexes for swapping
  const availableIndexes = toShow.length > maxWordsToShow ? 
                            toShow.slice(maxWordsToShow) : 
                            toShow;

  // Select a random index within the allowed range
  const randomIndex = availableIndexes.length > 0 ? 
                      Math.floor(Math.random() * availableIndexes.length) + maxWordsToShow : 
                      index;

  // Perform the swap
  const newToShow = [...toShow];
  [newToShow[index], newToShow[randomIndex]] = [newToShow[randomIndex], newToShow[index]];

  // Update the state with the modified list
  setToShow(newToShow);
  };

  const resetGame = () => {
    getWords().then(setToShow).catch(console.error); // Reload words on reset
    setFirstTimeCorrect([]);
    setIncorrectAttempts({});
    setCorrectlyMemorized(new Set());
    setTimeElapsed(0);
  };


  if (!loading && toShow.length === 0) {
    return (
      <Completed
        timeElapsed={timeElapsed}
        firstTimeCorrect={firstTimeCorrect}
        incorrectAttempts={incorrectAttempts}
        resetGame={resetGame}
      />
    );
  }

  return (
    <Game
      timeElapsed={timeElapsed}
      displayWords={toShow} // Pass the current list of words to Game.js
      handleMemorized={handleMemorized}
      handleNotMemorized={handleNotMemorized}
      firstTimeCorrectCount={firstTimeCorrect.length}
      totalWords={toShow.length} // Use toShow.length instead of words.length
      correctlyMemorizedCount={correctlyMemorized.size}
      incorrectAttempts={incorrectAttempts}
    />
  );
};

export default App;
