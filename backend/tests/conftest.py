"""lexitrail#232 AC1/AC2 — Flask 2.2.5's test client hard-codes
``werkzeug.__version__`` into its User-Agent header (``flask/testing.py``):

    "HTTP_USER_AGENT": f"werkzeug/{werkzeug.__version__}",

``__version__`` was removed from the werkzeug package itself somewhere
between 2.2 and 3.1 (#232's AC3 pins Werkzeug to 3.1.8 — what production
already runs — rather than downgrading it to match Flask 2.2.5's test
client, since a downgrade would be a deploy change nobody asked for).
So every ``app.test_client()`` call dies at fixture time with
``AttributeError: module 'werkzeug' has no attribute '__version__'``,
on any test, regardless of what it's actually testing.

Restoring the attribute here is test-scope only: nothing under
app/ imports it, and requirements.txt / the deployed Werkzeug version
are untouched. Read it from package metadata rather than hardcoding
3.1.8, so this keeps working if the pin ever moves.
"""
from __future__ import annotations

import werkzeug

if not hasattr(werkzeug, "__version__"):
    from importlib.metadata import version

    werkzeug.__version__ = version("werkzeug")
