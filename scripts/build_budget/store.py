"""issue-7947 / goal 1.1 — durable state for the IN-BUILD quota step.

`ledger.py` already stores state, and this module exists because it cannot serve
this caller: it writes `~/.ensemble/build-budget-state.json` on the bp host, and
the in-build step runs inside an EPHEMERAL Cloud Build worker with no shared
filesystem and no bp access. A counter whose state dies with the container is
not a counter — every build would read a fresh zero and be allowed.

🔴 THE CORRECTNESS PROPERTY IS COMPARE-AND-SWAP, and a plain read-then-write is
not merely untidy here — it is WRONG in the direction that grants free builds.

Cloud Build starts concurrent builds routinely (a push touching two triggers, a
PR plus its main merge). Two workers that both read `used=5` and both write
`used=6` have run two builds and charged one. Under-counting is silent, is the
reassuring direction, and compounds: the day's ceiling stops being a ceiling.

So every write carries the generation the read observed, and GCS rejects the
write if anything else advanced it. The loser re-reads and re-decides — it does
NOT re-apply its own delta, because `counter.decide` is pure over state and
re-running it against the fresh state is the whole point.

✅ MEASURED, all three arms, against the live bucket (2026-08-10, adm@):

    ifGenerationMatch=0  on a MISSING object   -> 200  (create wins)
    ifGenerationMatch=0  on an EXISTING object -> 412  (create-guard fires)
    ifGenerationMatch=G  with the CURRENT G    -> 200  (generation advances)
    ifGenerationMatch=G  with a STALE G        -> 412  (the race is caught)

The stale arm is the one that matters and it is the one a "looks fine" test
would omit: a store whose CAS silently succeeded on a stale generation is
indistinguishable from a working one until two builds race in production.

STATE IS PER-REPO, ONE OBJECT PER GCP PROJECT — deliberately.

`counter` state is already per-repo (`used` is that repo's count), so a shared
fleet-wide object would buy nothing and cost a great deal: builds run in five
different GCP projects, so one object means four cross-project IAM grants on a
write path that must never fail closed. Per-project objects need no cross-project
access at all, and CAS contention drops to concurrent builds of the SAME repo.

No third-party imports. The step runs in whatever image the build declares, so
depending on `google-cloud-storage` would silently restrict which images can
carry the gate — stdlib `urllib` works everywhere python3 does.
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional, Tuple

_GCS_ROOT = "https://storage.googleapis.com/storage/v1"
_GCS_UPLOAD = "https://storage.googleapis.com/upload/storage/v1"
_METADATA_TOKEN = (
    "http://metadata.google.internal/computeMetadata/v1/"
    "instance/service-accounts/default/token")

# A generation of 0 is GCS's own sentinel for "this object must not exist yet".
# Reusing it rather than inventing None-means-create keeps the create case and
# the update case on ONE code path, so the create is CAS-guarded too.
CREATE = 0


class StoreUnreadable(Exception):
    """The store exists but could not be read or understood.

    Deliberately NOT raised for a MISSING object: absent is a legitimate
    first-run state with an obvious correct answer (start fresh). Collapsing
    absent into unreadable would make every first run look like an instrument
    failure — the same distinction `ledger.LedgerUnreadable` draws, for the same
    reason.
    """


class StoreConflict(Exception):
    """A CAS write lost the race. Caller re-reads and re-decides."""


def _access_token() -> str:
    """Token for the GCS calls, in the order the environments actually appear.

    The env override is first so a test can inject a token without touching the
    metadata server, and `gcloud` is last because it is the one that is absent
    in a minimal build image.
    """
    tok = os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN")
    if tok:
        return tok.strip()
    try:
        req = urllib.request.Request(
            _METADATA_TOKEN, headers={"Metadata-Flavor": "Google"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)["access_token"]
    except Exception:
        pass
    try:
        out = subprocess.run(["gcloud", "auth", "print-access-token"],
                             capture_output=True, text=True, timeout=30)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    raise StoreUnreadable(
        "no access token: metadata server unreachable and gcloud unavailable")


class GcsStore:
    """CAS-backed state in one GCS object. The production store."""

    atomic = True

    def __init__(self, bucket: str, obj: str):
        self.bucket = bucket
        self.obj = obj

    def __str__(self) -> str:
        return f"gs://{self.bucket}/{self.obj}"

    def _obj_url(self, base: str) -> str:
        return f"{base}/b/{self.bucket}/o/{urllib.parse.quote(self.obj, safe='')}"

    def load(self) -> Tuple[Optional[dict], int]:
        """Returns (state_or_None, generation). None state means first run."""
        url = self._obj_url(_GCS_ROOT) + "?alt=media"
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {_access_token()}"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read()
                # The generation of the bytes we just read — NOT a second
                # metadata call, which could observe a different generation and
                # hand us a CAS token for state we never saw.
                gen = int(r.headers.get("x-goog-generation", "0"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, CREATE
            raise StoreUnreadable(f"GET {self} -> HTTP {e.code}") from e
        except Exception as e:
            raise StoreUnreadable(f"GET {self} failed: {e}") from e
        try:
            return json.loads(raw.decode("utf-8")), gen
        except Exception as e:
            raise StoreUnreadable(f"{self} is not valid JSON: {e}") from e

    def save(self, state: dict, generation: int) -> int:
        """Write iff the object is still at `generation`. Returns the new one."""
        body = json.dumps(state, sort_keys=True, indent=2).encode("utf-8")
        url = (f"{_GCS_UPLOAD}/b/{self.bucket}/o?uploadType=media"
               f"&name={urllib.parse.quote(self.obj, safe='')}"
               f"&ifGenerationMatch={generation}")
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Authorization": f"Bearer {_access_token()}",
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return int(json.load(r)["generation"])
        except urllib.error.HTTPError as e:
            if e.code == 412:
                raise StoreConflict(
                    f"{self} advanced past generation {generation}") from e
            raise StoreUnreadable(f"POST {self} -> HTTP {e.code}") from e
        except Exception as e:
            raise StoreUnreadable(f"POST {self} failed: {e}") from e


class FileStore:
    """Local file state. DEV AND TESTS ONLY — see `atomic`.

    🔴 `atomic = False` is load-bearing, not documentation. This store cannot
    detect a concurrent writer, so pointing an ENFORCING project at it would
    reinstate exactly the lost-update bug `GcsStore` exists to prevent — and it
    would do so silently, because an under-count looks like a quiet day. The
    caller refuses this combination unless it is asked for explicitly; that is
    what keeps "a fallback that is also a legitimate value" from being reachable
    by accident.
    """

    atomic = False

    def __init__(self, path: Path):
        self.path = Path(path)

    def __str__(self) -> str:
        return f"file://{self.path}"

    def load(self) -> Tuple[Optional[dict], int]:
        if not self.path.exists():
            return None, CREATE
        try:
            return json.loads(self.path.read_text()), 1
        except Exception as e:
            raise StoreUnreadable(f"{self} is not valid JSON: {e}") from e

    def save(self, state: dict, generation: int) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, sort_keys=True, indent=2))
        tmp.replace(self.path)
        return 1


def from_uri(uri: str) -> Any:
    """`gs://bucket/path` -> GcsStore; `file:///abs/path` -> FileStore.

    Anything else raises rather than defaulting. A mistyped scheme that fell
    through to a local file would produce a store that always reads zero and
    allows every build — a failure that reports itself as a healthy quota.
    """
    if uri.startswith("gs://"):
        rest = uri[len("gs://"):]
        if "/" not in rest:
            raise ValueError(f"gs:// URI needs bucket AND object path: {uri}")
        bucket, obj = rest.split("/", 1)
        if not bucket or not obj:
            raise ValueError(f"gs:// URI needs bucket AND object path: {uri}")
        return GcsStore(bucket, obj)
    if uri.startswith("file://"):
        return FileStore(Path(uri[len("file://"):]))
    raise ValueError(
        f"unsupported state URI {uri!r}: expected gs:// or file://")
