"""lexitrail#182 -- `GET /users` must not exist. Asserted WITHOUT a database.

THE DEFECT. `get_users()` was decorated with `@authenticate_user` and nothing
else -- the only route in `users.py` that did not call `validate_user_access`
to scope its response to the caller -- and returned every registered member's
email. The auth layer accepts a guest/demo identity as authenticated, so an
anonymous visitor could read the whole member list. Confirmed against
production 2026-08-27 (counts only).

🔴 WHY THIS FILE EXISTS SEPARATELY FROM test_users.py. The rest of the suite
needs a live MySQL on 127.0.0.1:3306 and downloads a schema from GCS in
`setUp`; measured 2026-08-28, every test in `tests/test_users.py` ERRORS in an
environment without those. This repo also has **no CI at all**. So a regression
pin added there is a pin that, in practice, nothing runs -- and an unrun test is
not a guarantee, it is a comment that looks like one. This file registers the
blueprint on a bare Flask app and reads the ROUTE TABLE, which needs neither.

🔴 IT ASSERTS THE ROUTE TABLE, NOT THE SOURCE. A grep for `def get_users` would
be satisfied by the explanatory comment left at the bottom of `users.py` naming
exactly that -- the use/mention trap, and the comment is already there. What
cannot be faked by prose is whether werkzeug will route the request.
"""
from __future__ import annotations

import pathlib
import sys

import pytest
from flask import Flask
from werkzeug.exceptions import MethodNotAllowed, NotFound

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.routes.users import bp  # noqa: E402


@pytest.fixture
def adapter():
    app = Flask(__name__)
    app.register_blueprint(bp)
    return app.url_map.bind("localhost")


def _match(adapter, path, method):
    """The endpoint name, or the refusal class. Never raises."""
    try:
        return adapter.match(path, method=method)[0]
    except MethodNotAllowed:
        return "405"
    except NotFound:
        return "404"


def test_get_on_the_users_COLLECTION_is_not_routable(adapter):
    """🔴 THE BUG. Before the fix this resolved to `users.get_users`, which
    returned every member's email to any authenticated caller -- and a guest
    token is authenticated. Measured after removal: 405, because `POST /users`
    still exists so the path is known and only the method is not."""
    assert _match(adapter, "/users", "GET") == "405"


def test_the_sibling_routes_still_resolve(adapter):
    """POSITIVE CONTROL, and the reason the assertion above means anything.

    If the blueprint failed to import, or were registered under a different
    prefix, every lookup would return 404/405 and the test above would pass
    while testing nothing. These three prove the route table is real and that
    the fix removed ONE route rather than breaking the module."""
    assert _match(adapter, "/users", "POST") == "users.create_user"
    assert _match(adapter, "/users/a@b.co", "GET") == "users.get_user"
    assert _match(adapter, "/users/migrate", "POST") == "users.migrate_user"


def test_no_route_returns_a_collection_of_users(adapter):
    """The CLASS, not just the one instance -- #182's second acceptance line is
    "no endpoint returns another user's email to an unauthorized caller", and a
    future `/users/all` or `/users/list` would satisfy the single-path test
    above while restoring the leak.

    Every remaining rule under /users either takes an <email> (and its handler
    calls `validate_user_access`) or is a non-GET. A new collection GET has to
    change this assertion deliberately, which is the point."""
    app = Flask(__name__)
    app.register_blueprint(bp)
    collection_gets = [
        str(r) for r in app.url_map.iter_rules()
        if str(r).startswith("/users")
        and "GET" in r.methods
        and "<email>" not in str(r)
    ]
    assert collection_gets == [], (
        f"a GET under /users that is not scoped to an <email> is back: "
        f"{collection_gets}. #182 was exactly this shape -- if the new route "
        "is intended, it needs an authorization check that this backend does "
        "not currently have (there is no admin role), not just a new test."
    )
