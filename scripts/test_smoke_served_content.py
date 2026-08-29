"""Pins the THREE-state contract of the served-content smoke (issue-77 AC3).

The live four-arm run in PR review proved the instrument discriminates today.
This file exists so it cannot silently stop, offline and in CI.

The load-bearing assertion is `test_dead_control_is_cannot_tell_not_pass`. Every
other check here would still pass if someone "simplified" the control away, and
the resulting smoke would then report a healthy deploy for the rest of its life
without ever looking at one -- which is the exact failure #77 was filed about,
reintroduced inside the fix for it.
"""
from __future__ import annotations

import importlib.util
import sys
import urllib.error
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent / "smoke_served_content.py"
_spec = importlib.util.spec_from_file_location("smoke_served_content", _SRC)
smoke = importlib.util.module_from_spec(_spec)
sys.modules["smoke_served_content"] = smoke
_spec.loader.exec_module(smoke)

SHELL = (200, "text/html; charset=utf-8", b"<html>spa shell</html>")
PNG = (200, "image/png", b"\x89PNG" + b"\x00" * 512)
OG = "/images/og/generated/og-landscape.png"


def _http_error(code: int, url: str = "https://x.test/x"):
    """issue-240: what the live site now does on an unknown path.

    `urllib` RAISES on 4xx, and `HTTPError` is a SUBCLASS of `URLError` -- which is
    how "404 as designed" and "the site did not answer" came to share one branch.
    Tests must raise the real class, not a stand-in, or they cannot exercise that
    ordering at all.
    """
    return urllib.error.HTTPError(url, code, "err", hdrs=None, fp=None)


NOT_FOUND = _http_error(404)


def _repo(tmp_path: Path, og: str = "%PUBLIC_URL%" + OG) -> Path:
    idx = tmp_path / "ui" / "public"
    idx.mkdir(parents=True)
    (idx / "index.html").write_text(
        f'<html><head><meta property="og:image" content="{og}"></head></html>'
    )
    # issue-240 AC5: the known-good route is READ from serve.json, not hard-coded,
    # so a fixture without one is a fixture the script must refuse to guess from.
    (idx / "serve.json").write_text(
        '{"rewrites":[{"source":"/","destination":"/index.html"}]}'
    )
    return tmp_path


def _run(monkeypatch, routes, repo_root, base="https://x.test"):
    """Route by suffix so a test states which URL returns what, not call order."""

    def fake(url, timeout=20.0):
        for suffix, resp in routes.items():
            if url.endswith(suffix):
                if isinstance(resp, Exception):
                    raise resp
                return resp
        raise AssertionError(f"test did not stub {url}")

    monkeypatch.setattr(smoke, "_fetch", fake)
    return smoke.main(["--base", base, "--repo-root", str(repo_root)])


def test_healthy_site_passes(monkeypatch, tmp_path):
    assert _run(
        monkeypatch,
        {smoke.CONTROL_PATH: NOT_FOUND, OG: PNG, "/": (200, "text/html", f'<meta property="og:image" content="{OG}">'.encode())},
        _repo(tmp_path),
    ) == smoke.PASS


def test_stale_deploy_fails(monkeypatch, tmp_path):
    """The served page still advertises the OLD asset. Status is 200 throughout."""
    served = b'<meta property="og:image" content="/images/og/generated/og-OLD.png">'
    assert _run(
        monkeypatch,
        {smoke.CONTROL_PATH: NOT_FOUND, "/": (200, "text/html", served)},
        _repo(tmp_path),
    ) == smoke.FAIL


def test_asset_that_200s_as_the_shell_fails(monkeypatch, tmp_path):
    """The og:image URL returns 200 -- and serves HTML. This is #77's whole point."""
    assert _run(
        monkeypatch,
        {smoke.CONTROL_PATH: NOT_FOUND, OG: SHELL, "/": (200, "text/html", f'<meta property="og:image" content="{OG}">'.encode())},
        _repo(tmp_path),
    ) == smoke.FAIL


def test_dead_control_is_cannot_tell_not_pass(monkeypatch, tmp_path):
    """🔴 THE ONE THAT MATTERS.

    Everything downstream is healthy -- the og:image matches and serves a real
    PNG -- so a smoke without a control would return PASS here and be right by
    accident. The control path answering `image/png` means the catch-all has
    changed and "is it an image" no longer separates a served asset from a
    served shell. The correct answer is CANNOT-TELL, and it must not be PASS.
    """
    rc = _run(
        monkeypatch,
        {smoke.CONTROL_PATH: PNG, OG: PNG, "/": (200, "text/html", f'<meta property="og:image" content="{OG}">'.encode())},
        _repo(tmp_path),
    )
    assert rc == smoke.CANNOT_TELL, (
        "a smoke whose discriminator has died must refuse to answer, not pass"
    )
    assert rc != smoke.PASS


def test_unreachable_site_is_cannot_tell_not_fail(monkeypatch, tmp_path):
    """A network error says nothing about the deploy -- it must not read as a bug."""
    assert _run(
        monkeypatch,
        {smoke.CONTROL_PATH: OSError("connection refused")},
        _repo(tmp_path),
    ) == smoke.CANNOT_TELL


def test_missing_source_is_cannot_tell(monkeypatch, tmp_path):
    assert _run(monkeypatch, {smoke.CONTROL_PATH: SHELL}, tmp_path) == smoke.CANNOT_TELL


def test_public_url_token_is_resolved_not_compared_raw(tmp_path):
    """CRA's build-time token must be expanded, or every run is a false FAIL."""
    assert smoke._repo_og(_repo(tmp_path)) == OG


def test_the_three_exit_codes_are_distinct():
    """A regression that aliased CANNOT_TELL to PASS would be invisible above."""
    assert len({smoke.PASS, smoke.FAIL, smoke.CANNOT_TELL}) == 3


# ─── issue-240: the control was invalidated by the fix it verifies ───────────
#
# The control required the SPA shell back, because when this script was written
# every path on the site returned 200. That was issue-204's BUG. #204's fix went
# live 2026-08-29 and unknown paths now 404, so the control reported CANNOT-TELL
# on every run — a permanently-red step, which is the muted-alarm outcome #235
# AC3 predicted before the wiring was written.
#
# These pin the NEW contract: unknown paths 404, enumerated routes 200.


def test_control_200_is_cannot_tell_because_the_catch_all_regressed_240(monkeypatch, tmp_path):
    """BUG SHAPE, INVERTED. A 200 on the control path used to be REQUIRED; it is
    now the anomaly — it means #204 regressed and unknown paths are being served
    as real pages again. It must not pass, and it must not read as a mere probe
    problem: it is a finding about the site."""
    assert _run(
        monkeypatch,
        {smoke.CONTROL_PATH: SHELL, OG: PNG,
         "/": (200, "text/html", f'<meta property="og:image" content="{OG}">'.encode())},
        _repo(tmp_path),
    ) == smoke.CANNOT_TELL


def test_control_404_and_network_failure_do_not_share_a_branch_240(monkeypatch, tmp_path):
    """AC3. `HTTPError` is a SUBCLASS of `URLError`, so catching them together
    made 'the site 404'd exactly as designed' and 'the site did not answer'
    indistinguishable — two facts wearing one value.

    404 is the healthy state and must reach PASS. A genuine network failure must
    still be CANNOT-TELL. If these ever collapse again, one of these two reds."""
    repo = _repo(tmp_path)   # built ONCE: _repo is not idempotent, by design
    ok_routes = {OG: PNG,
                 "/": (200, "text/html", f'<meta property="og:image" content="{OG}">'.encode())}

    healthy = _run(monkeypatch, {smoke.CONTROL_PATH: NOT_FOUND, **ok_routes}, repo)
    assert healthy == smoke.PASS, "a 404 control is the HEALTHY state post-#204"

    dead = _run(monkeypatch,
                {smoke.CONTROL_PATH: urllib.error.URLError("no route to host"), **ok_routes},
                repo)
    assert dead == smoke.CANNOT_TELL, "an unreachable site is not a healthy 404"

    # The two must differ. Asserting each value separately would still pass if a
    # future edit made BOTH return CANNOT_TELL -- which is the exact collapse.
    assert healthy != dead, "404-as-designed and site-unreachable collapsed again"


def test_a_non_404_http_error_on_the_control_is_cannot_tell_240(monkeypatch, tmp_path):
    """A 500 on the control is neither the guaranteed 404 nor a reachable answer.
    Without this, `exc.code != 404` could fall through to whatever the last branch
    happens to be — and the third state must never render as the first."""
    assert _run(
        monkeypatch,
        {smoke.CONTROL_PATH: _http_error(500), OG: PNG,
         "/": (200, "text/html", f'<meta property="og:image" content="{OG}">'.encode())},
        _repo(tmp_path),
    ) == smoke.CANNOT_TELL


def test_known_good_route_is_read_from_serve_json_not_hard_coded_240(tmp_path):
    """AC5, hc2's proposal on #241. `serve.json`'s rewrites ARE the declaration of
    what this site routes, so deriving from it means the check cannot drift away
    from the config that decides the answer — the same property the og:image
    expectation already gets by reading `index.html`."""
    repo = _repo(tmp_path)
    assert smoke._known_good_route(repo) == "/"

    (repo / "ui" / "public" / "serve.json").write_text(
        '{"rewrites":[{"source":"/game/:id","destination":"/index.html"},'
        '{"source":"/wordsets/**","destination":"/index.html"},'
        '{"source":"/privacy","destination":"/index.html"}]}'
    )
    assert smoke._known_good_route(repo) == "/privacy", (
        "must skip :param and ** sources — they are patterns, not fetchable routes"
    )


def test_absent_serve_json_is_cannot_tell_not_a_guessed_route_240(monkeypatch, tmp_path):
    """NEGATIVE CONTROL for AC5. With no serve.json there is no route the site is
    DECLARED to serve, so a fetch failure could not be told apart from a route
    that simply is not routed. Guessing `/` would put us back to hard-coding with
    an extra step."""
    repo = _repo(tmp_path)
    (repo / "ui" / "public" / "serve.json").unlink()
    assert _run(
        monkeypatch,
        {smoke.CONTROL_PATH: NOT_FOUND, OG: PNG,
         "/": (200, "text/html", f'<meta property="og:image" content="{OG}">'.encode())},
        repo,
    ) == smoke.CANNOT_TELL
