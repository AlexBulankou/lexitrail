#!/usr/bin/env python3
"""Pins lexitrail's cloudbuild quota-gate wiring (issue-77).

Every assertion here guards a failure that is INVISIBLE IN A GREEN BUILD: the
step runs, python exits 0, the build goes green, and the gate enforces nothing.
There is no output that distinguishes a working gate from an inert one, which is
why these are mechanical rather than a comment asking the next author to check.

Run:  python3 -m pytest scripts/build_budget/test_cloudbuild_wiring_77.py
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_ROOT = Path(__file__).resolve().parents[2]

# EVERY gated build config in the repo, with the id of its docker build step.
# issue-216 added the second one; the wiring below was written for the first and
# would have passed unchanged while the new file gated nothing, because the
# tests named a single file rather than the class of files.
#
# 🔴 A config added here and NOT added to this list is the failure this list
# exists to stop, so the last test in the yaml block asserts the list is the
# whole set rather than trusting whoever adds the next one to remember.
# `build_id` is the docker build step to check `--cache-from` on, or None for a
# config that builds no image (the jest one runs npm, so a layer cache is not a
# thing it can have — skipping that ONE assertion is right, silently excluding
# the whole file from the other six would not be).
CONFIGS = [
    (_ROOT / "cloudbuild.yaml", "backend-build"),
    (_ROOT / "cloudbuild-ui.yaml", "ui-build"),
    (_ROOT / "cloudbuild-ui-test.yaml", None),
]
_IDS = [p.name for p, _ in CONFIGS]

# Kept so the module still names the original file explicitly.
CB = CONFIGS[0][0]

gated = pytest.mark.parametrize("path,build_id", CONFIGS, ids=_IDS)


def _cfg(path=CB):
    return yaml.safe_load(path.read_text())


def _step(cfg, sid):
    for s in cfg["steps"]:
        if s.get("id") == sid:
            return s
    raise AssertionError(f"no step {sid!r}; ids={[s.get('id') for s in cfg['steps']]}")


@gated
def test_quota_gate_exists_and_starts_first(path, build_id):
    gate = _step(_cfg(path), "quota-gate")
    assert gate["waitFor"] == ["-"], "the gate itself must start at t=0"


@gated
def test_every_other_step_waits_on_the_gate_transitively(path, build_id):
    """🔴 The largest bypass measured in the fleet.

    `waitFor: ['-']` means START AT t=0 REGARDLESS OF FILE POSITION. A gate
    placed at the top of a file whose steps all say `['-']` gates ZERO of them —
    present, correctly placed, enforcing nothing. Transitive because chaining
    (`a -> gate`, `b -> a`) is legitimate and still gated; only a `['-']` or a
    chain that never reaches the gate is a bypass.
    """
    cfg = _cfg(path)
    by_id = {s.get("id"): s for s in cfg["steps"]}

    def reaches_gate(sid, seen=()):
        if sid == "quota-gate":
            return True
        if sid in seen:
            return False
        wf = by_id[sid].get("waitFor")
        assert wf is not None, (
            f"step {sid!r} has NO waitFor. That waits for the step ABOVE it, "
            "which is position-dependent and silently serialises the build. "
            "Point it at 'quota-gate' explicitly.")
        assert wf != ["-"], (
            f"step {sid!r} declares waitFor ['-'] — it starts at t=0 and "
            "BYPASSES the quota gate entirely (issue-77).")
        return all(reaches_gate(p, seen + (sid,)) for p in wf)

    for sid in by_id:
        if sid != "quota-gate":
            assert reaches_gate(sid), f"step {sid!r} never reaches the quota gate"


@gated
def test_gate_passes_trigger_name(path, build_id):
    """issue-8237: without it the trigger name reads EMPTY, empty is treated as
    ungated, and inbuild.py's per-trigger downgrade turns enforcement off while
    leaving counting on. Fails toward 'never gate anything'."""
    args = _step(_cfg(path), "quota-gate")["args"]
    assert "--trigger-name=$TRIGGER_NAME" in args


@gated
def test_gate_wires_the_break_glass_var_its_own_message_names(path, build_id):
    """The refusal message tells a blocked engineer to re-run with
    _BREAK_GLASS=1. A Cloud Build step gets no ambient environment, so without
    this the hatch the message names does not exist — worse than none, because
    it is specific and reads as actionable."""
    cfg = _cfg(path)
    env = _step(cfg, "quota-gate").get("env") or []
    assert any("ENSEMBLE_BUILD_QUOTA_BREAK_GLASS" in e for e in env)
    assert "_BREAK_GLASS" in (cfg.get("substitutions") or {}), \
        "_BREAK_GLASS must default to empty, or every ordinary build overrides"


@gated
def test_gate_reads_lexitrails_own_repo_and_state(path, build_id):
    args = _step(_cfg(path), "quota-gate")["args"]
    assert "--repo=lexitrail" in args
    assert any(a.startswith("--state-uri=gs://") for a in args), \
        "a file:// store cannot compare-and-swap and degrades the gate open"


@gated
def test_no_machine_type_anywhere(path, build_id):
    """Constraint 4 of the authorization: default machine type. A larger one is
    a silent cost increase no later reviewer would think to look for.

    Asserted against the PARSED yaml, not the text — the file's own prose says
    'No machineType anywhere in this file', so a substring search matches the
    comment SAYING it is absent and passes even if a real key is added.
    """
    cfg = _cfg(path)
    assert "machineType" not in (cfg.get("options") or {})
    for s in cfg["steps"]:
        assert "machineType" not in s, f"step {s.get('id')} sets machineType"


@gated
def test_layer_cache_is_wired_and_tolerates_a_cold_start(path, build_id):
    """Constraint 3. An uncached rebuild is the most expensive thing this file
    can do; a missing cache on the FIRST build must not fail the build."""
    if build_id is None:
        pytest.skip(f"{path.name} builds no image -- no layer cache to wire")
    cfg = _cfg(path)
    pull = _step(cfg, "pull-cache")
    assert "|| true" in " ".join(pull["args"]), "first build has nothing to pull"
    assert "--cache-from" in _step(cfg, build_id)["args"]


@gated
def test_logging_destination_is_set_because_these_run_under_a_service_account(path, build_id):
    """issue-228. Cloud Build REJECTS a service-account build with no logging
    destination -- and it rejects it at VALIDATION, before step 0.

    🔴 That is why this is pinned rather than left to review. The rejection means
    `quota-gate` never runs, so the build is invisible to the budget: the first one
    (2026-08-28T16:00:31Z) left `used` at 1. Every other test in this module guards
    a gate that runs and enforces nothing; this one guards a gate that never runs at
    all, and the two are indistinguishable downstream -- both leave the counter
    untouched.

    Pinned for EVERY config, not just the one that failed. `cloudbuild-ui.yaml` had
    the identical omission and no trigger yet, so nothing would have failed until
    issue-216 created one and its first build was rejected the same way -- the same
    bug, rediscovered at the same cost, one issue later.
    """
    cfg = _cfg(path)
    opts = cfg.get("options") or {}
    assert opts.get("logging") in ("CLOUD_LOGGING_ONLY", "NONE") or opts.get(
        "defaultLogsBucketBehavior") == "REGIONAL_USER_OWNED_BUCKET" or cfg.get(
        "logsBucket"), (
        f"{path.name} sets no logging destination. A trigger running it under a "
        "service account is rejected before step 0 -- see issue-228."
    )


def test_configs_list_covers_every_gated_build_config_in_the_repo():
    """🔴 The guard on the list itself.

    Every assertion above names files through CONFIGS, so a NEW `cloudbuild*.yaml`
    that nobody adds to that list is unpinned -- and unpinned is invisible,
    because an inert gate produces a green build exactly like a live one. That is
    the same shape the gate tests guard inside a file, one level out.

    Keyed on "declares a step with id `quota-gate`", not on the filename, so a
    config that genuinely has no gate (nothing to enforce) is correctly ignored
    rather than needing an exclusion entry.
    """
    listed = {p.name for p, _ in CONFIGS}
    found = set()
    for f in sorted(_ROOT.glob("cloudbuild*.yaml")):
        cfg = yaml.safe_load(f.read_text()) or {}
        if any(s.get("id") == "quota-gate" for s in (cfg.get("steps") or [])):
            found.add(f.name)
    assert found == listed, (
        f"gated configs on disk {sorted(found)} != CONFIGS {sorted(listed)}. "
        "A gated config missing from CONFIGS is checked by nothing; a name in "
        "CONFIGS with no gate on disk means the gate was removed."
    )


# ── the trap that is NOT in cloudbuild.yaml ──────────────────────────────────
CFG = Path(__file__).resolve().parents[2] / "config" / "build-budget.json"


def _lexitrail_cfg():
    import json
    return json.loads(CFG.read_text())["projects"]["lexitrail"]


def test_gate_triggers_is_not_empty_while_enforcing():
    """The second inert-gate trap, and the only one this repo's yaml cannot show.

    `gate.py`: "a trigger not in `gate_triggers` is never touched, whatever the
    balance." So `enforcing: true` beside an empty list is enforcement in NAME
    ONLY -- the build is counted and can never be refused, and a green build is
    byte-identical either way. lexitrail shipped exactly that pair (gate.py names
    it as the live instance), which is why this is mechanical rather than a note.

    Pinned as the PAIR, not as two facts: either is individually legitimate
    (enforcing=false with no triggers is an honest shadow config), and it is
    only their combination that claims a property the config cannot deliver.
    """
    c = _lexitrail_cfg()
    if not c.get("enforcing", False):
        pytest.skip("enforcing=false -- an empty gate_triggers is honest here")
    assert c.get("gate_triggers"), (
        "lexitrail declares enforcing=true with an empty `gate_triggers` -- "
        "nothing can ever be refused. Either list the deploy trigger's name or "
        "set enforcing=false; it DEBITS either way, so what is lost is the "
        "refusal, not the accounting."
    )


def test_gated_trigger_name_matches_the_state_bucket_project():
    """A name in `gate_triggers` that no real trigger carries is inert in the
    quiet direction: `gate.py` fails open on every ambiguity, so a typo here
    disables enforcement and reports nothing. Nothing in this repo can see the
    live trigger list, so this pins the weaker invariant that IS checkable --
    the gated name is lexitrail's, not a copy-paste from a sibling project."""
    names = _lexitrail_cfg().get("gate_triggers") or []
    assert names, "covered by the test above; this one assumes non-empty"
    for n in names:
        assert n.startswith("lexitrail-"), (
            f"gated trigger {n!r} is not a lexitrail trigger -- the vendored "
            "config was copied from a sibling project and gates someone else's "
            "builds while lexitrail's own run ungated."
        )


# ─── issue-216: the UI config must actually ROLL, and prove it rolled ─────────
#
# Until 2026-08-29 `cloudbuild-ui.yaml` stopped after the push. Every assertion
# above passed on it — the gate was wired, the cache was wired, logging was set —
# and merging UI work still changed nothing anyone could see. A green build was
# the whole symptom, so these pins are about what the build DOES, not whether it
# succeeds.

_UI = _ROOT / "cloudbuild-ui.yaml"


def _ui_steps():
    return {s["id"]: s for s in yaml.safe_load(_UI.read_text())["steps"]}


def _ui_step_script(step_id):
    steps = _ui_steps()
    # A missing step is the ORIGINAL bug (build-and-push-only), so say that
    # rather than letting a KeyError stand in for it -- the next editor to see
    # this red should read what it means, not a traceback.
    assert step_id in steps, (
        f"issue-216: cloudbuild-ui.yaml has no `{step_id}` step. That is the "
        "pre-2026-08-29 build-and-push-only shape: the build goes green and the "
        "served site never changes."
    )
    return "\n".join(steps[step_id].get("args", []))


def test_ui_config_has_no_images_block_216():
    """BUG SHAPE. `images:` pushes AFTER every step, so a deploy step can never
    see the digest it needs — `images:` and "roll it in this build" are mutually
    exclusive. Reintroducing it would ALSO leave two places deciding what ships."""
    doc = yaml.safe_load(_UI.read_text())
    assert "images" not in doc, (
        "issue-216: cloudbuild-ui.yaml grew an `images:` block back. It pushes "
        "after all steps, so ui-deploy cannot read the digest — the build goes "
        "green and the site stays stale, which is the whole bug."
    )


def test_ui_config_rolls_the_deployment_216():
    ids = _ui_steps()
    for needed in ("ui-push", "ui-deploy", "ui-smoke"):
        assert needed in ids, f"issue-216: cloudbuild-ui.yaml lost its `{needed}` step"


def test_ui_deploy_uses_set_image_not_rollout_restart_216():
    """BUG SHAPE. The Deployment is DIGEST-pinned: `rollout restart` re-pulls
    identical bytes and `rollout status` then reports success for a no-op. Only
    `set image` to a new digest ships anything."""
    script = _ui_step_script("ui-deploy")
    assert "set image" in script, "issue-216: ui-deploy no longer uses `set image`"
    assert "rollout restart" not in script, (
        "issue-216: ui-deploy uses `rollout restart` — inert on a digest-pinned "
        "Deployment, and it reports success while shipping nothing"
    )


def test_ui_deploy_reads_the_live_spec_back_and_compares_216():
    """`rollout status` has no opinion on whether the IMAGE changed. The
    read-back comparison is the only thing here that can tell a real deploy from
    a no-op, so it must exist AND must fail the build on mismatch."""
    script = _ui_step_script("ui-deploy")
    assert "jsonpath" in script and "containers[0].image" in script, (
        "issue-216: ui-deploy no longer reads the live image back off the spec"
    )
    assert "DEPLOY-FAIL" in script and "exit 1" in script, (
        "issue-216: the read-back no longer FAILS the build on mismatch — a "
        "comparison whose result is discarded is not a check"
    )


def test_ui_push_refuses_an_empty_digest_216():
    """CANNOT-TELL must not proceed as success. An empty digest would make
    `set image` a no-op argument and the read-back would compare '' to '' and
    pass — a green build, a stale site, and a check that certified it."""
    script = _ui_step_script("ui-push")
    assert "PUSH-FAIL" in script, (
        "issue-216: ui-push no longer refuses an empty digest; an unparsed push "
        "output would silently deploy nothing and still read as verified"
    )


def test_ui_push_does_not_take_the_digest_from_repodigests_216():
    """`.RepoDigests` is a LIST with one entry per tag, so `index 0` picks
    whichever the daemon happened to order first. The push output names the
    bytes unambiguously."""
    script = _ui_step_script("ui-push")
    assert "RepoDigests" not in script, (
        "issue-216: ui-push reads .RepoDigests — ambiguous across the two tags "
        "this build pushes; parse the push output instead"
    )


def test_ui_smoke_fails_the_build_on_cannot_tell_too_216():
    """zz1 relaying Alex: wire CANNOT-TELL *and* FAIL to a surface guaranteed to
    be seen. Exit 3 is CANNOT-TELL — if it were swallowed, a dead instrument
    would render exactly like a healthy deploy.

    Goes through `_ui_step_script()` rather than indexing `_ui_steps()` directly:
    hc2 caught (PR #237 review) that this was the ONE pin of the seven that
    bypassed the guard, so a missing step threw a bare KeyError — inside the very
    change whose stated purpose is making that case legible.
    """
    script = _ui_step_script("ui-smoke")
    assert "smoke_served_content.py" in script, "issue-216: ui-smoke no longer runs the smoke"
    # `$$rc`, NOT `$rc`: Cloud Build substitutes `$VAR` before bash sees it, so a
    # single `$` rejects the BUILD at validation (that is the 02:00Z rejection).
    assert 'exit "$$rc"' in script, (
        "issue-216: ui-smoke no longer propagates the smoke's exit code — "
        "swallowing exit 3 (CANNOT-TELL) makes a dead instrument look green. "
        "(If you just changed `$$rc` to `$rc`, that ALSO rejects the build.)"
    )
    assert _ui_steps()["ui-smoke"].get("waitFor") == ["ui-deploy"], (
        "issue-216: ui-smoke must run AFTER ui-deploy, or it smokes the OLD site "
        "and passes on the state the deploy was supposed to change"
    )


# ─── issue-216: Cloud Build substitutes $VAR before bash ever sees it ─────────
#
# 🔴 THIS IS THE GAP THAT SHIPPED. The 2026-08-29 02:00Z build was REJECTED at
# validation, before step 0, with:
#
#     invalid value for 'build.substitutions': key in the template "DIGEST"
#     is not a valid built-in substitution
#
# `$DIGEST` in an inline script is not a shell variable to Cloud Build — it is a
# SUBSTITUTION, and an unknown one rejects the whole build. Shell vars must be
# written `$$VAR`.
#
# Nothing then in this file could have caught it: `yaml.safe_load` parses the
# document fine, and every other assertion here is about structure. A config that
# PARSES is not a config that VALIDATES, and the rejection happens server-side
# before any step runs — so there is no local signal at all without this rule.
#
# ⚠️ Cloud Build reports only the FIRST offending key. Five were present across
# three steps (DIGEST, LIVE, REF, i, rc); fixing them one report at a time would
# have cost four merge-and-reject cycles. This checks ALL of them at once, which
# is the whole reason it is a rule and not a fix.
#
# (Free, at least: a validation rejection never reaches `quota-gate`, so it is
# invisible to the budget — the build costs no unit. That is documented in
# cloudbuild-ui.yaml's logging note, from issue-228 hitting the same class.)

# https://cloud.google.com/build/docs/configuring-builds/substitute-variable-values
_BUILTIN_SUBSTITUTIONS = {
    "PROJECT_ID", "PROJECT_NUMBER", "BUILD_ID", "LOCATION", "TRIGGER_NAME",
    "COMMIT_SHA", "SHORT_SHA", "REVISION_ID", "REPO_NAME", "REPO_FULL_NAME",
    "BRANCH_NAME", "TAG_NAME", "SERVICE_ACCOUNT", "SERVICE_ACCOUNT_EMAIL",
    "TRIGGER_BUILD_CONFIG_PATH",
}

# `$FOO` / `${FOO}` NOT preceded by another `$` (i.e. not already escaped).
_UNESCAPED_VAR = re.compile(r"(?<!\$)\$\{([A-Za-z_][A-Za-z0-9_]*)\}|(?<!\$)\$([A-Za-z_][A-Za-z0-9_]*)")


@pytest.mark.parametrize("path,build_id", CONFIGS, ids=lambda v: getattr(v, "name", v))
def test_no_unescaped_shell_vars_in_inline_scripts_216(path, build_id):
    """Every `$VAR` in a step's args must be a Cloud Build builtin, a `_`-prefixed
    user substitution, or escaped `$$VAR` for the shell. Anything else rejects the
    BUILD AT VALIDATION — no step runs, and the only place it is visible is the
    build's `statusDetail`."""
    doc = yaml.safe_load(path.read_text())
    declared = set(doc.get("substitutions", {}))
    offenders = {}
    for step in doc.get("steps", []):
        body = "\n".join(step.get("args", []) or [])
        names = {m.group(1) or m.group(2) for m in _UNESCAPED_VAR.finditer(body)}
        bad = sorted(
            n for n in names
            if n not in _BUILTIN_SUBSTITUTIONS and n not in declared and not n.startswith("_")
        )
        if bad:
            offenders[step.get("id")] = bad
    assert not offenders, (
        f"issue-216: unescaped shell variables in {path.name} — Cloud Build reads these as "
        f"SUBSTITUTIONS and rejects the build at validation, before step 0: {offenders}. "
        "Write them `$$VAR`. Note Cloud Build reports only the FIRST one, so fixing what it "
        "names is not the same as fixing this."
    )


def test_the_substitution_rule_can_actually_fail_216():
    """POSITIVE CONTROL. The check above passes trivially on a config with no
    inline scripts, so on its own a green run says nothing. Drive it to the other
    verdict on a synthetic step to prove it discriminates."""
    names = {m.group(1) or m.group(2)
             for m in _UNESCAPED_VAR.finditer('D="$(cmd)"\n[ -n "$D" ] || exit 1')}
    assert "D" in names, "the detector cannot see an unescaped var — it would pass on anything"
    escaped = {m.group(1) or m.group(2)
               for m in _UNESCAPED_VAR.finditer('D="$$(cmd)"\n[ -n "$$D" ] || exit 1')}
    assert not escaped, f"the detector flags CORRECTLY escaped vars: {escaped} — it would red every fixed config"
    assert not ({m.group(1) or m.group(2)
                 for m in _UNESCAPED_VAR.finditer("docker build -t x:$SHORT_SHA .")}
                - _BUILTIN_SUBSTITUTIONS), "a builtin must not be flagged"


def test_ui_smoke_allows_exit_3_but_never_exit_1_240():
    """issue-240 AC6, and the correction of my own #237 wiring.

    That version failed the build on ANY non-zero exit, collapsing FAIL (1) and
    CANNOT-TELL (3) into one red — which #235 AC3 said not to do, before the step
    existed, on the grounds that it trains people to ignore the alarm. It came
    true on the first real fire.

    `allowExitCodes: [3]` keeps both properties: the step's status is still
    recorded as FAILURE on exit 3 (seen), and the build stays green (not a claim
    about the code). Seen is not the same as identical.
    """
    step = _ui_steps()["ui-smoke"]
    allowed = step.get("allowExitCodes")
    assert allowed == [3], (
        f"issue-240 AC6: ui-smoke must allow ONLY exit 3, got {allowed!r}. "
        "Empty/absent collapses CANNOT-TELL into FAIL (the #237 bug #235 AC3 "
        "predicted); including 1 would let a STALE DEPLOY pass, which is the "
        "entire thing this step exists to catch."
    )


def test_ui_smoke_still_propagates_the_code_it_allows_240():
    """NEGATIVE CONTROL for the above. `allowExitCodes` only means anything if the
    step actually EXITS with the smoke's code — a script that swallowed the code
    and exited 0 would make the allowance decorative and the step permanently
    green, which is the failure mode inverted."""
    script = _ui_step_script("ui-smoke")
    assert 'exit "$$rc"' in script, (
        "issue-240: ui-smoke no longer propagates the smoke's exit code, so "
        "allowExitCodes has nothing to act on and the step can never report "
        "anything at all"
    )
