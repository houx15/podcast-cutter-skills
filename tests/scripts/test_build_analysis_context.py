#!/usr/bin/env python3
"""Tests for build_analysis_context.py — written first (TDD red phase)."""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest.mock
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load():
    spec = importlib.util.spec_from_file_location(
        "build_analysis_context", SCRIPTS / "build_analysis_context.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _setup(tmp_path):
    ep = tmp_path / "ep"
    td = ep / "1_transcribe"
    td.mkdir(parents=True)
    (ep / "2_analysis").mkdir(parents=True)

    sentences = {
        "sentences": [
            {"id": 0, "speaker": "S1", "start_ms": 0, "end_ms": 3000, "text": "录前闲聊"},
            {"id": 1, "speaker": "S2", "start_ms": 3500, "end_ms": 8000, "text": "正式内容"},
        ]
    }
    (td / "sentences.json").write_text(json.dumps(sentences))

    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    (rules_dir / "1-核心原则.md").write_text("# 核心原则\n删掉录前闲聊。")
    prefs_dir = tmp_path / "prefs"
    prefs_dir.mkdir()
    (prefs_dir / "preferences.yaml").write_text("aggressiveness: moderate\n")
    return ep, rules_dir, prefs_dir


def test_writes_analysis_context(tmp_path):
    ep, rules_dir, prefs_dir = _setup(tmp_path)
    mod = _load()
    with unittest.mock.patch(
        "sys.argv",
        [
            "build_analysis_context.py",
            "--ep-dir",
            str(ep),
            "--rules-dir",
            str(rules_dir),
            "--prefs-file",
            str(prefs_dir / "preferences.yaml"),
        ],
    ):
        mod.main()

    ctx = ep / "2_analysis" / "analysis_context.md"
    assert ctx.exists()
    text = ctx.read_text()
    assert "核心原则" in text
    assert "aggressiveness" in text
    assert "录前闲聊" in text
    assert "00:00" in text


def test_contains_output_format_spec(tmp_path):
    ep, rules_dir, prefs_dir = _setup(tmp_path)
    mod = _load()
    with unittest.mock.patch(
        "sys.argv",
        [
            "build_analysis_context.py",
            "--ep-dir",
            str(ep),
            "--rules-dir",
            str(rules_dir),
            "--prefs-file",
            str(prefs_dir / "preferences.yaml"),
        ],
    ):
        mod.main()

    text = (ep / "2_analysis" / "analysis_context.md").read_text()
    assert "rough_cuts.json" in text
    assert "fine_cuts.json" in text
    assert "self_review.json" in text
    assert "agent_rough" in text
    assert "agent_fine" in text


def test_missing_sentences_raises(tmp_path):
    ep = tmp_path / "ep"
    (ep / "1_transcribe").mkdir(parents=True)
    (ep / "2_analysis").mkdir(parents=True)
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    prefs_dir = tmp_path / "prefs"
    prefs_dir.mkdir()
    (prefs_dir / "preferences.yaml").write_text("")
    mod = _load()
    with unittest.mock.patch(
        "sys.argv",
        [
            "build_analysis_context.py",
            "--ep-dir",
            str(ep),
            "--rules-dir",
            str(rules_dir),
            "--prefs-file",
            str(prefs_dir / "preferences.yaml"),
        ],
    ):
        with pytest.raises((FileNotFoundError, SystemExit)):
            mod.main()


def test_default_rules_and_prefs_paths(tmp_path):
    ep, _, _ = _setup(tmp_path)
    mod = _load()
    with unittest.mock.patch(
        "sys.argv",
        [
            "build_analysis_context.py",
            "--ep-dir",
            str(ep),
        ],
    ):
        mod.main()  # uses real repo rules

    assert (ep / "2_analysis" / "analysis_context.md").exists()
