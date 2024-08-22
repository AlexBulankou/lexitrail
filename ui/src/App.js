import React, { useState, useEffect } from 'react';
import Game from './components/Game';
import Completed from './components/Completed';
import words from './words';
import './styles/Global.css';
import './styles/App.css';

const App = () => {
  const [toShow, setToShow] = useState(words);
  const [firstTimeCorrect, setFirstTimeCorrect] = useState([]);
  const [incorrectAttempts, setIncorrectAttempts] = useState({});
  const [correctlyMemorized, setCorrectlyMemorized] = useState(new Set());
  const [timeElapsed, setTimeElapsed] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setTimeElapsed(prev => prev + 1), 1000);
    if (toShow.length === 0) {
      clearInterval(timer);
    }
    return () => clearInterval(timer); // Cleanup on component unmount
  }, [toShow.length]);

  const handleMemorized = (index) => {
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
    
    setToShow(toShow.filter((_, i) => i !== index)); // Remove the memorized word
  };
  
  const handleNotMemorized = (index) => {
    const currentWord = toShow[index];
    console.log(`handleNotMemorized: Word not memorized at index ${index}: ${currentWord.word}`);
  
    setIncorrectAttempts(prev => ({
      ...prev,
      [currentWord.word]: (prev[currentWord.word] || 0) + 1,
    }));
  
    const newToShow = toShow.filter((_, i) => i !== index); // Remove the current word
    const randomIndex = Math.floor(Math.random() * (newToShow.length + 1));
    newToShow.splice(randomIndex, 0, currentWord); // Re-insert it at a random position
  
    setToShow(newToShow); // Update the state with the modified list
  };
  
  const resetGame = () => {
    setToShow(words);
    setFirstTimeCorrect([]);
    setIncorrectAttempts({});
    setCorrectlyMemorized(new Set());
    setTimeElapsed(0);
  };

  if (toShow.length === 0) {
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
      totalWords={words.length}
      correctlyMemorizedCount={correctlyMemorized.size}
      incorrectAttempts={incorrectAttempts}
    />
  );
};

export default App;
