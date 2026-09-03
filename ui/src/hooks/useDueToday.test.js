import { loadDueToday } from './useDueToday';
import { getWordsets } from '../services/wordsService';
import { getUserWordsByWordset } from '../services/userService';
import { userwordsKey } from '../utils/wordsetCache';

// Factory mocks, not automocks: an automock still LOADS the real module to
// derive its shape, and `apiService` reads `window.config.API_BASE_URL` at
// import time, which is undefined under jest. The factory replaces the module
// outright so nothing in that chain executes.
jest.mock('../services/wordsService', () => ({ getWordsets: jest.fn() }));
jest.mock('../services/userService', () => ({ getUserWordsByWordset: jest.fn() }));

const DAY = 24 * 60 * 60 * 1000;
const ago = (ms) => new Date(Date.now() - ms).toISOString();

// A userword row in the shape `/userwords/query` ACTUALLY returns -- taken
// from the serializer in `backend/app/routes/userwords.py`, not from what the
// consumer happened to expect.
//
// 🔴 The first version of this factory used `recall_history` /
// `original_recall_time` (the MAPPED shape `useWordsetLoader` produces). That
// made every test here pass over a consumer that could not read the real
// payload at all: `lastRecallTimeOf` returned null for every live row, and
// `isDue(state, null)` is true, so the Today home counted every included word
// as due. The mock agreed with the code and both were wrong about the server.
const uw = (over = {}) => ({
  user_id: 'user-1',
  word_id: 1,
  is_included: true,
  recall_state: 2,
  recall_histories: [{ recall: true, recall_time: ago(30 * DAY),
                       new_recall_state: 2, old_recall_state: 3, is_included: true }],
  ...over,
});

beforeEach(() => {
  jest.clearAllMocks();
});

describe('loadDueToday', () => {
  it('totals due words ACROSS wordsets, not just the first', async () => {
    // The whole point: a per-wordset answer already exists in useWordsetLoader.
    // Two sets with due words must sum.
    getWordsets.mockResolvedValue({ data: [{ wordset_id: 7 }, { wordset_id: 9 }] });
    getUserWordsByWordset.mockImplementation((userId, wordsetId) =>
      Promise.resolve({ data: wordsetId === 7 ? [uw()] : [uw(), uw({ word_id: 2 })] })
    );

    await expect(loadDueToday('user-1')).resolves.toMatchObject({ total: 3 });
  });

  it('excludes opted-out and resting words from the total', async () => {
    getWordsets.mockResolvedValue({ data: [{ wordset_id: 1 }] });
    getUserWordsByWordset.mockResolvedValue({
      data: [
        uw(),                                    // due
        uw({ word_id: 2, is_included: false }),  // opted out -> never due
        uw({ word_id: 3, recall_state: 0,        // mastered, rested 1 day of 7
             recall_histories: [{ recall_time: ago(1 * DAY) }] }),
      ],
    });

    await expect(loadDueToday('user-1')).resolves.toMatchObject({ total: 1 });
  });

  it('REJECTS when a fetch fails, so the caller can show an error', async () => {
    // Load-bearing: resolving to 0 here would read as "you are all caught up".
    // A learner with reviews waiting would be told there is nothing to do and
    // would have no way to tell that from the truth. The hook turns this
    // rejection into status 'error', never into a total of 0.
    getWordsets.mockRejectedValue(new Error('network'));

    await expect(loadDueToday('user-1')).rejects.toThrow('network');
  });

  it('propagates a per-wordset failure instead of silently undercounting', async () => {
    // One set failing while others succeed is the subtler version of the same
    // trap: Promise.all rejects, so we surface an error rather than return a
    // total that is quietly missing a wordset.
    getWordsets.mockResolvedValue({ data: [{ wordset_id: 1 }, { wordset_id: 2 }] });
    getUserWordsByWordset.mockImplementation((userId, wordsetId) =>
      wordsetId === 2
        ? Promise.reject(new Error('boom'))
        : Promise.resolve({ data: [uw()] })
    );

    await expect(loadDueToday('user-1')).rejects.toThrow('boom');
  });

  it('does not fetch the word rows — only the userwords', async () => {
    // Pins the halved fan-out: `is_included`, `recall_state` and
    // `recall_history` all live on the userword, so a `getWordsByWordset` call
    // would be pure cost. Asserts the call COUNT, because an unused import is
    // not what costs a request.
    getWordsets.mockResolvedValue({ data: [{ wordset_id: 1 }, { wordset_id: 2 }] });
    getUserWordsByWordset.mockResolvedValue({ data: [uw()] });

    await loadDueToday('user-1');

    expect(getUserWordsByWordset).toHaveBeenCalledTimes(2);
    expect(getWordsets).toHaveBeenCalledTimes(1);
  });

  it('tolerates a wordset with no userwords, and an empty wordset list', async () => {
    // A newly added set the learner has never opened returns an empty list.
    getWordsets.mockResolvedValue({ data: [{ wordset_id: 1 }] });
    getUserWordsByWordset.mockResolvedValue({ data: [] });
    await expect(loadDueToday('user-1')).resolves.toMatchObject({ total: 0 });

    getWordsets.mockResolvedValue({ data: [] });
    await expect(loadDueToday('user-1')).resolves.toMatchObject({ total: 0 });
  });

  it('returns the per-set breakdown Start opens, keyed to the wordset', async () => {
    // issue-107: the total alone cannot drive Start -- the practice route is
    // `/game/:wordsetId/:mode`, so the home has to know WHICH set. Pinning the
    // id and description together because a breakdown carrying the count but
    // not the id would render a correct number over a Start that cannot fire.
    getWordsets.mockResolvedValue({
      data: [{ wordset_id: 7, description: 'HSK 1' }, { wordset_id: 9, description: 'HSK 2' }],
    });
    getUserWordsByWordset.mockImplementation((userId, wordsetId) =>
      Promise.resolve({ data: wordsetId === 7 ? [uw()] : [uw(), uw({ word_id: 2 })] })
    );

    await expect(loadDueToday('user-1')).resolves.toEqual({
      total: 3,
      sets: [
        { wordsetId: 7, description: 'HSK 1', due: 1 },
        { wordsetId: 9, description: 'HSK 2', due: 2 },
      ],
    });
  });

  it('tolerates a response with no data envelope rather than throwing', async () => {
    // Defensive on the shape, not on the network: a 204 or a changed envelope
    // should render "0 due", not blank the home screen with a TypeError.
    getWordsets.mockResolvedValue(undefined);
    await expect(loadDueToday('user-1')).resolves.toMatchObject({ total: 0 });
  });
});

// issue-335 — Today PUBLISHES its fan-out so the practice loader can reuse it.
// Measured on prod before this: `e2e/redundant_fetches.py` reported 13 data
// requests / 3 redundant (23%), and the three duplicated URLs were exactly the
// wordsets the journey opened while Today had fetched all seven.
describe('loadDueToday publishes userwords for reuse (issue-335)', () => {
  it('writes each wordset\'s rows into the shared cache under userwordsKey', async () => {
    const rows7 = [uw()];
    const rows9 = [uw(), uw({ word_id: 2 })];
    getWordsets.mockResolvedValue({ data: [{ wordset_id: 7 }, { wordset_id: 9 }] });
    getUserWordsByWordset.mockImplementation((userId, wordsetId) =>
      Promise.resolve({ data: wordsetId === 7 ? rows7 : rows9 }));

    const cache = {};
    await loadDueToday('user-1', cache);

    expect(cache[userwordsKey('user-1', 7)]).toEqual(rows7);
    expect(cache[userwordsKey('user-1', 9)]).toEqual(rows9);
  });

  it('publishes an EMPTY ARRAY, never undefined, for a wordset with no rows', async () => {
    // BUG SHAPE. The consumer treats a present key as "already fetched". If a
    // set with no userwords published `undefined`, the key would be present and
    // falsy, so the loader would refetch — reintroducing exactly the redundant
    // request this change removes, and only for the sets where it is cheapest
    // to get right.
    getWordsets.mockResolvedValue({ data: [{ wordset_id: 7 }] });
    getUserWordsByWordset.mockResolvedValue({ data: [] });

    const cache = {};
    await loadDueToday('user-1', cache);

    expect(cache[userwordsKey('user-1', 7)]).toEqual([]);
    expect(userwordsKey('user-1', 7) in cache).toBe(true);
  });

  it('still works with NO cache passed — the pure function stays window-free', async () => {
    getWordsets.mockResolvedValue({ data: [{ wordset_id: 7 }] });
    getUserWordsByWordset.mockResolvedValue({ data: [uw()] });
    await expect(loadDueToday('user-1')).resolves.toHaveProperty('total');
  });
});