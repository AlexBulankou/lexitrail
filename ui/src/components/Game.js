import React, { useState, useEffect } from 'react';
import WordCard from './WordCard';
import Completed from './Completed';
import { useParams, useLocation } from 'react-router-dom';
import { useWordsetLoader } from '../hooks/useWordsetLoader';
import { useAuth } from '../hooks/useAuth';
import '../styles/Game.css';
import { useNavigate } from 'react-router-dom';

const Game = () => {
  const { wordsetId } = useParams();
  const { state } = useLocation();  // Capture the state passed from navigation
  const showExcludedFromState = state?.showExcluded || false;  // Extract the showExcluded flag
  const { user } = useAuth();
  const navigate = useNavigate();

  if (!user) {
    return <div>Please log in to play the game</div>;
  }

  const {
    toShow: displayWords,
    totalToShow: totalToShow,
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

  const [layoutClass, setLayoutClass] = useState('layout1c1r');
  const [maxCardsToShow, setMaxCardsToShow] = useState(1);

  useEffect(() => {
    updateLayout();
    window.addEventListener('resize', updateLayout);
  
    return () => {
      window.removeEventListener('resize', updateLayout);
    };
  }, [displayWords.length]); // Run effect whenever displayWords length changes



  const updateLayout = () => {
    const width = window.innerWidth;
    const height = window.innerHeight;

    const cardWidth = 180;
    const cardHeight = 310;
    const extraHorizontalSpaceNeeded = 120;

    const maxColumns = Math.min(Math.floor(width / cardWidth), 12);
    const maxRows = Math.min(Math.floor((height - extraHorizontalSpaceNeeded) / cardHeight), 4);

    // Dynamically generate layout options
    const layoutOptions = [];
    for (let columns = 1; columns <= maxColumns; columns++) {
      for (let rows = 1; rows <= maxRows; rows++) {
        const capacity = columns * rows;
        layoutOptions.push({
          className: `layout${columns}c${rows}r`,
          columns,
          rows,
          capacity
        });
      }
    }

    // Select the most suitable layout based on available cards and window size
    const selectedLayout = layoutOptions
      .filter(option => option.columns <= maxColumns && option.rows <= maxRows)
      .filter(option => option.capacity <= displayWords.length)
      .pop();

    if (selectedLayout) {
      setLayoutClass(selectedLayout.className);
      setMaxCardsToShow(selectedLayout.capacity);
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
    const reversedShowExcluded = !showExcludedFromState;
    navigate(`/game/${wordsetId}`, { state: { showExcluded: reversedShowExcluded } });
  };

  const markAllAsMemorized = () => {
    for (let i = 0; i < maxCardsToShow; i++) {
      handleCardGuessed(i, true);
    }
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

      <div className="progress-stats">
        <div className="not-memorized">❌ {Object.keys(incorrectAttempts).length}</div>

        <button className="show-excluded-button" onClick={toggleWordsetFilter}>
          {showExcludedFromState ? 'Show Included' : 'Show Excluded'}
        </button>
        <div className="timer">
          {Math.floor(timeElapsed / 60)}:{('0' + timeElapsed % 60).slice(-2)}

        </div>
        <div className="memorized">✔️ {correctlyMemorized.size}</div>
      </div>



      <div className={`cards-container ${layoutClass}`}>
        {wordsToRender.map((word, index) => (
          <WordCard
            key={index}
            word={{ ...word, user_id: user.email, index: word.word_index }} // Ensure user_id is passed correctly
            handleMemorized={() => handleCardGuessed(index, true)}
            handleNotMemorized={() => handleCardGuessed(index, false)}
            toggleExclusion={() => toggleExclusion(index)}  // Pass toggleExclusion to WordCard
            incorrectAttempts={incorrectAttempts[word.word] || 0}
          />
        ))}
      </div>

      {/* New Button to Mark All Cards as Memorized */}
      <button
        className="mark-all-memorized-button"
        onClick={markAllAsMemorized}
      >
        ✔️ to all {maxCardsToShow}
      </button>

      <div className="progress-bar-container">
        <div className="progress-bar">
          <div className="progress" style={{ width: totalToShow ? `${(correctlyMemorized.size / totalToShow) * 100}%` : '0%' }}></div>

        </div>
        <div className="progress-info">
          recalled {correctlyMemorized.size} out of {totalToShow}
        </div>
      </div>

    </div>
  );
};

export default Game;