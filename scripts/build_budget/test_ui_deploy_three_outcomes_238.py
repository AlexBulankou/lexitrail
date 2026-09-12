"""issue-238 AC2: the ui-deploy read-back has THREE outcomes, and a test must be
able to tell them apart BY INPUT.

Every other pin on `cloudbuild-ui.yaml` is a static-string assertion over the
YAML. Those establish that text is present; they are structurally incapable of
establishing that two branches are reachable by different inputs, which is
exactly what AC2 asks for -- "a test that cannot tell them apart re-creates the
bug it is meant to catch."

So this file EXECUTES the step's script with `kubectl` and `gcloud` stubbed on
PATH, and drives the only variable that decides the outcome: what the live spec
reads AFTER `set image`.

    live == what we pushed      -> exit 0, DEPLOY-OK
    live == the PREVIOUS digest -> exit 1, DEPLOY-FAIL      (set image did not take)
    live == some OTHER digest   -> exit 0, DEPLOY-SUPERSEDED (a concurrent deploy won)

The genuine-failure and superseded arms differ in NOTHING but that one value, so
a collapse of the two cannot pass: see `test_superseded_and_failure_are_not_the
_same_input_238`, which is the control.
"""

import os
import pathlib
import subprocess
import textwrap

import pytest
import yaml

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_UI = _ROOT / "cloudbuild-ui.yaml"

PREV = "us-central1-docker.pkg.dev/lexitrail/lexitrail-repo/lexitrail-ui@sha256:aaa"
REF = "us-central1-docker.pkg.dev/lexitrail/lexitrail-repo/lexitrail-ui@sha256:bbb"
OTHER = "us-central1-docker.pkg.dev/lexitrail/lexitrail-repo/lexitrail-ui@sha256:ccc"


def _deploy_script():
    """The ui-deploy step's script, unescaped for a real shell.

    Cloud Build reads `$$` as a literal `$`, so the file stores shell variables
    doubled. Running the stored text verbatim would expand nothing and the
    comparisons would all be empty-vs-empty -- which passes every arm and proves
    nothing. Unescaping is what makes this an execution rather than a pantomime.
    """
    doc = yaml.safe_load(_UI.read_text())
    steps = {s.get("id"): s for s in doc["steps"]}
    assert "ui-deploy" in steps, (
        "issue-238: cloudbuild-ui.yaml has no `ui-deploy` step -- that is the "
        "pre-2026-08-29 build-and-push-only shape (issue-216)."
    )
    args = steps["ui-deploy"].get("args", [])
    # args is ['-c', '<script>']. Joining ALL of them prepends the literal `-c`
    # as the script's first line, and `bash -c` then rejects it before a single
    # assertion runs. The sibling static-string pins join everything because
    # they only ever grep the result; an execution cannot.
    script = args[-1]
    assert "-c" not in args[-1][:4], (
        "issue-238: ui-deploy's args no longer end with the script body. "
        f"Reading args[-1] would execute a flag, not the step. args={args!r}"
    )
    assert "$$" in script, (
        "issue-238: the ui-deploy script no longer contains `$$`. Either the "
        "escaping convention changed or this helper is reading the wrong step; "
        "unescaping a script with no `$$` in it silently yields a no-op test."
    )
    return script.replace("$$", "$")


def _run(tmp_path, live_after):
    """Execute ui-deploy with stubbed binaries; `live_after` is the only variable."""
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
    (ws / "ui_image_ref.txt").write_text(REF)

    script = _deploy_script().replace("/workspace/", f"{ws}/")
    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}")
    return subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, env=env
    )


def test_live_matches_what_we_pushed_is_a_clean_deploy_238(tmp_path):
    r = _run(tmp_path, REF)
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}\n{r.stderr}"
    assert "DEPLOY-OK" in r.stdout, r.stdout
    assert "DEPLOY-FAIL" not in r.stdout + r.stderr
    assert "DEPLOY-SUPERSEDED" not in r.stdout


def test_live_still_the_previous_digest_is_a_genuine_failure_238(tmp_path):
    """`set image` did not take. This MUST stay red -- it is the original check."""
    r = _run(tmp_path, PREV)
    assert r.returncode == 1, f"expected exit 1, got {r.returncode}\n{r.stdout}"
    assert "DEPLOY-FAIL" in r.stderr, r.stderr
    assert "DEPLOY-SUPERSEDED" not in r.stdout


def test_live_is_a_third_digest_is_superseded_not_failed_238(tmp_path):
    """A concurrent build won the race. Our bytes were superseded, not lost:
    the winner is a LATER digest, so main is ahead of us. Exit 0, loudly."""
    r = _run(tmp_path, OTHER)
    assert r.returncode == 0, (
        "issue-238: a concurrent deploy is being reported as a build failure. "
        "That reds main with a result carrying no information about the code.\n"
        f"exit={r.returncode}\nstdout={r.stdout}\nstderr={r.stderr}"
    )
    assert "DEPLOY-SUPERSEDED" in r.stdout, r.stdout
    assert "DEPLOY-FAIL" not in r.stdout + r.stderr


def test_superseded_and_failure_are_not_the_same_input_238(tmp_path):
    """CONTROL for AC2. The two arms above differ in exactly one value, so this
    asserts the step actually DISCRIMINATES rather than happening to agree.

    Without it, a step that always exited 0 would pass the superseded arm, and a
    step that always exited 1 would pass the failure arm -- neither test can
    detect a collapse on its own, because each only ever sees one input."""
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    failed = _run(a, PREV)
    superseded = _run(b, OTHER)

    assert (failed.returncode, superseded.returncode) == (1, 0), (
        "issue-238: the genuine-failure and superseded cases returned the same "
        "exit code. They differ only in the live digest read back, so a shared "
        "verdict means the branches have been collapsed -- which is the bug "
        f"this issue exists to fix. failure={failed.returncode} "
        f"superseded={superseded.returncode}"
    )
    assert "DEPLOY-FAIL" in failed.stderr
    assert "DEPLOY-SUPERSEDED" in superseded.stdout


def test_previous_digest_is_read_before_set_image_238():
    """The three-outcome read is only possible if PREV is captured BEFORE the
    write. Ordering, pinned on the script text: a `get` that runs after `set
    image` reads our own write and can never name the digest we replaced."""
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
        "issue-238: PREV is captured at/after `set image`, so it reads the value "
        "we just wrote rather than the one we replaced. The superseded branch is "
        "then unreachable and the bug is back."
    )
