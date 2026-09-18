#!/usr/bin/env python3
"""lexitrail#547: the drift check must refuse a server that is not production.

WHY THIS IS A SEPARATE FILE FROM test_check_schema_drift.py
-----------------------------------------------------------
That file tests the comparison. This one tests the refusal to compare -- and the
refusal is the whole defect. Before the Cloud SQL cutover `check_schema_drift.py`
exec'd `mysql-0` and queried `mysql-0`, and those were the same database. They
are not any more:

    svc/mysql  selector app=cloudsql-proxy  -> proxies -> Cloud SQL  (PRODUCTION)
    pod mysql-0  label  app=mysql           -> still Running, full valid
                                               lexitraildb, read by nothing

🔴 WHY THE EXISTING `CANNOT-TELL` GUARDS COULD NOT CATCH THIS
The script already refuses an EMPTY live set, on the grounds that an empty set
reads as "everything is missing" one way and "no drift" the other. That guard is
sound and it is blind here, because **nothing is empty**. mysql-0 answers with a
populated, well-formed, internally consistent column set. Every downstream arm
then produces a confident verdict about a decommissioned database. The failure
is not a missing answer; it is a real answer from the wrong machine.

Measured 2026-09-18, both reachable from the same pod:

    via svc/mysql   @@version 8.0.45-google   @@server_id 441002752
    mysql-0 local   @@version 8.0.46          @@server_id 1

🔴 WHY IDENTITY IS TAKEN FROM THE SERVER, NOT FROM THE HOST STRING
The host is what we asked for; `@@version` is what answered. #547 happened
because a Service SELECTOR was repointed -- no string in the script changed, and
no host-based assertion could have noticed. A check keyed on the host we dialled
would have passed throughout the incident it exists to catch.

Run: python3 -m pytest -q scripts/test_drift_check_targets_production_547.py
"""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "check_schema_drift", ROOT / "scripts" / "check_schema_drift.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

PROD = "8.0.45-google|441002752"     # Cloud SQL, measured
MYSQL0 = "8.0.46|1"                  # the pre-cutover pod, measured
COLS = {"users.email", "words.word_id", "wordsets.wordset_id"}


# ── is_production_server: the pure predicate ──────────────────────────────

@pytest.mark.parametrize("ident,expected", [
    (PROD, True),
    (MYSQL0, False),
    ("8.0.46", False),
    (None, False),      # no identity is NOT permission to proceed
    ("", False),
])
def test_identity_discriminates_both_measured_servers(ident, expected):
    ok, _ = mod.is_production_server(ident)
    assert ok is expected


def test_the_refusal_names_the_server_it_saw():
    """A refusal that does not say what answered sends the reader to the wrong
    place -- they will check the host, which is not what went wrong."""
    _, why = mod.is_production_server(MYSQL0)
    assert MYSQL0 in why


# ── verdict: the arm that did not exist ───────────────────────────────────

def test_the_wrong_server_refuses_even_when_the_columns_MATCH():
    """The defect, stated exactly.

    mysql-0 and Cloud SQL were seeded from the same schema, so the wrong server
    will usually AGREE with the baseline. A green PASS here is the bug: a drift
    check reporting clean about a database nothing reads.
    """
    code, msg = mod.verdict(set(COLS), set(COLS), ident=MYSQL0)
    assert code == mod.CANNOT_TELL, f"compared against the wrong server: {msg}"
    assert "547" in msg


def test_the_wrong_server_refuses_even_when_the_columns_DIFFER():
    """The other direction: a FAIL from the wrong server is a false alarm that
    would send someone hunting a hand-run ALTER that never happened."""
    code, _ = mod.verdict(COLS | {"users.ghost"}, set(COLS), ident=MYSQL0)
    assert code == mod.CANNOT_TELL


def test_production_still_compares_normally():
    """The negative control. A refusal that fires on everything is not a check.

    Without this, every assertion above is satisfiable by hard-wiring
    CANNOT-TELL, and the file would pass while the script had stopped working.
    """
    assert mod.verdict(set(COLS), set(COLS), ident=PROD)[0] == mod.PASS
    assert mod.verdict(COLS | {"users.ghost"}, set(COLS), ident=PROD)[0] == mod.FAIL


def test_unreachable_cluster_still_outranks_the_identity_check():
    """`live is None` must keep its own message. Both are CANNOT-TELL, so the
    exit code cannot distinguish them -- only the text tells the operator
    whether to fix their kubeconfig or their target."""
    _, msg = mod.verdict(None, set(COLS), "pods 'mysql-nope' not found", ident=None)
    assert "mysql-nope" in msg


# ── the wiring, which is where a correct predicate usually dies ───────────

def test_live_cols_asks_the_SERVICE_by_default_not_the_pod():
    """#547 in one line: the pod is where the client runs, the host is the
    database. A correct predicate wired to the old target changes nothing."""
    assert mod.HOST == f"mysql.{mod.NAMESPACE}.svc.cluster.local"
    assert mod.POD not in mod.HOST


def test_identity_and_columns_come_from_ONE_invocation(monkeypatch):
    """If identity were fetched separately it could describe a different server
    than the columns -- svc/mysql load-balances across two proxy pods, so this
    is not hypothetical. Asserted by counting the exec calls."""
    calls = []

    class R:
        returncode = 0
        stderr = ""
        stdout = "aGVsbG8="          # base64, for the secret read

    class R2(R):
        stdout = f"{mod._IDENT}{PROD}\nusers.email\nwords.word_id\n"

    def fake_run(argv, **kw):
        calls.append(argv)
        return R2() if "exec" in argv else R()

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    cols, why, ident = mod._live_cols(mod.NAMESPACE, mod.POD, mod.SCHEMA)
    assert ident == PROD and why == ""
    assert cols == {"users.email", "words.word_id"}, cols
    assert sum(1 for c in calls if "exec" in c) == 1, calls


def test_the_identity_line_is_not_mistaken_for_a_column():
    """The sentinel shares a stream with the data it labels."""
    class R:
        returncode = 0
        stderr = ""
        stdout = "aGVsbG8="

    class R2(R):
        stdout = f"{mod._IDENT}{PROD}\nusers.email\n"

    import types
    fake = types.SimpleNamespace(run=lambda argv, **kw: R2() if "exec" in argv else R())
    orig, mod.subprocess = mod.subprocess, fake
    try:
        cols, _, _ = mod._live_cols(mod.NAMESPACE, mod.POD, mod.SCHEMA)
    finally:
        mod.subprocess = orig
    assert not any(mod._IDENT in c for c in cols), cols
