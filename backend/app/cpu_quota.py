"""Effective CPU count for THIS container — not the node's core count.

lexitrail#276. `multiprocessing.cpu_count()` reads `nproc`, which reports the
NODE's cores and is completely unaffected by a cgroup CPU quota. On the live
`lexitrail-backend` pod that is **2**, while `cpu.max` grants **0.2 CPU**:

    cpu.max          20000 100000     -> 20 ms of CPU per 100 ms period
    nr_throttled     3190 / 6669      -> 47.8% of periods throttled
    throttled_usec   117,397,557      -> 117.4 s STALLED
    usage_usec        69,246,627      ->  69.2 s running

So `ThreadPoolExecutor(min(cpu_count(), ...))` spawned 2 runnable threads
against a 0.2-CPU budget. Two threads drain 20 ms in ~10 ms of wall clock and
then the WHOLE container is frozen for the remaining ~90 ms of every period —
the classic CFS burst-then-freeze. More runnable threads make it strictly
worse, because they drain the budget faster and lengthen the freeze.

🔴 The trap this closes is that the wrong answer is not an error. `cpu_count()`
returns a real, plausible integer describing a real machine — just not the one
the process is allowed to use. Nothing raises, nothing logs, and the symptom
surfaces a layer away as latency.

⚠️ This is deliberately NOT tied to the current 200m limit. It is wrong on
*any* quota'd container and would be wrong again at the next limit change, so
it derives the number rather than encoding today's answer.
"""
from __future__ import annotations

import logging
import multiprocessing
import os

logger = logging.getLogger(__name__)

DEFAULT_CGROUP_ROOT = "/sys/fs/cgroup"


def _read(path: str) -> str | None:
    try:
        with open(path) as fh:
            return fh.read().strip()
    except OSError:
        # Absent or unreadable -> "cannot tell", which must fall through to the
        # next source rather than be scored as "no quota".
        return None


def quota_cpus(cgroup_root: str = DEFAULT_CGROUP_ROOT) -> int | None:
    """CPUs granted by the cgroup quota, or None when there is no quota.

    None means CANNOT TELL / UNLIMITED — deliberately distinct from an integer,
    so a caller can never mistake "no quota file" for "quota of zero".

    Rounds DOWN to a whole worker and floors at 1: a 0.2-CPU grant is one
    worker's worth of budget, and 0 workers is not a thing you can schedule.
    """
    # cgroup v2: "<quota> <period>", or "max <period>" when unlimited.
    v2 = _read(os.path.join(cgroup_root, "cpu.max"))
    if v2:
        parts = v2.split()
        if len(parts) == 2 and parts[0] != "max":
            try:
                quota, period = int(parts[0]), int(parts[1])
                if quota > 0 and period > 0:
                    return max(1, quota // period)
            except ValueError:
                pass
        elif parts and parts[0] == "max":
            return None  # explicitly unlimited, not "unreadable"

    # cgroup v1: two files, quota of -1 means unlimited.
    q = _read(os.path.join(cgroup_root, "cpu", "cpu.cfs_quota_us"))
    p = _read(os.path.join(cgroup_root, "cpu", "cpu.cfs_period_us"))
    if q is not None and p is not None:
        try:
            quota, period = int(q), int(p)
            if quota > 0 and period > 0:
                return max(1, quota // period)
            if quota <= 0:
                return None  # -1 = unlimited
        except ValueError:
            pass

    return None


def effective_cpus(cgroup_root: str = DEFAULT_CGROUP_ROOT) -> int:
    """Workers this container can actually run in parallel.

    `min(quota, nproc)` — the quota can exceed the node's cores (a limit of 4
    on a 2-core node), and spawning 4 threads there buys nothing.
    """
    host = multiprocessing.cpu_count()
    quota = quota_cpus(cgroup_root)
    if quota is None:
        return host
    return max(1, min(quota, host))
