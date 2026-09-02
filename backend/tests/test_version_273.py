"""Pins /version's THREE-state contract (issue-273 step 1).

`/version` exists so a credential-free detector can answer "is production built
from the newest commit that should have deployed it?" -- see
`scripts/check_deploy_current.py`. Every credential on bp is PERMISSION_DENIED
against lexitrail's Artifact Registry and its build list (#224), so comparing the
deployed image tag to the newest build is not implementable from any seat we have.

🔴 `test_unset_build_sha_is_null_and_known_false` is the load-bearing assertion.
An image built by hand, or any image predating this change, carries no BUILD_SHA.
If that returned `sha: ""` a consumer could read it as equal-to-nothing or as
falsy-so-no-drift, and the detector would be blind for exactly as long as an old
image keeps running -- which is the failure #273 is about, reintroduced inside
the fix for it. Unset is a third state and must be unmistakable.
"""
import os
import unittest
from unittest.mock import patch

from app import create_app
from app.config import TestConfig


class _NoDbConfig(TestConfig):
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


class VersionEndpointTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = create_app(_NoDbConfig)
        cls.client = cls.app.test_client()

    def test_baked_sha_is_reported_with_known_true(self):
        with patch.dict(os.environ, {'BUILD_SHA': 'e0986fc'}):
            body = self.client.get('/version').get_json()
        self.assertEqual(body['sha'], 'e0986fc')
        self.assertIs(body['known'], True)

    def test_unset_build_sha_is_null_and_known_false(self):
        env = {k: v for k, v in os.environ.items() if k != 'BUILD_SHA'}
        with patch.dict(os.environ, env, clear=True):
            body = self.client.get('/version').get_json()
        self.assertIsNone(body['sha'], "unset must be null, never an empty string")
        self.assertIs(body['known'], False)

    def test_whitespace_only_build_sha_is_treated_as_unset(self):
        """A docker --build-arg that resolved to nothing arrives as spaces, and a
        whitespace sha would compare unequal to every real one -- reporting
        permanent drift rather than the honest 'I do not know'."""
        with patch.dict(os.environ, {'BUILD_SHA': '   '}):
            body = self.client.get('/version').get_json()
        self.assertIsNone(body['sha'])
        self.assertIs(body['known'], False)

    def test_version_is_200_in_both_states(self):
        """It answers a question about itself, so it must not need the database
        and must not 503 -- a detector cannot distinguish 'down' from 'stale'."""
        for env in ({'BUILD_SHA': 'abc1234'}, {'BUILD_SHA': ''}):
            with patch.dict(os.environ, env):
                self.assertEqual(self.client.get('/version').status_code, 200)


if __name__ == '__main__':
    unittest.main()
