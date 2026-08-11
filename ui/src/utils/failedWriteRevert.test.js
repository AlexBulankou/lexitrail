import { revertWordWrite } from './failedWriteRevert';

const w = (id, extra = {}) => ({ word_id: id, word: `w${id}`, recall_state: 0, is_included: true, ...extra });

describe('revertWordWrite (lexitrail#45 R3-BUG-3)', () => {
  test('restores the server-owned fields of the word that failed', () => {
    const prior = w(2);
    const current = [w(1), w(2, { recall_state: 3, is_included: false }), w(3)];
    const out = revertWordWrite(current, prior);
    expect(out[1].recall_state).toBe(0);
    expect(out[1].is_included).toBe(true);
  });

  test('re-appends the word when the optimistic path removed it', () => {
    // removeWordAtIndex=true drops it, so a revert that only patches in place
    // would leave the learner with no way to see or redo the action.
    const prior = w(2);
    const out = revertWordWrite([w(1), w(3)], prior);
    expect(out.map((x) => x.word_id)).toEqual([1, 3, 2]);
    expect(out[2].recall_state).toBe(0);
  });

  // 🔴 BUG SHAPE — the regression a naive repair ships.
  test('keys on word_id, NOT on the index the write was issued at', () => {
    // The reorder moves words, so by the time the PUT rejects, the original
    // index routinely holds a DIFFERENT word. An index-keyed revert would
    // restore that innocent word's fields -- manufacturing a second divergence
    // while appearing to fix the first.
    const prior = w(2);                       // issued when w2 sat at index 0
    const current = [
      w(9, { recall_state: 4, is_included: false }),  // index 0 now holds w9
      w(2, { recall_state: 3, is_included: false }),
    ];
    const out = revertWordWrite(current, prior);
    expect(out[0].recall_state).toBe(4);      // w9 UNTOUCHED
    expect(out[0].is_included).toBe(false);
    expect(out[1].recall_state).toBe(0);      // w2 restored
  });

  test('does not mutate its input', () => {
    const current = [w(1), w(2, { recall_state: 3 })];
    const snapshot = JSON.stringify(current);
    revertWordWrite(current, w(2));
    expect(JSON.stringify(current)).toBe(snapshot);
  });

  test('leaves unrelated words alone, including concurrent edits', () => {
    // A revert must not clobber a change the learner made while the PUT was
    // in flight -- which is why this patches one word rather than restoring a
    // whole pre-write snapshot of the list.
    const current = [w(1, { recall_state: 7 }), w(2, { recall_state: 3 })];
    const out = revertWordWrite(current, w(2));
    expect(out[0].recall_state).toBe(7);
  });

  test.each([
    ['null list', null, w(1)],
    ['undefined prior', [w(1)], undefined],
    ['prior without word_id', [w(1)], { recall_state: 0 }],
  ])('%s returns something renderable rather than throwing', (_label, words, prior) => {
    // A revert helper that throws converts a failed write into a crashed
    // render -- strictly worse than the bug it is fixing.
    expect(() => revertWordWrite(words, prior)).not.toThrow();
    expect(Array.isArray(revertWordWrite(words, prior))).toBe(true);
  });
});
