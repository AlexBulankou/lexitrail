from flask import Blueprint, jsonify
import logging
from sqlalchemy import text
from .users import bp as users_bp
from .wordsets import bp as wordsets_bp
from .userwords import bp as userwords_bp
from .hint_generation import bp as hint_generation_bp
from ..database import db

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
        return jsonify({'status': 'ready'}), 200
