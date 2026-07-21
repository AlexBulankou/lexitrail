// FEAT-3 pure-logic tests for the Web Speech pronunciation helper.
// Runs under CRA's `react-scripts test` (jest + jsdom); mocks the speech API.
import { isSpeechSupported, speakChinese, DEFAULT_RATE } from './speak';

describe('speak util (FEAT-3)', () => {
  let spoken;
  let cancelled;

  beforeEach(() => {
    spoken = [];
    cancelled = 0;
    // Minimal Web Speech API mock.
    window.SpeechSynthesisUtterance = function (text) {
      this.text = text;
    };
    window.speechSynthesis = {
      speak: (u) => spoken.push(u),
      cancel: () => { cancelled += 1; },
      getVoices: () => [
        { lang: 'en-US', name: 'English' },
        { lang: 'zh-CN', name: 'Mandarin' },
      ],
    };
  });

  afterEach(() => {
    delete window.SpeechSynthesisUtterance;
    delete window.speechSynthesis;
  });

  test('isSpeechSupported reflects API presence', () => {
    expect(isSpeechSupported()).toBe(true);
    delete window.speechSynthesis;
    expect(isSpeechSupported()).toBe(false);
  });

  test('speakChinese dispatches a zh-CN utterance with the learner rate', () => {
    const ok = speakChinese('你好');
    expect(ok).toBe(true);
    expect(spoken).toHaveLength(1);
    expect(spoken[0].text).toBe('你好');
    expect(spoken[0].lang).toBe('zh-CN');
    expect(spoken[0].rate).toBe(DEFAULT_RATE);
  });

  test('cancels any in-flight speech before speaking (no overlap)', () => {
    speakChinese('一');
    speakChinese('二');
    expect(cancelled).toBe(2);
    expect(spoken).toHaveLength(2);
  });

  test('picks a Mandarin voice when available', () => {
    speakChinese('中文');
    expect(spoken[0].voice).toEqual({ lang: 'zh-CN', name: 'Mandarin' });
  });

  test('empty/whitespace text is a no-op', () => {
    expect(speakChinese('   ')).toBe(false);
    expect(speakChinese('')).toBe(false);
    expect(spoken).toHaveLength(0);
  });

  test('unsupported browser → no-op, no throw', () => {
    delete window.speechSynthesis;
    expect(speakChinese('你好')).toBe(false);
  });
});
