import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Route, Routes, Link } from "react-router-dom";
import Game from './components/Game';
import Completed from './components/Completed';
import Profile from './components/Profile.js';
import PrivateRoute from './components/PrivateRoute.js';
import { getWords } from './words.js';
import { googleLogout, useGoogleLogin, } from '@react-oauth/google';

import './styles/Global.css';
import './styles/App.css';
import './styles/NavBar.css';  // Import the CSS file

const App = () => {
  const [toShow, setToShow] = useState([]);
  const [firstTimeCorrect, setFirstTimeCorrect] = useState([]);
  const [incorrectAttempts, setIncorrectAttempts] = useState({});
  const [correctlyMemorized, setCorrectlyMemorized] = useState(new Set());
  const [timeElapsed, setTimeElapsed] = useState(0);
  const [loading, setLoading] = useState(true);

  const [user, setUser] = useState(null);

  const initUser = {
    onSuccess: (tokenResponse) => {
      fetch(`https://www.googleapis.com/oauth2/v3/userinfo?access_token=${tokenResponse.access_token}`, {
        method: 'GET',
        headers: {
          Authorization: `Bearer ${tokenResponse.access_token}`,
          Accept: 'application/json'
        }
      })
        .then((response) => {
          if (!response.ok) {
            throw new Error('Network response was not ok');
          }
          return response.json();
        })
        .then((data) => {
          setUser(data);
          console.log(data);
        })
        .catch((error) => {
          console.log(error);
        });
    },
    onError: (error) => console.log('Login Failed:', error)
  };

  const login = useGoogleLogin(initUser);

  const logOut = () => {
    console.log("logout");
    googleLogout();
    setUser(null);
  };


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

  return (
    <>
      <Router>
        <div>
          <nav className="navbar">
            <ul className="nav-list">
              <li className="nav-item">
                <Link to="/" className="nav-link">Home</Link>
              </li>
              <li className="nav-item">
                <Link to="/game" className="nav-link">Game</Link>
              </li>
              {user ? (
                <li className="user-section">
                  <div className="nav-user-info">
                    <img src={user.picture} alt={user.name} className='nav-profile-avatar' />
                    <span>{user.name}</span>
                  </div>
                  <button onClick={logOut} className="logout-button">Logout</button>
                </li>
              ) : (
                <li className="user-section">
                  <button onClick={() => login()} className="login-button">Login with Google</button>
                </li>
              )}
            </ul>
          </nav>
          <Routes>
            <Route path="/" element={
              <Profile profileDetails={user} login={login} logout={logOut} />
            } />

            <Route path="/game" element={
              <PrivateRoute profileDetails={user} login={login} logOut={logOut}>
                <div>
                  {
                    !loading && toShow.length === 0 ?
                      (
                        <Completed
                          timeElapsed={timeElapsed}
                          firstTimeCorrect={firstTimeCorrect}
                          incorrectAttempts={incorrectAttempts}
                          resetGame={resetGame}
                        />
                      ) :
                      (
                        <Game
                          timeElapsed={timeElapsed}
                          displayWords={toShow} // Pass the current list of words to Game.js
                          handleMemorized={handleMemorized}
                          handleNotMemorized={handleNotMemorized}
                          firstTimeCorrectCount={firstTimeCorrect.length}
                          totalWords={toShow.length}
                          correctlyMemorizedCount={correctlyMemorized.size}
                          incorrectAttempts={incorrectAttempts}
                        />
                      )
                  }
                </div>
              </PrivateRoute>

            } />
          </Routes>
        </div>
      </Router>
    </>
  );

};

export default App;

