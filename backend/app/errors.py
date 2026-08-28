"""lexitrail#180 — a 500 from an uncaught exception used to emit NOTHING.

THE DEFECT. This backend had two error-logging surfaces and neither saw an uncaught exception:

  1. `utils.error_response()` logs, but it is a helper a route must CALL. 31 call sites, all of
     them HANDLED errors. Nothing catches what a route did not anticipate.
  2. The access log only ever sees `GET /` — measured over 1 day, 100/100 lines. It logs GCP
     health checks against the root and never an API path.

  grep -rn 'errorhandler|handle_exception|register_error_handler' backend/   ->  0 hits

🔴 SO EVERY 500 INVESTIGATION ON THIS SERVICE STARTED FROM AN UNDERCOUNT, AND NOTHING SAID SO.
Measuring #45's R3-BUG-1 I reported "4 user-facing 500s in 14 days, 0.55%". The query limit was
not the constraint; COVERAGE was, and I had not checked it. The honest figure was >=4 and >=0.55%.
An absence that is really a blindness is the most expensive kind, because it reads as good news.

⚠️ WHAT THIS DOES NOT DO: it does not make the ACCESS log see API routes. That is a separate
surface (werkzeug is pinned to WARNING in create_app) and a separate decision about log volume.
This closes the uncaught-exception half only, and #180's other half stays open.
"""
from __future__ import annotations

import logging
import traceback

from flask import jsonify, request
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)


def register_error_handlers(app):
    """Log every uncaught exception, and return the same JSON shape routes already return.

    🔴 HTTPException IS RE-RAISED, NOT SWALLOWED. A catch-all that also caught `HTTPException`
    would convert every 404 and 405 into a 500 -- including the 405 that lexitrail#182's route
    pin depends on, and every 404 that #204 just made real. That would be a far worse regression
    than the blindness being fixed, delivered by the fix for it.
    """
    @app.errorhandler(HTTPException)
    def _passthrough_http(exc):                      # noqa: ANN001
        # 4xx/5xx that Flask itself raised: the status is already correct and already meaningful.
        # Logged at WARNING (not ERROR) so it does not drown the thing this module exists for.
        logger.warning(
            "HTTP %s on %s %s", exc.code, request.method, request.path)
        return exc

    @app.errorhandler(Exception)
    def _log_uncaught(exc):                          # noqa: ANN001
        # The traceback is the point: without it the log says a 500 happened and not where.
        logger.error(
            "UNCAUGHT %s on %s %s: %s\n%s",
            type(exc).__name__, request.method, request.path, exc,
            traceback.format_exc(),
        )
        # Same shape `utils.error_response` returns, so a client cannot tell a handled error from
        # an unhandled one -- deliberately. The DIFFERENCE belongs in the log, not in the body:
        # leaking "this one surprised us" tells an attacker which inputs are interesting.
        return jsonify({"error": True, "message": "Internal server error"}), 500
