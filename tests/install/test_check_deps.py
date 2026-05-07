"""Tests for shared/scripts/install/check_deps.sh."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parent.parent.parent
    / "shared/scripts/install/check_deps.sh"
)


def test_check_deps_passes_when_all_present() -> None:
    if not all(shutil.which(b) for b in ["node", "ffmpeg", "python3"]):
        pytest.skip("real deps not installed; cannot verify pass path")
    proc = subprocess.run(
        ["bash", str(SCRIPT)], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr


def test_check_deps_fails_when_dep_missing(tmp_path: Path) -> None:
    """Run with PATH set to an empty dir so no binaries are found."""
    bash = shutil.which("bash") or "/bin/bash"
    proc = subprocess.run(
        [bash, str(SCRIPT)],
        capture_output=True,
        text=True,
        env={"PATH": str(tmp_path), "HOME": os.environ.get("HOME", "/tmp")},
    )
    assert proc.returncode != 0
    assert "not found" in proc.stdout.lower() or "missing" in proc.stdout.lower()
