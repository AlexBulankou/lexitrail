"""issue-494 AC2: the backend-deploy read-back has THREE outcomes, and a test
must be able to tell them apart BY INPUT.

Sibling of `test_ui_deploy_three_outcomes_238.py`, which covers the same shape
in `cloudbuild-ui.yaml`. The backend step carried the identical two-outcomes-
for-three-facts collapse verbatim and was out of #238's scope.

    live == what we pushed      -> exit 0, DEPLOY-OK
    live == the PREVIOUS digest -> exit 1, DEPLOY-FAIL       (set image did not take)
    live == some OTHER digest   -> exit 0, DEPLOY-SUPERSEDED (a concurrent deploy won)

The genuine-failure and superseded arms differ in NOTHING but that one value, so
a collapse of the two cannot pass -- see the control test at the bottom.

⚠️ This file also pins `scripts/deploy_ui_local.sh` (AC3), but only STRUCTURALLY.
That is a real difference in strength and it is stated rather than glossed: a
static assertion establishes that text is present and is structurally incapable
of establishing that two branches are reachable by different inputs. The backend
arms below are executions; the local-script arms are not.
"""

import os
import pathlib
import subprocess
import textwrap

import yaml

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_BACKEND = _ROOT / "cloudbuild.yaml"
_LOCAL = _ROOT / "scripts" / "deploy_ui_local.sh"

PREV = "us-central1-docker.pkg.dev/lexitrail/lexitrail-repo/lexitrail-backend@sha256:aaa"
REF = "us-central1-docker.pkg.dev/lexitrail/lexitrail-repo/lexitrail-backend@sha256:bbb"
OTHER = "us-central1-docker.pkg.dev/lexitrail/lexitrail-repo/lexitrail-backend@sha256:ccc"


def _deploy_script():
    """The backend-deploy step's script, unescaped for a real shell.

    Cloud Build reads `$$` as a literal `$`, so the file stores shell variables
    doubled. Running the stored text verbatim would expand nothing and every
    comparison would be empty-vs-empty -- which passes every arm and proves
    nothing. Unescaping is what makes this an execution rather than a pantomime.
    """
    doc = yaml.safe_load(_BACKEND.read_text())
    steps = {s.get("id"): s for s in doc["steps"]}
    assert "backend-deploy" in steps, (
        "issue-494: cloudbuild.yaml has no `backend-deploy` step. Either the id "
        f"changed or the deploy was removed. ids={sorted(steps)}"
    )
    args = steps["backend-deploy"].get("args", [])
    # args is ['-c', '<script>']. Joining ALL of them prepends the literal `-c`
    # as the script's first line and `bash -c` rejects it before a single
    # assertion runs. The sibling static pins join everything because they only
    # ever grep the result; an execution cannot.
    script = args[-1]
    assert "$$" in script, (
        "issue-494: the backend-deploy script no longer contains `$$`. Either "
        "the escaping convention changed or this helper is reading the wrong "
        "step; unescaping a script with no `$$` silently yields a no-op test."
    )
    return script.replace("$$", "$")


def _run(tmp_path, live_after):
    """Execute backend-deploy with stubbed binaries; `live_after` is the only variable."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # kubectl `get` is called twice: once before `set image` (PREV) and once
    # after (live_after). A call counter is what lets one stub serve both.
    (bin_dir / "kubectl").write_text(
        textwrap.dedent(
            f"""\
            #!/bin/bash
            if [ "$1" = "-n" ] && [ "$3" = "get" ]; then
              n=0
              [ -f "{tmp_path}/calls" ] && n=$(cat "{tmp_path}/calls")
              n=$((n+1)); echo "$n" > "{tmp_path}/calls"
              if [ "$n" = "1" ]; then echo -n "{PREV}"; else echo -n "{live_after}"; fi
            fi
            exit 0
            """
        )
    )
    (bin_dir / "gcloud").write_text("#!/bin/bash\nexit 0\n")
    for f in ("kubectl", "gcloud"):
        (bin_dir / f).chmod(0o755)

    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "backend_image_ref.txt").write_text(REF)

    script = _deploy_script().replace("/workspace/", f"{ws}/")
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}")
    return subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, env=env
    )


def test_live_matches_what_we_pushed_is_a_clean_deploy_494(tmp_path):
    r = _run(tmp_path, REF)
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}\n{r.stderr}"
    assert "DEPLOY-OK" in r.stdout, r.stdout
    assert "DEPLOY-FAIL" not in r.stdout + r.stderr
    assert "DEPLOY-SUPERSEDED" not in r.stdout


def test_live_still_the_previous_digest_is_a_genuine_failure_494(tmp_path):
    """`set image` did not take. This MUST stay red -- it is the original check,
    and the whole risk of a three-outcome rewrite is quietly losing it."""
    r = _run(tmp_path, PREV)
    assert r.returncode == 1, f"expected exit 1, got {r.returncode}\n{r.stdout}"
    assert "DEPLOY-FAIL" in r.stderr, r.stderr
    assert "DEPLOY-SUPERSEDED" not in r.stdout


def test_live_is_a_third_digest_is_superseded_not_failed_494(tmp_path):
    """A concurrent build won the race. Our bytes were superseded, not lost: the
    winner is a LATER digest, so main is ahead of us, not behind."""
    r = _run(tmp_path, OTHER)
    assert r.returncode == 0, (
        "issue-494: a concurrent deploy is being reported as a build failure. "
        "That reds main with a result carrying no information about the code.\n"
        f"exit={r.returncode}\nstdout={r.stdout}\nstderr={r.stderr}"
    )
    assert "DEPLOY-SUPERSEDED" in r.stdout, r.stdout
    assert "DEPLOY-FAIL" not in r.stdout + r.stderr


def test_superseded_and_failure_are_not_the_same_input_494(tmp_path):
    """CONTROL for AC2. The two arms above differ in exactly one value, so this
    asserts the step actually DISCRIMINATES rather than happening to agree.

    Without it, a step that always exited 0 would pass the superseded arm and a
    step that always exited 1 would pass the failure arm -- neither test can
    detect a collapse alone, because each only ever sees one input."""
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    failed = _run(a, PREV)
    superseded = _run(b, OTHER)

    assert (failed.returncode, superseded.returncode) == (1, 0), (
        "issue-494: the genuine-failure and superseded cases returned the same "
        "exit code. They differ only in the live digest read back, so a shared "
        "verdict means the branches have been collapsed -- which is the bug this "
        f"issue exists to fix. failure={failed.returncode} "
        f"superseded={superseded.returncode}"
    )
    assert "DEPLOY-FAIL" in failed.stderr
    assert "DEPLOY-SUPERSEDED" in superseded.stdout


def test_previous_digest_is_read_before_set_image_494():
    """The three-outcome read is only possible if PREV is captured BEFORE the
    write. A `get` after `set image` reads our own write and can never name the
    digest we replaced, so the superseded branch becomes unreachable."""
    # Strip comment lines first. The patch that fixed this deliberately says
    # "read the digest BEFORE `set image`" in a comment ABOVE the PREV capture,
    # so a naive index() finds that MENTION and reports the ordering as wrong --
    # a confident red on correct code, produced by the documentation of the fix.
    script = "\n".join(
        ln for ln in _deploy_script().splitlines() if not ln.strip().startswith("#")
    )
    prev_at = script.index("PREV=")
    set_at = script.index("set image")
    assert prev_at < set_at, (
        "issue-494: PREV is captured at/after `set image`, so it reads the value "
        "we just wrote rather than the one we replaced."
    )


# ── AC3: scripts/deploy_ui_local.sh ──────────────────────────────────────────
# Structural only. See the module docstring: these cannot show the branches are
# reachable by different inputs, and that is a genuine weakness, not a nit.

def _local_body():
    return "\n".join(
        ln for ln in _LOCAL.read_text().splitlines() if not ln.strip().startswith("#")
    )


def test_local_deploy_captures_prev_before_set_image_494():
    body = _local_body()
    prev_at = body.index("PREV=")
    set_at = body.index("set image")
    assert prev_at < set_at, (
        "issue-494 AC3: deploy_ui_local.sh captures PREV at/after `set image`."
    )


def test_local_deploy_superseded_branch_does_not_die_494():
    """The load-bearing behavioural claim, and the one a reader is most likely to
    undo: the superseded branch must NOT call `die`. `p/local-ci/lt-deploy-
    poller.sh` runs this unattended on every merge, so dying on a race a
    concurrent Cloud Build won fails a poller run that carries no information
    about the code."""
    body = _local_body()
    start = body.index("DEPLOY-SUPERSEDED")
    tail = body[start:]
    branch = tail[: tail.index("\nfi")] if "\nfi" in tail else tail
    assert "die " not in branch, (
        "issue-494 AC3: the DEPLOY-SUPERSEDED branch calls `die`. A concurrent "
        "deploy winning is not this run's failure -- the winner is a LATER "
        f"digest, so main is ahead, not behind.\nbranch={branch!r}"
    )


def test_local_deploy_still_dies_on_the_genuine_failure_494():
    """The counterpart, so the fix above cannot be satisfied by making the whole
    read-back non-fatal: the PREVIOUS-digest case must still be fatal."""
    body = _local_body()
    assert 'die "DEPLOY-FAIL' in body, (
        "issue-494 AC3: deploy_ui_local.sh no longer dies on the genuine "
        "set-image-did-not-take case. Three outcomes collapsed to one."
    )
