import React, { useState, useEffect } from 'react';
import { getHint, regenerateHint } from '../services/hintService';
import { GameMode } from './Game';
import PinyinText from './PinyinText';
import SpeakButton from './SpeakButton';
import { buildHistoryTiles } from '../utils/historyTiles';
import '../styles/WordCard.css';

const WordCard = ({ mode, word, isFlipped, isHintDisplayed, handleMemorized, handleNotMemorized, toggleExclusion, feedbackClass, provideFeedback, setFlippedState }) => {
  const [hintImage, setHintImage] = useState(null);
  const [loadingHint, setLoadingHint] = useState(true);
  const [loadingWord, setLoadingWord] = useState(true); // New state for controlling button loading state

  useEffect(() => {
    // Validate that user_id and word_id are set correctly
    if (word.user_id && word.word_id) {
      setLoadingWord(false);

      // Clear the current hint and show loading message
      setHintImage(null);

      // SUG-2: hint images are opt-in. Only request one when the learner has
      // hints shown, so browsing the card grid doesn't fire a generate/fetch
      // request per card (one short session issued 37 hint requests).
      if (!isHintDisplayed) {
        setLoadingHint(false);
        return;
      }

      // Fetch the hint image when the component mounts or the word changes
      const fetchHint = async () => {
        try {
          setLoadingHint(true);
          const response = await getHint(word.user_id, word.word_id);
          if (response && response.data) {
            setHintImage(response.data.hint_image);
          }
        } catch (error) {
          console.error('Failed to load hint image:', error);
        } finally {
          setLoadingHint(false);
        }
      };
      fetchHint();
    } else {
      console.error(`Word: ${word ? JSON.stringify(word) : ""} has invalid user_id: ${word ? word.user_id : ""} or word_id: ${word ? word.word_id : ""}.`);
      setLoadingHint(false);
      setLoadingWord(false); // Set loadingWord to false if user_id or word_id is invalid
    }
  }, [word.user_id, word.word_id, isHintDisplayed]);

  const handleCardClick = () => {
    setFlippedState(!isFlipped);
  };


  const stopPropagation = (e) => {
    e.stopPropagation();
  };

  const handleButtonClick = (action) => {
    // Set loadingWord to true to disable all buttons
    setLoadingWord(true);
    setHintImage(null);

    // Save the current word ID to check if it changes after the action
    const currentWordId = word.word_id;

    // Execute the action
    action();

    // Check if the word has changed
    setTimeout(() => {
      if (word.word_id === currentWordId) {
        // If the word is still the same, reset the loading state and hint image
        setLoadingWord(false);
        setHintImage(hintImage); // Restore the previous hint image
      }
    }, 0); // Run this check right after the action to update states
  };



  const onMemorized = () => {
    provideFeedback(true, () => {
      if (isFlipped) {
        setFlippedState(false); // Ensure the card flips back
      }
      handleMemorized(); // Call the memorized handler
    });
  };

  const onNotMemorized = () => {
    provideFeedback(false, () => {
      if (isFlipped) {
        setFlippedState(false); // Ensure the card flips back
      }
      handleNotMemorized(); // Call the not-memorized handler
    });
  };

  const onQuizOptionClicked = (isCorrect) => {
    provideFeedback(isCorrect, () => {
      if (isCorrect) {
        handleMemorized();
      } else {
        handleNotMemorized();
      }
    });
  };

  const handleRegenerateHint = async () => {
    if (word.user_id && word.word_id) {
      setLoadingHint(true); // Set loadingHint to true while regenerating hint
      try {
        const response = await regenerateHint(word.user_id, word.word_id);
        if (response && response.data) {
          setHintImage(response.data.hint_image);
        }
      } catch (error) {
        console.error('Failed to regenerate hint image:', error);
      } finally {
        setLoadingHint(false); // Set loadingHint to false once hint regeneration is done
      }
    } else {
      console.error('Invalid user_id or word_id for regeneration:', word.user_id, word.word_id);
    }
  };

  // lexitrail#52 bug 2: the plain-text "Seen N×, M correct" summary (SUG-1) was
  // hard to read at a glance. Revert to the past-history tiles view Alex wants —
  // one small red/green tile per past answer (green = correct, red = wrong) —
  // but keep the accessibility improvements from SUG-7: a screen-reader summary
  // on the row and a small ✓/✗ glyph so the state isn't conveyed by color alone.
  // Shows the most recent answers (newest on the right); older ones are clipped.
  const renderHistoryTiles = (w) => {
    const { tiles, correct, total } = buildHistoryTiles(w.recall_history);
    if (total === 0) {
      return <span className="history-empty">New</span>;
    }
    return (
      <div
        className="history-tiles"
        role="img"
        aria-label={`Past answers: ${correct} correct of ${total}`}
      >
        {tiles.map((t, i) => (
          <span
            key={i}
            className={`history-tile ${t.correct ? 'correct' : 'wrong'}`}
            title={`${t.correct ? 'Correct' : 'Wrong'}${t.time ? ' · ' + t.time : ''}`}
            aria-hidden="true"
          >
            {t.correct ? '✓' : '✗'}
          </span>
        ))}
      </div>
    );
  };

  // Remove leading and trailing quotes and whitespace
  const removeQuotes = (text) => {
    if (!text) {
      return "";
    }

    return text
    .replace(/^['"]+|['"]+$/g, '')  // Remove quotes at the beginning and end
    .trim()                         // Trim whitespace
    .toLowerCase()                  // Convert to lowercase
    .replace(/\.$/, '');            // Remove trailing dot if it exists
};

  // Remove quotes and calculate the longest line for font size
  const calculateFontSize = (text, baseCoefficient, minSize = 1.5) => {
    // Remove leading and trailing quotes
    const trimmedText = text.trim();

    // Split text by '\n' and find the longest line
    const lines = trimmedText.split('\n');
    const longestLineLength = Math.max(...lines.map(line => removeQuotes(line).length));

    // Calculate font size based on the longest line length
    const fontSize = Math.max(baseCoefficient / (Math.pow(longestLineLength, 0.70)), minSize); // Ensure the font size doesn't go too small
    return `${fontSize}rem`;
  };

  return (
    <div className={`word-card ${feedbackClass}`}>
      {/* SUG-7: non-color cue (shape + label) for correct/incorrect, so the
          red/green border isn't the only signal for color-blind users. */}
      {feedbackClass && (
        <span
          className={`feedback-indicator ${feedbackClass}`}
          role="status"
          aria-live="assertive"
          aria-label={feedbackClass === 'success' ? 'Correct' : 'Incorrect'}
        >
          {feedbackClass === 'success' ? '✓' : '✗'}
        </span>
      )}
      {/* Metadata Section */}

      {mode !== GameMode.TEST ? (
        <div className="metadata">
          {/* THIS IS FOR DEBUGGING
        <span>{word.index}</span>
        */}
          <button
            className={`exclude-button ${word.is_included ? 'red' : 'green'}`}
            onClick={(e) => {
              stopPropagation(e);
              handleButtonClick(toggleExclusion);  // Disable all buttons and toggle exclusion
            }}
            disabled={loadingWord} // Disable button while loading a new word
          >
            {word.is_included ? 'Exclude' : 'Include'}
          </button>

          <div className="mastery-indicator">
            {loadingWord ? '⏳' : renderHistoryTiles(word)}
          </div>
        </div>) :
        (<></>)}

      {/* Hint Image Section */}
      <div className="hint-image-container"
        style={{ height: isHintDisplayed ? '85px' : '0px' }}
      >
        {isHintDisplayed ? (
          <>
            {loadingHint ? (
              <div className="loading-hint">Loading hint...</div>
            ) : (
              hintImage && (
                <div className="hint-image-wrapper">
                  <img src={`data:image/jpeg;base64,${hintImage}`} alt="Hint" className="hint-image" />
                  <button className="regenerate-hint-button" onClick={handleRegenerateHint} disabled={loadingWord}>🔄</button>
                </div>
              )
            )}
          </>
        ) : (<></>)}
      </div>

      <div onClick={mode === GameMode.TEST ? undefined : handleCardClick}
        className={`word-card-inner ${isFlipped ? 'flipped' : ''}`}
        style={{ height: isHintDisplayed ? '85px' : '170px' }}>
        <div
          className="word-card-front"
        >

          {loadingWord ?
            <p>⏳</p>
            :
            /* lexitrail#52 bug 3: the pronunciation control belongs only on the
               back (answer) card, not the front — hearing the word before you
               try to recall it defeats the prompt. Removed from the front here;
               kept on the back card below. */
            <p lang="zh" style={{ fontSize: calculateFontSize(word.word, isHintDisplayed ? 5 : 6) }}>{word.word}</p>
          }

        </div>
        <div className="word-card-back">
          {loadingWord ? '⏳ Loading...' :
            <div className="word-meaning">
              <div class="word-meaning-ref">
                <div class="word-meaning-ref-text" lang="zh">
                {word.word}
                </div>
                <SpeakButton text={word.word} size="md" />
              </div>
              <div class="word-meaning-def1">
                <p style={{ fontSize: calculateFontSize(word.def1, isHintDisplayed ? 6 : 7, 1.0) }}>
                  <PinyinText text={word.def1} />
                </p>
              </div>
              <div class="word-meaning-def2">
                <p className="word-translation" style={{ fontSize: calculateFontSize(word.def2, isHintDisplayed ? 6 : 8, 1.0) }}>
                  {removeQuotes(word.def2)}
                </p>
              </div>
            </div>
          }

        </div>
      </div>


      {
        mode !== GameMode.TEST ? (
          <div className="practice-buttons" onClick={stopPropagation}>
            <button onClick={onNotMemorized} disabled={loadingWord}>
              {loadingWord ? '⏳' : '❌'}
            </button>
            <button onClick={onMemorized} disabled={loadingWord}>
              {loadingWord ? '⏳' : '✔️'}
            </button>
          </div>
        )
          :
          (
            <div className="test-buttons" onClick={stopPropagation}>
              {[word.quiz_option1, word.quiz_option2, word.quiz_option3, word.quiz_option4].map((option, index) => (
                <button
                  key={index}
                  onClick={() => onQuizOptionClicked(option.correct)}
                  disabled={loadingWord}
                >
                  {loadingWord ? '⏳' : <PinyinText text={option.pinyin} />}
                </button>
              ))}
            </div>
          )
      }



    </div >
  );
};

export default WordCard;
