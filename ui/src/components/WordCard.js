import React, { useState, useEffect, useRef } from 'react';
import { getHint, regenerateHint } from '../services/hintService';
import { correctOption, shouldReveal, REVEAL_MS } from '../utils/quizReveal';
import { GameMode } from './Game';
import PinyinText from './PinyinText';
import SpeakButton from './SpeakButton';
import { buildHistoryTiles } from '../utils/historyTiles';
import '../styles/WordCard.css';

const WordCard = ({ mode, word, isFlipped, isHintDisplayed, handleMemorized, handleNotMemorized, toggleExclusion, feedbackClass, provideFeedback, setFlippedState }) => {
  const [hintImage, setHintImage] = useState(null);
  // issue-344: the correct option, held only while a wrong answer is being
  // revealed. null = not revealing, which is also the state a card with no
  // flagged correct option stays in (see quizReveal.correctOption).
  const [revealed, setRevealed] = useState(null);
  const revealTimer = useRef(null);

  // issue-344: cancel an in-flight reveal when THIS SLOT's word changes, and on
  // unmount.
  //
  // 🔴 NOT DEFENSIVE — this path is reachable today, and hc2@ found it on review
  // while describing it as hypothetical. `Game.js:487` keys WordCard on
  // `key={index}`, the SLOT, not on the word (issue-137 documents that choice).
  // So when a reveal's timer fires and removes its word, `wordsToRender` shrinks,
  // every later slot receives a DIFFERENT word, and React reuses the instance
  // rather than remounting it.
  //
  // Test mode shows several cards at once and `revealed` is card-local, so a
  // neighbour's buttons stay enabled while this card reveals. Answer two cards in
  // quick succession and the second card can inherit a new word with the previous
  // word's reveal still set. Two consequences, both real:
  //
  //   1. the highlight keys on the NEW word's `option.correct`, so it hands the
  //      learner that word's answer for free, unanswered
  //   2. the pending timer calls `handleNotMemorized()` for a word nobody
  //      answered, writing a recall the learner never earned
  //
  // Clearing the timer is the half that matters; `setRevealed(null)` alone would
  // stop the highlight and still fire the write.
  useEffect(() => {
    return () => {
      if (revealTimer.current) {
        clearTimeout(revealTimer.current);
        revealTimer.current = null;
      }
    };
  }, [word.word_id]);

  // `setFlippedState` is a fresh closure each render (Game.js binds the slot into
  // it), so it is held on a ref rather than listed as a dep -- listing it would
  // re-run this on every render and clear a reveal the instant it started.
  const setFlippedRef = useRef(setFlippedState);
  setFlippedRef.current = setFlippedState;

  useEffect(() => {
    setRevealed(null);
    // Un-flip too: `isFlipped` is the PARENT's state, keyed on the slot
    // (`flippedStates[index]`), so a card left flipped when its word changes
    // would show the NEW word's back face -- its meaning -- unprompted. Same
    // leak as the highlight, one prop up.
    setFlippedRef.current(false);
  }, [word.word_id]);
  // lexitrail#265: the `hintText` state, its setters and its caption are all DELETED, not
  // left unread. #193 added them believing `hint_text` was an AI etymology; it is the Gemini
  // image PROMPT (see the note at the render site). Keeping the state would leave the leak one
  // line of JSX from live again — the same reason issue-109 deleted rather than hid its control.
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
    const options = [word.quiz_option1, word.quiz_option2, word.quiz_option3, word.quiz_option4];

    // issue-344: a wrong answer used to mark the word missed and advance, so the
    // learner never saw which option was right or what the word meant. Reveal
    // first, then advance -- the moment after a failed retrieval is the one with
    // the most learning value in the session.
    //
    // A CORRECT pick is deliberately untouched: same call, same timing. The
    // reveal shares `provideFeedback` with the success path, so slowing that
    // branch would tax the common case (`shouldReveal` pins this).
    if (!shouldReveal(isCorrect, options)) {
      provideFeedback(isCorrect, () => {
        if (isCorrect) {
          handleMemorized();
        } else {
          handleNotMemorized();
        }
      });
      return;
    }

    setRevealed(correctOption(options));
    // The back face carries `.word-meaning` and IS rendered in TEST mode -- only
    // the click-to-flip handler is gated on mode -- so flipping shows the meaning
    // without any new markup.
    setFlippedState(true);

    // Stored on the ref so unmount can clear it. Advancing a card that has left
    // the DOM is the #90 hang shape one layer down: the callback would call
    // `handleNotMemorized` for a slot the loader has already moved past.
    revealTimer.current = setTimeout(() => {
      revealTimer.current = null;
      setRevealed(null);
      setFlippedState(false);
      provideFeedback(false, () => handleNotMemorized());
    }, REVEAL_MS);
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
    const { tiles, correct, bulk, total } = buildHistoryTiles(w.recall_history);
    if (total === 0) {
      return <span className="history-empty">New</span>;
    }
    return (
      <div
        className="history-tiles"
        role="img"
        // #109: the bulk count is appended ONLY when it is non-zero, i.e. only
        // when we positively know some greens were a "to all" tap. A history of
        // unknown provenance (every row written before the column existed) says
        // nothing new here rather than being described either way.
        aria-label={`Past answers: ${correct} correct of ${total}` +
          (bulk ? `, ${bulk} from the "to all" shortcut` : '')}
      >
        {tiles.map((t, i) => (
          <span
            key={i}
            className={`history-tile ${t.correct ? 'correct' : 'wrong'}` +
              (t.provenance === 'bulk' ? ' bulk' : '')}
            title={`${t.correct ? 'Correct' : 'Wrong'}` +
              (t.provenance === 'bulk' ? ' · marked by the "to all" shortcut'
                : t.provenance === 'single' ? ' · answered card by card' : '') +
              (t.time ? ' · ' + t.time : '')}
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
          {/* issue-144: a STABLE accessible name, unlike the visible text.
              The two recall buttons above already have one (issue-52: "the
              aria-label, not the emoji, is the accessible name"); this
              control kept the flipping text as its only handle, so anything
              referring to it by name -- a test, a script, a spoken
              instruction -- had to know the word's state first. It also made
              the control invisible to the obvious search: grepping this file
              for `aria-label` returned two hits, and I concluded the
              exclusion path was undrivable from a session. It was not.
              The VISIBLE text still flips; that is what it is for. */}
          <button
            aria-label="Toggle whether this word is in your practice set"
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
                  <button className="regenerate-hint-button" onClick={handleRegenerateHint}
                          disabled={loadingWord} aria-label="Regenerate hint image">🔄</button>
                </div>
              )
            )}
          </>
        ) : (<></>)}
      </div>

      {/* lexitrail#265 — THE CAPTION IS REMOVED. #193 added it believing `hint_text` was
          "an AI etymology/mnemonic ... free depth, already paid for, currently discarded".
          It is not. `hint_generation.py:256` sets it to the Gemini IMAGE-GENERATION PROMPT
          verbatim (`'hint_text': _clean_text(prompt)`), so the caption rendered internal
          prompt text straight into the learner-facing UI (Alex, 2026-08-29).

          🔴 Not merely untidy: `generate_prompt` instructs the model that the prompt "should
          be subtle and not directly reveal the word's meaning" — it is a DESCRIPTION OF THE
          PICTURE, so showing it in text both leaks internals AND hands over the hint the
          image exists to make you work for.

          The prompt is stripped at the PRODUCER too (it no longer ships in the payload), per
          Alex's instruction — a renderer-only fix leaves the next surface to leak it again.
          Deleted rather than hidden, for the same reason issue-109's control was. */}

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
            {/* issue-52: aria-label, not the emoji, is the accessible name.
                Without it the name is "❌"/"✔️" — and it CHANGES to "⏳" while
                loading, so any name-keyed selector breaks intermittently. */}
            <button onClick={onNotMemorized} disabled={loadingWord}
                    aria-label="Mark as not memorized">
              {loadingWord ? '⏳' : '❌'}
            </button>
            <button onClick={onMemorized} disabled={loadingWord}
                    aria-label="Mark as memorized">
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
                  /* issue-344: while revealing, the correct option is marked so
                     the learner can SEE which one it was. Keyed on the option's
                     own `correct` flag rather than on identity, so it cannot
                     highlight a different button than the one that was scored. */
                  className={revealed && option && option.correct ? 'quiz-option-correct' : undefined}
                  onClick={() => onQuizOptionClicked(option.correct)}
                  disabled={loadingWord || revealed !== null}
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
