// FEAT-9 pure-logic tests (react-scripts/jest). No network — buildIndex +
// selectExamples are pure; getExamples is covered with a mocked fetch.
import {
  buildIndex,
  selectExamples,
  getExamples,
  _resetCache,
} from './sentencesService';

const SAMPLE = [
  { w: '阿姨', zh: '阿姨在家吗？', py: 'Āyí zài jiā ma?', en: 'Is aunt at home?' },
  { w: '阿姨', zh: '我和阿姨去商店。', py: 'Wǒ hé āyí qù shāngdiàn.', en: 'I go to the store with aunt.' },
  { w: '阿姨', zh: 'third', py: 'p', en: 'e' },
  { w: '您', zh: '您是老师吗？', py: 'Nín shì lǎoshī ma?', en: 'Are you a teacher?' },
  { w: '', zh: 'skip-empty-word', py: '', en: '' },
];

describe('sentencesService (FEAT-9)', () => {
  test('buildIndex groups by word and skips empty-word rows', () => {
    const idx = buildIndex(SAMPLE);
    expect(Object.keys(idx).sort()).toEqual(['您', '阿姨']);
    expect(idx['阿姨']).toHaveLength(3);
    expect(idx['']).toBeUndefined();
  });

  test('buildIndex tolerates null/empty input', () => {
    expect(buildIndex(null)).toEqual({});
    expect(buildIndex([])).toEqual({});
  });

  test('selectExamples returns up to limit, in order', () => {
    const idx = buildIndex(SAMPLE);
    const two = selectExamples(idx, '阿姨', 2);
    expect(two).toHaveLength(2);
    expect(two[0].zh).toBe('阿姨在家吗？');
    expect(selectExamples(idx, '阿姨', 5)).toHaveLength(3);
  });

  test('selectExamples: unknown word / blank / null index → []', () => {
    const idx = buildIndex(SAMPLE);
    expect(selectExamples(idx, '不存在')).toEqual([]);
    expect(selectExamples(idx, '  ')).toEqual([]);
    expect(selectExamples(null, '阿姨')).toEqual([]);
  });

  test('getExamples fetches once, indexes, and returns matches', async () => {
    _resetCache();
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ sentences: SAMPLE }),
    });
    const ex = await getExamples('您', 2);
    expect(ex).toHaveLength(1);
    expect(ex[0].en).toBe('Are you a teacher?');
    // second call reuses the cached index (no second fetch)
    await getExamples('阿姨', 2);
    expect(global.fetch).toHaveBeenCalledTimes(1);
    delete global.fetch;
  });

  test('getExamples: failed fetch → [] and no throw', async () => {
    _resetCache();
    global.fetch = jest.fn().mockRejectedValue(new Error('offline'));
    await expect(getExamples('您')).resolves.toEqual([]);
    delete global.fetch;
  });
});
