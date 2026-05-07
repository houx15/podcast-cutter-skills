"""Tests for shared.scripts.lib.json_io."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from shared.scripts.lib import json_io


def test_dump_and_load_roundtrip(tmp_path: Path) -> None:
    payload = {"speakers": [{"id": "S1", "name": None}], "duration_ms": 7200000}
    target = tmp_path / "out.json"
    json_io.dump_json(payload, target)
    assert json_io.load_json(target) == payload


def test_dump_is_atomic_against_partial_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crash mid-write must not leave a partial file at the target path.

    json_io.dump_json must write to <path>.tmp then os.replace.
    """
    target = tmp_path / "out.json"
    target.write_text(json.dumps({"old": True}))  # pre-existing good file

    real_replace = json_io.os.replace

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated crash before rename completes")

    monkeypatch.setattr(json_io.os, "replace", boom)
    with pytest.raises(RuntimeError):
        json_io.dump_json({"new": True}, target)

    # Original file is untouched.
    assert json.loads(target.read_text()) == {"old": True}
    # No stray .tmp file blocks future writes.
    monkeypatch.setattr(json_io.os, "replace", real_replace)
    json_io.dump_json({"new": True}, target)
    assert json_io.load_json(target) == {"new": True}


def test_dump_ensures_chinese_text_not_escaped(tmp_path: Path) -> None:
    target = tmp_path / "zh.json"
    json_io.dump_json({"text": "做播客最难的不是开始"}, target)
    raw = target.read_text(encoding="utf-8")
    assert "做播客" in raw
    assert "\\u" not in raw  # no escape of CJK


def test_dump_creates_parent_dirs(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "nested" / "out.json"
    json_io.dump_json({"k": 1}, target)
    assert target.exists()


def test_load_missing_file_raises_filenotfound(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        json_io.load_json(tmp_path / "nope.json")
