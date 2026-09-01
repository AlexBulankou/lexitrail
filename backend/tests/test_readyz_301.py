"""Pins that readiness DEPENDS on the database and liveness does NOT (issue-301).

#301: one replica returned 500 on every database-backed request for ~26 minutes
while `/health` answered 200 throughout, because `/health` returns a literal. Both
the readiness and liveness probes pointed at it, so Kubernetes neither took the pod
out of rotation nor restarted it -- both self-healing mechanisms disabled by one
line.

🔴 `test_readyz_reports_not_ready_when_the_database_is_unreachable` is the
load-bearing assertion. Every other test here would still pass if `/readyz` were
"simplified" back into a literal, and the endpoint would then report ready for the
rest of its life without ever looking at a database -- the exact defect it exists
to fix, reintroduced inside the fix for it.

`test_health_does_not_touch_the_database` is its counterweight and is NOT
redundant: making /health DB-dependent would fix #301's symptom and create a worse
bug, because a DB-dependent LIVENESS probe restarts every replica during a brief
blip. The design is that these two endpoints disagree under exactly one condition.
"""
import unittest
from unittest.mock import patch

from app import create_app
from app.config import TestConfig


class _NoDbConfig(TestConfig):
    """sqlite in-memory: these tests never execute real SQL.

    Deliberately NOT `tests.utils.setup_test_app`, which downloads a schema from
    GCS and needs a live MySQL. Every assertion here is about what the endpoints
    do with the RESULT of `db.session.execute`, which is mocked in the cases that
    matter -- so requiring real infrastructure would buy nothing and would make
    these unrunnable outside the cluster.
    """
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


class ReadyzTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = create_app(_NoDbConfig)
        cls.client = cls.app.test_client()

    def test_readyz_is_200_when_the_database_answers(self):
        resp = self.client.get('/readyz')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['status'], 'ready')

    def test_readyz_reports_not_ready_when_the_database_is_unreachable(self):
        """🔴 The one that matters -- the negative direction.

        Asserting only that /readyz returns 200 when healthy would be satisfied by
        the literal `/health` this issue is about. The check only means something
        if 503 is a value it can actually produce.
        """
        with patch('app.routes.db.session.execute',
                   side_effect=OSError("Can't connect to MySQL server (timed out)")):
            resp = self.client.get('/readyz')
        self.assertEqual(resp.status_code, 503)
        body = resp.get_json()
        self.assertEqual(body['status'], 'not-ready')
        self.assertIn('MySQL', body['reason'])

    def test_health_does_not_touch_the_database(self):
        """Liveness must stay DB-independent.

        If this ever starts failing alongside /readyz, a brief DB blip will restart
        every replica at once -- strictly worse than the bug in #301.
        """
        with patch('app.routes.db.session.execute',
                   side_effect=OSError("Can't connect to MySQL server (timed out)")):
            resp = self.client.get('/health')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['status'], 'healthy')

    def test_readyz_and_health_are_distinct_endpoints(self):
        """Collapsing them into one is the failure mode, in either direction."""
        with patch('app.routes.db.session.execute',
                   side_effect=OSError("db down")):
            self.assertEqual(self.client.get('/health').status_code, 200)
            self.assertEqual(self.client.get('/readyz').status_code, 503)


if __name__ == '__main__':
    unittest.main()
