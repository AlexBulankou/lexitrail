import React, { useState } from 'react';
import '../styles/WordCard.css';

const WordCard = ({ word, handleMemorized, handleNotMemorized, incorrectAttempts }) => {
  const [isFlipped, setIsFlipped] = useState(false);

  const handleCardClick = () => {
    setIsFlipped(!isFlipped);
  };

  const stopPropagation = (e) => {
    e.stopPropagation();
  };

  const flipCard = () => {
    setIsFlipped(!isFlipped);
  };

  const onMemorized = () => {
    if (isFlipped) {
      flipCard(); // Flip back to front first
    }
    handleMemorized(); // Then proceed with memorizing
  };

  const onNotMemorized = () => {
    if (isFlipped) {
      flipCard(); // Flip back to front first
    }
    handleNotMemorized(); // Then proceed with not memorizing
  };

  return (
    <div className="word-card" onClick={handleCardClick}>
      <div className={`word-card-inner ${isFlipped ? 'flipped' : ''}`}>
        <div className="word-card-front">
          {word.word}
        </div>
        <div className="word-card-back">
          <p>
            {word.meaning.split('\n').map((line, index) => (
              <React.Fragment key={index}>
                {line}
                <br />
              </React.Fragment>
            ))}
          </p>
        </div>
      </div>
      <div className="buttons" onClick={stopPropagation}>
        <button onClick={onNotMemorized}>❌</button>
        <button onClick={onMemorized}>✔️</button>
      </div>
    </div>
  );
};


export default WordCard;
