import React, { useState, useEffect } from 'react';
import WordCard from './WordCard';
import Completed from './Completed';  // Import Completed component
import { useParams } from 'react-router-dom';  
import { useWordsetLoader } from '../hooks/useWordsetLoader';
import '../styles/Game.css';  

const Game = () => {
  const { wordsetId } = useParams();
  const { toShow: displayWords, loading, timeElapsed, handleMemorized, handleNotMemorized, firstTimeCorrect, correctlyMemorized, incorrectAttempts, resetGame } = useWordsetLoader(wordsetId);  

  const [layoutClass, setLayoutClass] = useState('layout1');
  const [maxCardsToShow, setMaxCardsToShow] = useState(1);  

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
    const cardHeight = 300;  

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
      if (height <= cardHeight * 2) {
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

  const wordsToRender = displayWords.slice(0, maxCardsToShow);

  if (loading) {
    return <div>Loading...</div>;
  }

  // If there are no words left to show, display the Completed component
  if (displayWords.length === 0) {
    return (
      <Completed
        timeElapsed={timeElapsed}
        firstTimeCorrect={firstTimeCorrect}
        incorrectAttempts={incorrectAttempts}
        resetGame={resetGame}  // Provide a way to reset the game
      />
    );
  }

  return (
    <div className="container">
      <div className="timer">
        {Math.floor(timeElapsed / 60)}:{('0' + timeElapsed % 60).slice(-2)}
      </div>
      <div className={`cards-container ${layoutClass}`}>
        {wordsToRender.map((word, index) => (
          <WordCard
            key={index}
            word={word}
            handleMemorized={() => handleCardGuessed(index, true)}
            handleNotMemorized={() => handleCardGuessed(index, false)}
            incorrectAttempts={incorrectAttempts[word.word] || 0}
          />
        ))}
      </div>
      <div className="progress-bar-container">
        <div className="progress-bar">
          <div className="progress" style={{ width: `${(correctlyMemorized.size / displayWords.length) * 100}%` }}></div>
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
