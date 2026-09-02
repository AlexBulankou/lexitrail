"""Pins that a cache HIT can say so (issue-215).

`cache_status` is set in exactly one place -- the compute path -- and the hit
path used to return the stored response verbatim. So the field a reader reaches
for to answer *"is the cache working?"* reported `miss` on every hit, forever,
beside timings describing a computation minutes old. Measured in production on
2026-09-02: two wordsets served in 0.24s and 0.29s while reporting
`processing_time_ms` of 2827 and 4933 and `cache_status: "miss"`.

🔴 `test_origin_timings_do_not_stay_at_the_top_level` is the load-bearing
assertion. Setting `cache_status: "hit"` while leaving `total_time_ms` beside it
would satisfy the issue's title and leave the actual defect in place -- a stale
duration presented as a statement about the request that just happened. Every
other test here passes on that half-fix.

🔴 `test_a_hit_does_not_mutate_the_cached_object` is the second. Relabelling in
place would rewrite the cached dict, and the SECOND hit would then nest `origin`
inside `origin` -- a corruption that the first hit's test cannot see.
"""
import time
import unittest

from app.routes.wordsets import _as_cache_hit


def _stored():
    """The shape the compute path stores, with the real field names."""
    return {
        'success': True,
        'data': [{'word_id': 1, 'word': 'x'}],
        'metadata': {
            'query': 'SELECT ...',
            'query_time_ms': 12.0,
            'processing_time_ms': 2827.12,
            'total_time_ms': 2839.12,
            'num_workers': 1,
            'words_processed': 1,
            'cache_status': 'miss',
        },
    }


class CacheHitMetadataTests(unittest.TestCase):

    def test_a_hit_reports_hit(self):
        out = _as_cache_hit(_stored(), time.time())
        self.assertEqual(out['metadata']['cache_status'], 'hit')

    def test_origin_timings_do_not_stay_at_the_top_level(self):
        """🔴 The half-fix -- relabel and leave the stale numbers -- must fail."""
        out = _as_cache_hit(_stored(), time.time())
        md = out['metadata']
        for stale in ('total_time_ms', 'processing_time_ms', 'query_time_ms'):
            self.assertNotIn(
                stale, md,
                f"{stale} describes the ORIGINAL computation; beside "
                f"cache_status:'hit' it reads as this request's duration",
            )

    def test_origin_is_preserved_rather_than_discarded(self):
        """Moved, not deleted -- how expensive the warm was is worth keeping."""
        out = _as_cache_hit(_stored(), time.time())
        self.assertEqual(out['metadata']['origin']['total_time_ms'], 2839.12)
        self.assertEqual(out['metadata']['origin']['query'], 'SELECT ...')

    def test_origin_does_not_carry_its_own_stale_cache_status(self):
        """`origin.cache_status: 'miss'` is the same trap one level down."""
        out = _as_cache_hit(_stored(), time.time())
        self.assertNotIn('cache_status', out['metadata']['origin'])

    def test_served_time_describes_THIS_request(self):
        """The number beside `hit` must be small, not the 2827ms warm."""
        out = _as_cache_hit(_stored(), time.time() - 0.05)
        served = out['metadata']['served_time_ms']
        self.assertGreater(served, 0)
        self.assertLess(served, 1000, "served_time_ms must not be the origin's")

    def test_a_hit_does_not_mutate_the_cached_object(self):
        """🔴 The cache holds the response dict itself. Relabelling in place
        would make the SECOND hit nest origin inside origin."""
        stored = _stored()
        first = _as_cache_hit(stored, time.time())
        self.assertEqual(stored['metadata']['cache_status'], 'miss',
                         "the cached object must be untouched")
        second = _as_cache_hit(stored, time.time())
        self.assertNotIn('origin', second['metadata']['origin'])
        self.assertIsNot(first['metadata'], second['metadata'])

    def test_the_payload_is_carried_through_unchanged(self):
        out = _as_cache_hit(_stored(), time.time())
        self.assertEqual(out['data'], [{'word_id': 1, 'word': 'x'}])
        self.assertIs(out['success'], True)

    def test_missing_metadata_still_reports_the_hit(self):
        """A stored response with no metadata must not lose the hit signal --
        reporting `hit` is the whole point of the change."""
        out = _as_cache_hit({'success': True, 'data': []}, time.time())
        self.assertEqual(out['metadata']['cache_status'], 'hit')
        self.assertIsNone(out['metadata']['origin'])

    def test_a_non_dict_cache_entry_is_handed_back_untouched(self):
        """Do not dress up something we do not understand as a hit."""
        sentinel = ['not', 'a', 'response']
        self.assertIs(_as_cache_hit(sentinel, time.time()), sentinel)


if __name__ == '__main__':
    unittest.main()
