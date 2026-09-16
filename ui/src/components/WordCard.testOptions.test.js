// uibug 2026-09-16 — the size class REACHES the TEST-mode option buttons.
//
// quizOptionSize.test.js pins the length→class mapping; this file pins the
// wiring — WordCard actually applies the mapping to each `.test-buttons`
// button. Without this, deleting the `quizOptionSizeClass(...)` call from the
// className would pass every pure test while re-clipping every long option.
//
// Rendered with @testing-library (present since the SUG work), TEST mode,
// hints off so the hint effect takes its early-return and no network is
// touched. jsdom does no layout, so the box itself is proven by the harness
// sweep — here we assert the class names, which are the fix's contract with
// WordCard.css.
import React from 'react';
import { render, screen } from '@testing-library/react';

// Both mocks are about the IMPORT GRAPH, not behavior. hintService →
// apiService reads `window.config` at module top level and pulls in axios,
// whose ESM entry CRA's jest does not transform; Game.js drags in the loader
// hooks and services the same way. WordCard only takes `getHint`/
// `regenerateHint` (never called here: hints are off) and the GameMode enum.
jest.mock('../services/hintService', () => ({
  getHint: jest.fn(),
  regenerateHint: jest.fn(),
}));
jest.mock('./Game', () => ({
  GameMode: {
    PRACTICE: 'PRACTICE',
    SHOW_EXCLUDED: 'SHOW_EXCLUDED',
    TEST: 'TEST',
    DUE_TODAY: 'DUE_TODAY',
  },
}));

import WordCard from './WordCard';
import { GameMode } from './Game';

const opt = (pinyin, correct = false) => ({ pinyin, correct });

const word = {
  user_id: 'test@example.com',
  word_id: 42,
  word: '打电话',
  def1: 'dǎdiànhuà',
  def2: 'to make a phone call',
  quiz_option1: opt('dǎdiànhuà', true), // 9 chars — the worst live clip (90px vs 67px)
  quiz_option2: opt('zěnmeyàng'),       // 9 chars — 95px vs 67px, rendered 'nmeyà' live
  quiz_option3: opt('wǒmen'),           // 5 chars — 73px vs 67px, lost first+last letter
  quiz_option4: opt('sì'),              // short — must stay exactly as before
};

const noop = () => {};

const renderTestCard = () =>
  render(
    <WordCard
      mode={GameMode.TEST}
      word={word}
      isFlipped={false}
      isHintDisplayed={false}
      handleMemorized={noop}
      handleNotMemorized={noop}
      toggleExclusion={noop}
      feedbackClass=""
      provideFeedback={noop}
      setFlippedState={noop}
    />
  );

// PinyinText renders one <span> per character, so the computed accessible name
// carries a space between every character ("d ǎ d i à n h u à"); textContent
// is the label as the reader sees it, so the lookup keys on that.
const optionButton = (pinyin) => {
  const match = screen
    .getAllByRole('button')
    .filter((b) => b.textContent === pinyin);
  expect(match).toHaveLength(1);
  return match[0];
};

describe('uibug 2026-09-16 — TEST-mode options carry their length-step class', () => {
  test('long options get the step their length maps to', () => {
    renderTestCard();
    expect(optionButton('dǎdiànhuà')).toHaveClass('test-option-xs');
    expect(optionButton('zěnmeyàng')).toHaveClass('test-option-xs');
    expect(optionButton('wǒmen')).toHaveClass('test-option-md');
  });

  test('a short option is untouched: no size class at all', () => {
    renderTestCard();
    expect(optionButton('sì').className).toBe('');
  });
});
