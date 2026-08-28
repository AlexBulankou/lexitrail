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


def _repo(tmp_path: Path, og: str = "%PUBLIC_URL%" + OG) -> Path:
    idx = tmp_path / "ui" / "public"
    idx.mkdir(parents=True)
    (idx / "index.html").write_text(
        f'<html><head><meta property="og:image" content="{og}"></head></html>'
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
        {smoke.CONTROL_PATH: SHELL, OG: PNG, "/": (200, "text/html", f'<meta property="og:image" content="{OG}">'.encode())},
        _repo(tmp_path),
    ) == smoke.PASS


def test_stale_deploy_fails(monkeypatch, tmp_path):
    """The served page still advertises the OLD asset. Status is 200 throughout."""
    served = b'<meta property="og:image" content="/images/og/generated/og-OLD.png">'
    assert _run(
        monkeypatch,
        {smoke.CONTROL_PATH: SHELL, "/": (200, "text/html", served)},
        _repo(tmp_path),
    ) == smoke.FAIL


def test_asset_that_200s_as_the_shell_fails(monkeypatch, tmp_path):
    """The og:image URL returns 200 -- and serves HTML. This is #77's whole point."""
    assert _run(
        monkeypatch,
        {smoke.CONTROL_PATH: SHELL, OG: SHELL, "/": (200, "text/html", f'<meta property="og:image" content="{OG}">'.encode())},
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
