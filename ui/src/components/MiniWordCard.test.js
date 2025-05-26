import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import MiniWordCard from './MiniWordCard';

// Mock PinyinText as it's a dependency and not relevant to this test
jest.mock('./PinyinText', () => ({ text }) => <>{text}</>);

describe('MiniWordCard', () => {
  // Mock window.speechSynthesis
  const mockSpeak = jest.fn();
  beforeAll(() => {
    // Ensure mocks from WordCard.test.js don't interfere if run in the same suite,
    // or define them robustly here if tests are separate.
    if (!global.speechSynthesis) {
      global.SpeechSynthesisUtterance = jest.fn();
      global.speechSynthesis = {
        speak: mockSpeak,
        cancel: jest.fn(),
        pause: jest.fn(),
        resume: jest.fn(),
        getVoices: jest.fn().mockReturnValue([]),
      };
    } else {
      // If already mocked (e.g. by WordCard.test.js in a shared context), ensure our mockSpeak is used
      global.speechSynthesis.speak = mockSpeak;
    }
    // If SpeechSynthesisUtterance is already mocked, reset its mock constructor if necessary
    if (global.SpeechSynthesisUtterance && global.SpeechSynthesisUtterance.mockClear) {
         global.SpeechSynthesisUtterance.mockClear();
    } else {
        global.SpeechSynthesisUtterance = jest.fn();
    }
  });

  beforeEach(() => {
    mockSpeak.mockClear();
    // Ensure SpeechSynthesisUtterance constructor is cleared before each test
    if (global.SpeechSynthesisUtterance && global.SpeechSynthesisUtterance.mockClear) {
        global.SpeechSynthesisUtterance.mockClear();
    } else {
        // If it was replaced by a simple jest.fn() and not a mock constructor
        global.SpeechSynthesisUtterance = jest.fn();
    }
  });

  const mockMiniWord = {
    user_id: 'user1', // Required by useEffect for loadingWord
    word_id: 'word1',   // Required by useEffect for loadingWord
    word: '再见',
    def1: 'zàijiàn',
    // other props if MiniWordCard uses them, but it primarily uses word and def1
  };

  const mockProps = {
    mode: 'some_mode', // MiniWordCard doesn't seem to use mode prop directly for speak button
    word: mockMiniWord,
  };

  test('renders the speak button and calls speechSynthesis.speak on click', () => {
    render(<MiniWordCard {...mockProps} />);

    // Find the speak button (using its text content 🔊)
    const speakButton = screen.getByText('🔊');
    expect(speakButton).toBeInTheDocument();

    // Simulate a click on the speak button
    fireEvent.click(speakButton);

    // Check if SpeechSynthesisUtterance was called with the word
    expect(global.SpeechSynthesisUtterance).toHaveBeenCalledTimes(1);
    expect(global.SpeechSynthesisUtterance).toHaveBeenCalledWith('再见');

    // Check if speechSynthesis.speak was called
    expect(mockSpeak).toHaveBeenCalledTimes(1);
    const utteranceInstance = global.SpeechSynthesisUtterance.mock.instances[0];
    expect(utteranceInstance.lang).toBe('zh-CN'); // Check if lang property was set
    expect(mockSpeak).toHaveBeenCalledWith(utteranceInstance);
  });

  test('speak button is present even if word.user_id or word.word_id is missing initially', () => {
    // Test that the button still renders if word IDs are initially missing,
    // as loadingWord state should affect disabled status, not presence.
    const wordWithoutId = { ...mockMiniWord, user_id: null, word_id: null };
    render(<MiniWordCard {...mockProps} word={wordWithoutId} />);

    // When word.user_id or word.word_id is missing, loadingWord remains true,
    // and the component should display the loading indicator.
    const loadingIndicator = screen.getByText('⏳');
    expect(loadingIndicator).toBeInTheDocument();

    // The speak button should NOT be present in this state
    const speakButton = screen.queryByText('🔊');
    expect(speakButton).not.toBeInTheDocument();
  });

  // MiniWordCard does not have an explicit loadingWord prop or complex state changes
  // that would make the button disabled in the same way as WordCard.
  // The loadingWord state is primarily set based on the presence of word.user_id and word.word_id
  // and is quickly set to false. The speak button's disabled state is tied to `loadingWord`.
  // The default state for loadingWord is true, and it is set to false in useEffect.
  // So, the button should generally be enabled once the component has processed useEffect.
});
