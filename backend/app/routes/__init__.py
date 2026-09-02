from flask import Blueprint, jsonify
import logging
import time
from sqlalchemy import text
from .users import bp as users_bp
from .wordsets import bp as wordsets_bp
from .userwords import bp as userwords_bp
from .hint_generation import bp as hint_generation_bp
from ..database import db
from ..cache_warm_policy import (WARM_NOT_READY,  # issue-266
                                 cache_warm_readiness)
from .wordsets import cache_status

def register_routes(app):
    # Register all blueprints
    app.register_blueprint(users_bp)
    app.register_blueprint(wordsets_bp)
    app.register_blueprint(userwords_bp)
    app.register_blueprint(hint_generation_bp)

    # Add root route
    @app.route('/')
    def index():
        return jsonify(message="Welcome to the Flask API"), 200


    @app.route('/health')
    def health_check():
        return jsonify({'status': 'healthy'}), 200

    @app.route('/version')
    def version():
        """The git sha these bytes were built from (issue-273 step 1).

        A merge at build-budget margin 0 does not red main -- the quota gate
        declines the deploy trigger and the artifact silently never moves. Alex's
        P1 #265 fix sat merged-but-not-live for ~75 minutes that way, and was
        found only by accident. Nothing in this repo could say "main is ahead of
        production", because nothing shipped can say WHICH COMMIT it is.

        🔴 The alternative that was measured and rejected: grepping the served
        bytes for a string a recent commit introduced. That works only when a
        commit happens to add a distinctive literal. A commit that changes a
        constant, reorders logic or edits a template adds nothing greppable, and
        the check then reports "current" for a stale artifact -- failing in the
        reassuring direction, which is the same shape as the silent no-deploy it
        is meant to catch.

        🔴 UNSET IS ITS OWN STATE AND MUST NOT LOOK LIKE A MATCH. `BUILD_SHA` is
        injected by the Dockerfile at image build; a locally-run or hand-built
        image has none. Returning `""` there would let a naive comparison read
        equal-to-nothing, or a truthiness check read "no drift". So the field is
        JSON `null` and `known` is `false`, and a consumer that ignores `known`
        gets a value it cannot mistake for a sha. See scripts/check_deploy_current.py,
        which renders this as CANNOT-TELL rather than as pass or fail.

        Unauthenticated on purpose. Every credential on bp is PERMISSION_DENIED
        against lexitrail's Artifact Registry and its build list (#224), so a
        detector built on "compare the deployed image tag to the newest build" is
        not implementable from any seat we have. A public sha is not a secret --
        the repo is the operator's and the commits are visible in it -- and it is
        the only thing that makes the check runnable from anywhere, CI included.
        """
        import os
        sha = (os.environ.get('BUILD_SHA') or '').strip()
        return jsonify({
            'sha': sha or None,
            'known': bool(sha),
        }), 200

    @app.route('/readyz')
    def readiness_check():
        """Readiness: can this replica actually SERVE, not merely run.

        `/health` above returns a literal, so it reports `healthy` for a pod that
        cannot reach MySQL — which is what happened in #301: one replica returned
        500 on every database-backed request for ~26 minutes while `/health` kept
        answering 200, so Kubernetes went on routing user traffic to it. A signal
        whose value cannot vary with the fact it reports is not a readiness check.

        This issues a real `SELECT 1` through the SAME engine the app uses, so a
        lost connection makes the pod NotReady and it leaves the Service.

        🔴 `/health` is deliberately left alone. It must stay database-INDEPENDENT
        because the liveness probe points at it: a DB-dependent liveness check
        restarts every replica during a brief DB blip, turning a partial outage
        into a total one. Readiness depends on the DB; liveness must not. Do not
        "simplify" these two into one endpoint — that is the whole design.
        """
        try:
            db.session.execute(text('SELECT 1'))
        except Exception as exc:  # noqa: BLE001 -- any failure means NOT ready
            logging.getLogger(__name__).warning('readiness probe failed: %s', exc)
            return jsonify({'status': 'not-ready', 'reason': str(exc)[:200]}), 503

        # issue-266: the database is reachable. Can this replica serve WELL?
        # The decision lives in cache_warm_policy (pure, testable without a
        # Flask environment) -- see its docstring for why the deadline arm
        # reports READY rather than holding traffic forever.
        verdict, reason = cache_warm_readiness(cache_status, time.time())
        if verdict == WARM_NOT_READY:
            return jsonify({'status': 'not-ready', 'reason': reason}), 503
        return jsonify({'status': 'ready', 'cache': reason}), 200
