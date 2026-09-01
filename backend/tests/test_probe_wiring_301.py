"""issue-301: the probe WIRING, not the endpoint.

#303 added `/readyz` and `test_readyz_301.py` pins its behaviour. That is the
endpoint half. This is the other half: at the time #303 merged, the readiness
probe in `terraform-ys/workloads.tf` still pointed at `/health`, so the new
endpoint had zero consumers and the fix was inert — the deployed replica
answered `/readyz` correctly and Kubernetes never asked it.

Measured live 2026-09-01, after #303 merged:

    kubectl -n lexitrail get deploy lexitrail-backend -o jsonpath=...
      READY=/health  LIVE=/health  START=

    kubectl -n lexitrail exec <pod> -- curl 127.0.0.1:80/readyz
      HTTP 200 {"status":"ready"}

So this file pins the JOIN. It also pins the SPLIT, which is the part a future
reader is most likely to "clean up": liveness and startup must stay on
`/health`. A DB-dependent liveness probe restarts every replica during a DB
blip (partial outage -> total), and a DB-dependent startup probe stops a pod
binding at all while the DB is down.

⚠️ CORRECTION (hc2, #309 review): an earlier version of this note said
"lexitrail's cloudbuild.yaml has no pytest step, so nothing runs this in CI."
The first half is true and the CONCLUSION IS FALSE -- .github/workflows/
backend-tests.yml runs pytest on every PR touching backend paths (#269). I
checked Cloud Build, found nothing, and generalised to "no CI" -- enumerating
one CI surface and concluding about all of them. These tests DO gate merges.
"""
import re
from pathlib import Path

import pytest

WORKLOADS = Path(__file__).resolve().parents[2] / "terraform-ys" / "workloads.tf"


def _backend_probe_paths():
    """Return {probe_kind: path} for the backend container's three probes."""
    if not WORKLOADS.is_file():
        pytest.skip(f"terraform-ys not in this tree ({WORKLOADS})")
    src = WORKLOADS.read_text()
    # The backend container is the only one declaring a readiness_probe with an
    # http_get on port 80; scope to the region between its readiness_probe and
    # the end of its liveness_probe so a future second container cannot silently
    # satisfy these assertions from elsewhere in the file.
    found = {}
    for kind in ("readiness_probe", "startup_probe", "liveness_probe"):
        m = re.search(
            kind + r"\s*\{\s*http_get\s*\{\s*path\s*=\s*\"([^\"]+)\"",
            src,
        )
        assert m, f"{kind} with an http_get path not found in {WORKLOADS.name}"
        found[kind] = m.group(1)
    return found


def test_readiness_points_at_readyz_not_health():
    """The join #303 left open: readiness must ASK the endpoint #303 added."""
    paths = _backend_probe_paths()
    assert paths["readiness_probe"] == "/readyz", (
        "issue-301: readiness points at %r. /health is a literal that returns "
        "200 for a replica that cannot reach MySQL, so readiness on /health "
        "keeps a dead pod in the Service -- the exact defect #301 reported."
        % paths["readiness_probe"]
    )


def test_liveness_and_startup_stay_database_independent():
    """The split, pinned in the direction a 'consistency' cleanup would break."""
    paths = _backend_probe_paths()
    for kind in ("liveness_probe", "startup_probe"):
        assert paths[kind] == "/health", (
            "issue-301: %s points at %r. It must stay on /health: a "
            "DB-dependent liveness probe restarts EVERY replica during a DB "
            "blip (partial outage -> total), and a DB-dependent startup probe "
            "stops a pod binding at all while the DB is down. Readiness "
            "depends on the DB; these two must not." % (kind, paths[kind])
        )
