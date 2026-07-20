import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import PinyinText from './PinyinText';
import '../styles/Completed.css';

const Completed = ({ timeElapsed, firstTimeCorrect, incorrectAttempts, incorrectWords = {}, resetGame }) => {
  const totalWords = firstTimeCorrect.length + Object.keys(incorrectAttempts).length;
  const memorizedPercentage = totalWords > 0 ? (firstTimeCorrect.length / totalWords) * 100 : 0;
  const navigate = useNavigate();
  const [shareMessage, setShareMessage] = useState('');

  const timeLabel = `${Math.floor(timeElapsed / 60)}:${('0' + timeElapsed % 60).slice(-2)}`;
  const missedWords = Object.keys(incorrectAttempts);

  const handleShare = async () => {
    const summary = `I reviewed ${totalWords} words on Lexitrail — ${firstTimeCorrect.length}/${totalWords} correct (${Math.round(memorizedPercentage)}%) in ${timeLabel}.`;
    try {
      if (navigator.share) {
        await navigator.share({ title: 'Lexitrail', text: summary });
      } else if (navigator.clipboard) {
        await navigator.clipboard.writeText(summary);
        setShareMessage('Copied result to clipboard!');
      } else {
        setShareMessage(summary);
      }
    } catch (error) {
      // Share sheet dismissed or clipboard denied — nothing to recover.
    }
  };

  return (
    <div className="container completed">
      <div className="completed-time">{timeLabel}</div>
      <div className="completed-stats">{Math.round(memorizedPercentage)}%</div>

      {missedWords.length > 0 && (
        <div className="completed-review">
          <h3 className="completed-review-title">Review missed words</h3>
          <ul className="completed-review-list">
            {missedWords.map((word, index) => {
              const details = incorrectWords[word] || {};
              return (
                <li key={`missed-${index}`} className="completed-review-item">
                  <span className="completed-review-word" lang="zh">{word}</span>
                  {details.def1 && (
                    <span className="completed-review-def"><PinyinText text={details.def1} /></span>
                  )}
                  <span className="completed-incorrect-indicator">({incorrectAttempts[word] + 1} attempts)</span>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {firstTimeCorrect.length > 0 && (
        <ul className="completed-list">
          {firstTimeCorrect.map((item, index) => (
            <li key={index} lang="zh">{item.word}</li>
          ))}
        </ul>
      )}

      {shareMessage && <div className="completed-share-message">{shareMessage}</div>}

      <div className="completed-actions">
        <button className="completed-button" onClick={resetGame}>Play again</button>
        <button className="completed-button" onClick={() => navigate('/wordsets')}>Back to Word Sets</button>
        <button className="completed-button completed-button-share" onClick={handleShare}>Share</button>
      </div>
    </div>
  );
};

export default Completed;
