"""Tests for shared/scripts/install/verify_volcano.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from shared.scripts.install import verify_volcano

_LLM_KEYS = (
    "LLM_API_KEY=ark-test\n"
    "LLM_BASE_URL=https://ark.example.com/api/v3\n"
    "LLM_MODEL=doubao-test\n"
)


def test_verify_volcano_reports_missing_creds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = tmp_path / ".env"
    env.write_text("VOLC_RESOURCE_ID=volc.seedasr.auc\n" + _LLM_KEYS)
    rc = verify_volcano.main(env_path=env, do_network=False)
    assert rc != 0
    out = capsys.readouterr().out + capsys.readouterr().err
    assert "VOLC_API_KEY" in out or "Volcano" in out


def test_verify_volcano_dry_run_passes_with_creds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "VOLC_API_KEY=newkey\nVOLC_RESOURCE_ID=volc.seedasr.auc\n" + _LLM_KEYS
    )
    rc = verify_volcano.main(env_path=env, do_network=False)
    assert rc == 0
    out = capsys.readouterr().out
    assert "ok" in out.lower() or "passed" in out.lower()
