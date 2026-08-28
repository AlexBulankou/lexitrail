"""lexitrail#180 — an uncaught exception must reach the log.

🔴 DB-FREE ON PURPOSE. `tests/test_users.py` and its siblings need a live MySQL on 127.0.0.1:3306
and a GCS schema download in setUp, and this repo has NO CI for `backend/` (the one GitHub Actions
workflow is path-filtered to `ui/`). A pin added to that suite is a pin that, in practice, nothing
runs. This registers the handlers on a bare Flask app, which needs no database, no env and no
network -- same shape as test_users_collection_route_182.py.
"""
from __future__ import annotations

import logging
import pathlib
import sys

import pytest
from flask import Flask

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.errors import register_error_handlers  # noqa: E402


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config["TESTING"] = False       # or Flask re-raises and the handler never runs
    register_error_handlers(app)

    @app.route("/boom")
    def boom():
        raise ValueError("the surprise")

    @app.route("/fine")
    def fine():
        return {"ok": True}

    return app.test_client()


def test_an_uncaught_exception_is_LOGGED_with_a_traceback(client, caplog):
    """🔴 THE BUG. Before this, the request 500'd and emitted nothing at all."""
    with caplog.at_level(logging.ERROR):
        r = client.get("/boom")
    assert r.status_code == 500
    text = caplog.text
    assert "UNCAUGHT" in text
    assert "ValueError" in text
    assert "/boom" in text
    # The traceback is the point: without it the log says a 500 happened and not where.
    assert "Traceback (most recent call last)" in text


def test_the_body_does_not_leak_the_exception(client):
    """A client must not be able to tell a handled error from an unhandled one.

    The difference belongs in the log. Leaking "this one surprised us" tells an attacker which
    inputs are interesting -- and the shape matches utils.error_response's so nothing downstream
    has to special-case it.
    """
    body = client.get("/boom").get_json()
    assert body == {"error": True, "message": "Internal server error"}
    assert "surprise" not in str(body)


def test_a_404_is_STILL_a_404(client, caplog):
    """🔴 THE REGRESSION THIS FIX COULD HAVE CAUSED, and the reason HTTPException is re-raised.

    A catch-all that also caught HTTPException turns every 404 and 405 into a 500 -- including the
    404s lexitrail#204 just made real. That would be far worse than the blindness being fixed, and
    delivered by the fix for it.
    """
    with caplog.at_level(logging.WARNING):
        assert client.get("/no-such-route").status_code == 404
    assert "UNCAUGHT" not in caplog.text
    assert "HTTP 404" in caplog.text


def test_a_405_is_STILL_a_405(client, caplog):
    """Same, for the method case -- which is what lexitrail#182's route pin depends on."""
    with caplog.at_level(logging.WARNING):
        assert client.post("/fine").status_code == 405
    assert "UNCAUGHT" not in caplog.text


def test_CONTROL_a_working_route_is_untouched_and_silent(client, caplog):
    """Without this, every assertion above is satisfied by a handler that 500s everything."""
    with caplog.at_level(logging.WARNING):
        r = client.get("/fine")
    assert r.status_code == 200
    assert r.get_json() == {"ok": True}
    assert caplog.text.strip() == ""


def test_the_handlers_are_REGISTERED_by_create_app():
    """A handler nothing installs is inert -- the shape lexitrail#180 is itself about.

    Asserted on the source because create_app() needs a database. Anchored on the CALL, not the
    name: an import alone would satisfy a name check while nothing registered anything.
    """
    src = pathlib.Path(__file__).resolve().parents[1].joinpath(
        "app", "__init__.py").read_text()
    assert "register_error_handlers(app)" in src
