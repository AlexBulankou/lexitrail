// FEAT-1 pure-logic tests (react-scripts/jest).
import {
  emptyState,
  daysBetween,
  advance,
  currentStreak,
  todayProgress,
  goalMet,
} from './streak';

describe('streak util (FEAT-1)', () => {
  test('daysBetween counts whole days, null on bad input', () => {
    expect(daysBetween('2026-07-21', '2026-07-21')).toBe(0);
    expect(daysBetween('2026-07-21', '2026-07-22')).toBe(1);
    expect(daysBetween('2026-07-21', '2026-07-25')).toBe(4);
    expect(daysBetween(null, '2026-07-21')).toBeNull();
    expect(daysBetween('x', '2026-07-21')).toBeNull();
  });

  test('first practice starts a 1-day streak', () => {
    const s = advance(emptyState(), '2026-07-21');
    expect(s).toEqual({ lastDay: '2026-07-21', streak: 1, todayCount: 1 });
  });

  test('same-day practice bumps count, not streak', () => {
    let s = advance(emptyState(), '2026-07-21');
    s = advance(s, '2026-07-21');
    s = advance(s, '2026-07-21');
    expect(s.streak).toBe(1);
    expect(s.todayCount).toBe(3);
  });

  test('consecutive day increments streak and resets today count', () => {
    let s = advance(emptyState(), '2026-07-21');
    s = advance(s, '2026-07-21'); // 2 today
    s = advance(s, '2026-07-22'); // next day
    expect(s.streak).toBe(2);
    expect(s.todayCount).toBe(1);
    s = advance(s, '2026-07-23');
    expect(s.streak).toBe(3);
  });

  test('a missed day resets the streak to 1', () => {
    let s = advance(emptyState(), '2026-07-21');
    s = advance(s, '2026-07-22'); // streak 2
    s = advance(s, '2026-07-25'); // gap
    expect(s.streak).toBe(1);
    expect(s.todayCount).toBe(1);
  });

  test('currentStreak lapses to 0 after a skipped day', () => {
    const s = { lastDay: '2026-07-21', streak: 5, todayCount: 2 };
    expect(currentStreak(s, '2026-07-21')).toBe(5); // today
    expect(currentStreak(s, '2026-07-22')).toBe(5); // yesterday — still alive
    expect(currentStreak(s, '2026-07-23')).toBe(0); // lapsed
  });

  test('todayProgress + goalMet reflect only today', () => {
    const s = { lastDay: '2026-07-21', streak: 3, todayCount: 8 };
    expect(todayProgress(s, '2026-07-21')).toBe(8);
    expect(todayProgress(s, '2026-07-22')).toBe(0);
    expect(goalMet(s, '2026-07-21', 10)).toBe(false);
    expect(goalMet({ ...s, todayCount: 10 }, '2026-07-21', 10)).toBe(true);
  });
});
