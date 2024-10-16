import React, { useState, useEffect } from 'react';
import WordCard from './WordCard';
import Completed from './Completed';
import { useParams, useLocation } from 'react-router-dom';
import { useWordsetLoader } from '../hooks/useWordsetLoader';
import { useAuth } from '../hooks/useAuth';
import '../styles/Game.css';

const Game = () => {
  const { wordsetId } = useParams();
  const { state } = useLocation();  // Capture the state passed from navigation
  const showExcludedFromState = state?.showExcluded || false;  // Extract the showExcluded flag
  const { user } = useAuth();

  if (!user) {
    return <div>Please log in to play the game</div>;
  }

  const {
    toShow: displayWords,
    loading,
    timeElapsed,
    handleMemorized,
    handleNotMemorized,
    firstTimeCorrect,
    correctlyMemorized,
    incorrectAttempts,
    toggleExclusion,
    resetGame
  } = useWordsetLoader(wordsetId, user.email, showExcludedFromState);  // Pass showExcludedFromState to hook

  const [layoutClass, setLayoutClass] = useState('layout1');
  const [maxCardsToShow, setMaxCardsToShow] = useState(1);
  const [showExcluded, setShowExcluded] = useState(showExcludedFromState);  // Initialize with state value

  useEffect(() => {
    updateLayout();
    window.addEventListener('resize', updateLayout);

    return () => {
      window.removeEventListener('resize', updateLayout);
    };
  }, []);

  const updateLayout = () => {
    const width = window.innerWidth;
    const height = window.innerHeight;

    const cardWidth = 250;
    const cardHeight = 500;
    const extraHorizonalSpaceNeeded = 250;

    if (width <= cardWidth * 2) {
      setLayoutClass('layout1');
      setMaxCardsToShow(1);
    } else if (width <= cardWidth * 3) {
      if (height <= cardHeight * 2) {
        setLayoutClass('layout2');
        setMaxCardsToShow(2);
      } else {
        setLayoutClass('layout4');
        setMaxCardsToShow(4);
      }
    } else {
      if (height <= (cardHeight * 2) + extraHorizonalSpaceNeeded) {
        setLayoutClass('layout3');
        setMaxCardsToShow(3);
      } else {
        setLayoutClass('layout5');
        setMaxCardsToShow(6);
      }
    }
  };

  const handleCardGuessed = (index, isCorrect) => {
    const word = displayWords[index];
    if (isCorrect) {
      handleMemorized(index, maxCardsToShow);
    } else {
      handleNotMemorized(index, maxCardsToShow);
    }
  };

  const toggleWordsetFilter = () => {
    const newShowExcluded = !showExcluded;
    setShowExcluded(newShowExcluded);
    loadWithExclusionFilter(newShowExcluded);  // Call the loadWithExclusionFilter explicitly
  };

  const wordsToRender = displayWords.slice(0, maxCardsToShow);

  if (loading) {
    return <div>Loading...</div>;
  }

  if (displayWords.length === 0) {
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
    <div className="container">
      <button onClick={toggleWordsetFilter}>
        {showExcluded ? 'Show Included' : 'Show Excluded'}
      </button>
      <div className="timer">
        {Math.floor(timeElapsed / 60)}:{('0' + timeElapsed % 60).slice(-2)}
      </div>
      <div className={`cards-container ${layoutClass}`}>
        {wordsToRender.map((word, index) => (
          <WordCard
            key={index}
            word={{ ...word, user_id: user.email }} // Ensure user_id is passed correctly
            handleMemorized={() => handleCardGuessed(index, true)}
            handleNotMemorized={() => handleCardGuessed(index, false)}
            toggleExclusion={() => toggleExclusion(index)}  // Pass toggleExclusion to WordCard
            incorrectAttempts={incorrectAttempts[word.word] || 0}
          />
        ))}
      </div>
      <div className="progress-bar-container">
        <div className="progress-bar">
          <div className="progress" style={{ width: displayWords.length ? `${(correctlyMemorized.size / displayWords.length) * 100}%` : '0%' }}></div>
        </div>
        <div className="progress-info">
          recalled {correctlyMemorized.size} out of {displayWords.length}
        </div>
      </div>
      <div className="progress-stats">
        <div className="not-memorized">❌ {Object.keys(incorrectAttempts).length}</div>
        <div className="memorized">✔️ {correctlyMemorized.size}</div>
      </div>
    </div>
  );
};

export default Game;