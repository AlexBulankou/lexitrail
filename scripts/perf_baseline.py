#!/usr/bin/env python3
"""Capture a latency + DB-CPU baseline for the lexitrail#358 Cloud SQL cutover.

WHY THIS IS A SCRIPT AND NOT A COMMAND
--------------------------------------
The cutover tripwire in `terraform-ys/cloudsql.tf` says: if `/wordsets` or a
Practice round degrades against a baseline, move `db-f1-micro -> db-g1-small`.
That comparison is only meaningful if BEFORE and AFTER are measured the same
way. A number captured by an ad-hoc `curl` loop and compared against a number
captured by a different ad-hoc loop measures the two loops as much as the two
databases. So the instrument is committed, and the after-run is this same file.

⚠️ CPU IS NOT OPTIONAL (hc2, on PR #409). `db-f1-micro` is SHARED-CORE and
burstable. Once the burst budget is spent the symptom is CPU throttling, not
buffer-pool misses — and a latency-only capture would show the degradation and
misattribute the cause. The two point at the same remedy here only by luck, so
capturing latency alone would produce a tripwire that fires for the wrong
reason and a fix chosen for the wrong reason.

WHAT THIS DOES NOT MEASURE, STATED SO IT IS NOT OVER-READ
---------------------------------------------------------
- It measures the API's latency, which includes app + network + DB. It does not
  isolate the DB. A regression here is a signal to look, not a diagnosis.
- The authenticated Practice round is NOT covered: it needs a real Google
  session. That half is captured by hand and recorded alongside.
- `kubectl top` is a ~15s rolling average from metrics-server, not a peak. It
  cannot see a sub-15s burst, which is exactly the shape shared-core throttling
  takes. Treat it as a floor on demand, never a ceiling.
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

DEFAULT_URL = "https://api.lexitrail.com/wordsets"


def _pct(xs: list[float], p: float) -> float:
    """Nearest-rank percentile. Explicit because `statistics.quantiles`
    interpolates, and an interpolated p95 over n=40 invents a value that was
    never observed."""
    if not xs:
        return float("nan")
    s = sorted(xs)
    k = max(0, min(len(s) - 1, int(round(p / 100.0 * len(s) + 0.5)) - 1))
    return s[k]


def sample(url: str, n: int, warmup: int, timeout: float) -> dict:
    lat: list[float] = []
    codes: dict[str, int] = {}
    errors: list[str] = []
    for i in range(n + warmup):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                body = r.read()
                code = str(r.status)
        except urllib.error.HTTPError as e:
            body, code = b"", str(e.code)
        except Exception as e:                      # noqa: BLE001
            body, code = b"", "EXC"
            errors.append(f"{type(e).__name__}: {e}")
        dt = (time.perf_counter() - t0) * 1000.0
        if i >= warmup:                             # discard warmup: TLS + cold caches
            lat.append(dt)
            codes[code] = codes.get(code, 0) + 1
        time.sleep(0.25)                            # do not self-inflict queueing
    return {"latency_ms": lat, "status_counts": codes, "errors": errors,
            "n": len(lat), "warmup_discarded": warmup}


def db_cpu(namespace: str, selector: str) -> dict:
    """Best-effort DB-side CPU/memory. Absence is reported, never silently
    rendered as zero — an unmeasured baseline must not read as a quiet one."""
    out: dict = {"source": "kubectl top", "selector": selector, "rows": []}
    try:
        p = subprocess.run(
            ["kubectl", "top", "pod", "-n", namespace, "-l", selector,
             "--no-headers"],
            capture_output=True, text=True, timeout=60)
    except Exception as e:                          # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"
        return out
    if p.returncode != 0:
        out["error"] = (p.stderr or "").strip() or f"rc={p.returncode}"
        return out
    for line in p.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3:
            out["rows"].append({"pod": parts[0], "cpu": parts[1], "mem": parts[2]})
    if not out["rows"]:
        out["error"] = "no rows — selector matched nothing"
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--warmup", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=20.0)
    ap.add_argument("--namespace", default="lexitrail")
    ap.add_argument("--db-selector", default="app=mysql",
                    help="pod selector for the CURRENT database; after the "
                         "cutover the DB is managed and this yields no rows, "
                         "which is reported rather than treated as 0 CPU")
    ap.add_argument("--label", required=True,
                    help="what this run is, e.g. 'before-cutover-selfhosted'")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    s = sample(a.url, a.n, a.warmup, a.timeout)
    lat = s["latency_ms"]
    rec = {
        "label": a.label,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "url": a.url,
        "instrument": "scripts/perf_baseline.py",
        "sample": {k: v for k, v in s.items() if k != "latency_ms"},
        "latency_ms": {
            "min": round(min(lat), 1) if lat else None,
            "p50": round(_pct(lat, 50), 1) if lat else None,
            "p95": round(_pct(lat, 95), 1) if lat else None,
            "p99": round(_pct(lat, 99), 1) if lat else None,
            "max": round(max(lat), 1) if lat else None,
            "mean": round(statistics.fmean(lat), 1) if lat else None,
        },
        "db": db_cpu(a.namespace, a.db_selector),
        "raw_latency_ms": [round(x, 1) for x in lat],
    }
    text = json.dumps(rec, indent=2)
    if a.out:
        with open(a.out, "w") as f:
            f.write(text + "\n")
    print(text)
    # A run whose sample is not clean must not be quietly banked as a baseline.
    ok = bool(lat) and set(s["status_counts"]) == {"200"}
    if not ok:
        sys.stderr.write("\nBASELINE NOT CLEAN: non-200 responses or empty "
                         "sample — do NOT use this as the comparison point.\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
