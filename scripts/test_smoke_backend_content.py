"""Pins the THREE-state contract of the backend content smoke (issue-77 AC3).

The live run in #301 proved this instrument discriminates today: it returned FAIL
against a genuinely broken production state and PASS against the fixed one, ten
minutes apart, unchanged in between. This file exists so it cannot silently stop.

The load-bearing assertions are `test_dead_control_is_cannot_tell_not_pass` and
`test_empty_data_list_is_a_failure`. Every other check here would still pass if
someone "simplified" the control away or relaxed the non-empty requirement, and
the resulting smoke would then report a healthy deploy for the rest of its life
without ever looking at one -- which is the failure #77 was filed about,
reintroduced inside the fix for it.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import urllib.error
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent / "smoke_backend_content.py"
_spec = importlib.util.spec_from_file_location("smoke_backend_content", _SRC)
smoke = importlib.util.module_from_spec(_spec)
sys.modules["smoke_backend_content"] = smoke
_spec.loader.exec_module(smoke)

JSON_CT = "application/json"
HTML_CT = "text/html; charset=utf-8"
ROWS = json.dumps({"data": [{"wordset_id": 1, "description": "HSK1"}]}).encode()


def _http_error(code: int, ctype: str = HTML_CT):
    """What the live host does on an unknown path.

    `urllib` RAISES on 4xx, and `HTTPError` is a SUBCLASS of `URLError` -- which is
    how "404 as designed" and "the host did not answer" can come to share one
    branch. Tests raise the real class so that ordering is genuinely exercised.
    """
    class _H:
        @staticmethod
        def get(_k, _d=None):
            return ctype

    err = urllib.error.HTTPError("https://x.test/x", code, "err", hdrs=None, fp=None)
    err.headers = _H()
    return err


def _fetches(mapping, default=None):
    """Build a `_fetch` stub keyed on the path suffix of the requested URL."""

    def _f(url, timeout=20.0):
        for suffix, result in mapping.items():
            if url.endswith(suffix):
                if isinstance(result, Exception):
                    raise result
                return result
        if default is None:
            raise AssertionError(f"unexpected fetch: {url}")
        if isinstance(default, Exception):
            raise default
        return default

    return _f


@pytest.fixture()
def repo(tmp_path):
    src = tmp_path / "backend" / "app" / "routes"
    src.mkdir(parents=True)
    (src / "wordsets.py").write_text(
        "bp = Blueprint('wordsets', __name__, url_prefix='/wordsets')\n"
    )
    return tmp_path


def _run(monkeypatch, repo, fetch):
    monkeypatch.setattr(smoke, "_fetch", fetch)
    return smoke.main(["--base", "https://x.test", "--repo-root", str(repo)])


def test_healthy_backend_passes(monkeypatch, repo):
    rc = _run(monkeypatch, repo, _fetches({
        smoke.CONTROL_PATH: _http_error(404),
        "/wordsets": (200, JSON_CT, ROWS),
    }))
    assert rc == smoke.PASS


def test_dead_control_is_cannot_tell_not_pass(monkeypatch, repo):
    """🔴 The one that matters.

    If an unknown path starts answering 200, `application/json` stops being a
    value this host can fail to return -- so the content-type assertion would
    pass for free, forever. That MUST be CANNOT-TELL, never PASS: a smoke whose
    instrument has died looks exactly like a healthy deploy.
    """
    rc = _run(monkeypatch, repo, _fetches({
        smoke.CONTROL_PATH: (200, JSON_CT, b"{}"),
        "/wordsets": (200, JSON_CT, ROWS),
    }))
    assert rc == smoke.CANNOT_TELL


def test_control_404_in_json_is_cannot_tell(monkeypatch, repo):
    """A 404 is not enough on its own -- it must not be a JSON 404.

    A JSON error handler in front of the app would 404 correctly and still
    destroy the discriminator, because the check below asserts JSON.
    """
    rc = _run(monkeypatch, repo, _fetches({
        smoke.CONTROL_PATH: _http_error(404, ctype=JSON_CT),
        "/wordsets": (200, JSON_CT, ROWS),
    }))
    assert rc == smoke.CANNOT_TELL


def test_unreachable_host_is_cannot_tell_not_fail(monkeypatch, repo):
    """"The host did not answer" is not "the deploy shipped bad content"."""
    rc = _run(monkeypatch, repo, _fetches({
        smoke.CONTROL_PATH: urllib.error.URLError("no route"),
    }))
    assert rc == smoke.CANNOT_TELL


def test_500_on_the_route_is_a_failure(monkeypatch, repo):
    """The exact live state of #301: the route is declared but 500s."""
    rc = _run(monkeypatch, repo, _fetches({
        smoke.CONTROL_PATH: _http_error(404),
        "/wordsets": _http_error(500),
    }))
    assert rc == smoke.FAIL


def test_empty_data_list_is_a_failure(monkeypatch, repo):
    """🔴 The reason this smoke uses /wordsets rather than /.

    Flask up + routing + JSON, and zero rows: what a lost database connection
    looks like from outside. Relaxing this to "did it return JSON" reproduces
    the defect the smoke exists to catch, while still passing every other test
    in this file.
    """
    rc = _run(monkeypatch, repo, _fetches({
        smoke.CONTROL_PATH: _http_error(404),
        "/wordsets": (200, JSON_CT, json.dumps({"data": []}).encode()),
    }))
    assert rc == smoke.FAIL


def test_html_on_the_route_is_a_failure(monkeypatch, repo):
    rc = _run(monkeypatch, repo, _fetches({
        smoke.CONTROL_PATH: _http_error(404),
        "/wordsets": (200, HTML_CT, b"<html>shell</html>"),
    }))
    assert rc == smoke.FAIL


def test_route_is_read_from_source_not_hardcoded(monkeypatch, repo):
    """Rename the blueprint prefix and the smoke must follow it.

    A hardcoded '/wordsets' would keep passing against a stale deploy on the day
    the prefix changed -- the decay this derivation exists to refuse.
    """
    (repo / "backend" / "app" / "routes" / "wordsets.py").write_text(
        "bp = Blueprint('wordsets', __name__, url_prefix='/v2/wordsets')\n"
    )
    seen = []

    def _f(url, timeout=20.0):
        seen.append(url)
        if url.endswith(smoke.CONTROL_PATH):
            raise _http_error(404)
        return (200, JSON_CT, ROWS)

    assert _run(monkeypatch, repo, _f) == smoke.PASS
    assert "https://x.test/v2/wordsets" in seen


def test_missing_source_is_cannot_tell(monkeypatch, repo):
    (repo / "backend" / "app" / "routes" / "wordsets.py").unlink()
    rc = _run(monkeypatch, repo, _fetches({smoke.CONTROL_PATH: _http_error(404)}))
    assert rc == smoke.CANNOT_TELL


def test_three_exit_codes_are_distinct():
    """0/1/3 must stay three values. Collapsing CANNOT-TELL into either
    neighbour is the whole failure mode this contract exists to prevent."""
    assert len({smoke.PASS, smoke.FAIL, smoke.CANNOT_TELL}) == 3
    assert smoke.CANNOT_TELL not in (smoke.PASS, smoke.FAIL)
