"""#179 — every prod 500 in a 14d window was a pooled MySQL connection the
server had already dropped, handed to a request as if live. The fix is
`SQLALCHEMY_ENGINE_OPTIONS` on the Flask app's `Config`, not the CLI-script
`create_engine` calls in `backend/scripts/` — this test pins the app-config
surface specifically, since that distinction is the AC's second bullet.

`pool_recycle` must stay strictly under the server's `wait_timeout` (measured
28800s on mysql-0, 2026-08-27) or the setting is a no-op: SQLAlchemy would
"recycle" a connection the server had already reaped.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.config import Config, TestConfig  # noqa: E402

# The measured server value (see config.py's comment for the measurement
# recipe). Not imported from config.py itself — the whole point is to catch
# pool_recycle drifting to sit >= the server's real value, so the bound must
# be independent of whatever config.py currently sets.
MEASURED_WAIT_TIMEOUT_S = 28800


def test_pool_pre_ping_enabled():
    opts = Config.SQLALCHEMY_ENGINE_OPTIONS
    assert opts.get('pool_pre_ping') is True


def test_pool_recycle_is_comfortably_under_server_wait_timeout():
    opts = Config.SQLALCHEMY_ENGINE_OPTIONS
    recycle = opts.get('pool_recycle')
    assert recycle is not None
    assert recycle < MEASURED_WAIT_TIMEOUT_S, (
        f"pool_recycle={recycle} must be strictly under wait_timeout="
        f"{MEASURED_WAIT_TIMEOUT_S}s, or SQLAlchemy will recycle a connection "
        "no sooner than the server already reaps it -- a no-op fix."
    )


def test_engine_options_inherited_by_test_config():
    # TestConfig subclasses Config and does not override
    # SQLALCHEMY_ENGINE_OPTIONS -- confirms the setting reaches every config
    # variant the app actually instantiates, not just the default.
    assert TestConfig.SQLALCHEMY_ENGINE_OPTIONS == Config.SQLALCHEMY_ENGINE_OPTIONS
