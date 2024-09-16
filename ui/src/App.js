import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Route, Routes, Navigate } from "react-router-dom";
import Game from './components/Game';
import Completed from './components/Completed';
import Profile from './components/Profile.js';
import PrivateRoute from './components/PrivateRoute.js';
import NavBar from './components/NavBar.js';  // Import NavBar component
import { useAuth } from './hooks/useAuth';  // Custom Hook
import Wordsets from './components/Wordsets'; // Import Wordsets component
import { getWordsByWordset } from './services/wordsService'; // New function to fetch words for a wordset


import './styles/Global.css';
import './styles/App.css';
import './styles/NavBar.css';  // Import the CSS file

const App = () => {
  const { user, login, logOut } = useAuth();
  const [toShow, setToShow] = useState([]);
  const [firstTimeCorrect, setFirstTimeCorrect] = useState([]);
  const [incorrectAttempts, setIncorrectAttempts] = useState({});
  const [correctlyMemorized, setCorrectlyMemorized] = useState(new Set());
  const [timeElapsed, setTimeElapsed] = useState(0);
  const [loading, setLoading] = useState(true);

  const loadWordsForWordset = (wordsetId) => {
    setLoading(true);
    getWordsByWordset(wordsetId)
      .then((loadedWords) => {
        setToShow(loadedWords);
        setLoading(false);
      })
      .catch(() => setLoading(false));
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

  return (
    <Router>
      <NavBar user={user} login={login} logOut={logOut} />
      <Routes>
        <Route path="/" element={<Profile profileDetails={user} login={login} logout={logOut} />} />
        <Route path="/wordsets" element={<Wordsets />} />
        <Route path="/game/:wordsetId" element={
          <PrivateRoute profileDetails={user} login={login} logOut={logOut}>
            {!loading && toShow.length === 0 ? (
              <Completed
                timeElapsed={timeElapsed}
                firstTimeCorrect={firstTimeCorrect}
                incorrectAttempts={incorrectAttempts}
                resetGame={resetGame}
              />
            ) : (
              <Game
                timeElapsed={timeElapsed}
                displayWords={toShow}
                handleMemorized={handleMemorized}
                handleNotMemorized={handleNotMemorized}
                firstTimeCorrectCount={firstTimeCorrect.length}
                totalWords={toShow.length}
                correctlyMemorizedCount={correctlyMemorized.size}
                incorrectAttempts={incorrectAttempts}
              />
            )}
          </PrivateRoute>
        } />
        {/* This will handle the base /game route by redirecting to /wordsets */}
        <Route path="/game" element={<Navigate to="/wordsets" />} />
      </Routes>
    </Router>
  );
};

export default App;
