# tests/scripts/test_align_tracks.py
"""TDD tests for align_tracks.py (stage 1.05)."""
import importlib.util
import json
import sys
import unittest.mock
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "shared" / "scripts"

sys.path.insert(0, str(SCRIPTS))


def _load_mod():
    spec = importlib.util.spec_from_file_location(
        "align_tracks", SCRIPTS / "align_tracks.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _audio_meta(n_tracks: int) -> dict:
    tracks = [
        {"file": f"working_track{i}.wav", "duration_ms": 30000, "sample_rate": 44100}
        for i in range(1, n_tracks + 1)
    ]
    return {
        "episode_id": "ep_test",
        "mode": "two_track" if n_tracks >= 2 else "single_track",
        "tracks": tracks,
        "total_duration_ms": 30000,
    }


def _raw_json(words: list[dict]) -> dict:
    """Build a volcano raw JSON fixture."""
    return {
        "resp": {
            "code": "20000000",
            "task_id": "t1",
            "utterances": [{"words": words}],
        }
    }


# ---------------------------------------------------------------------------
# Test 1: timestamp mode
# ---------------------------------------------------------------------------

def test_timestamp_offset(tmp_path):
    """--t1 10:00:00 --t2 10:00:03 → offsets [0, 3000]."""
    ep_dir = tmp_path / "ep01"
    in_dir = ep_dir / "input"
    in_dir.mkdir(parents=True)
    (in_dir / "audio_meta.json").write_text(json.dumps(_audio_meta(2)))

    mod = _load_mod()
    with unittest.mock.patch("sys.argv", [
        "align_tracks.py",
        "--ep-dir", str(ep_dir),
        "--t1", "10:00:00",
        "--t2", "10:00:03",
    ]):
        mod.main()

    meta = json.loads((in_dir / "audio_meta.json").read_text())
    assert meta["track_offsets_ms"] == [0, 3000]


# ---------------------------------------------------------------------------
# Test 2: transcript mode
# ---------------------------------------------------------------------------

def test_transcript_offset(tmp_path):
    """Transcript mode: same 4 words, track2 starts 500ms later → offset ~500ms."""
    ep_dir = tmp_path / "ep01"
    in_dir = ep_dir / "input"
    td = ep_dir / "1_transcribe"
    in_dir.mkdir(parents=True)
    td.mkdir(parents=True)
    (in_dir / "audio_meta.json").write_text(json.dumps(_audio_meta(2)))

    texts = ["你好", "世界", "测试", "完成"]
    base = 1000  # ms per word gap

    words1 = [
        {
            "text": t,
            "start_time": i * base,
            "end_time": i * base + 300,
            "confidence": 0.9,
            "blank_duration": 50,
        }
        for i, t in enumerate(texts, start=1)
    ]
    words2 = [
        {
            "text": t,
            "start_time": i * base + 500,
            "end_time": i * base + 800,
            "confidence": 0.9,
            "blank_duration": 50,
        }
        for i, t in enumerate(texts, start=1)
    ]

    (td / "volcano_raw_track1.json").write_text(json.dumps(_raw_json(words1)))
    (td / "volcano_raw_track2.json").write_text(json.dumps(_raw_json(words2)))

    mod = _load_mod()
    with unittest.mock.patch("sys.argv", ["align_tracks.py", "--ep-dir", str(ep_dir)]):
        mod.main()

    meta = json.loads((in_dir / "audio_meta.json").read_text())
    offsets = meta["track_offsets_ms"]
    assert offsets[0] == 0
    assert abs(offsets[1] - 500) < 50


# ---------------------------------------------------------------------------
# Test 3: single-track no-op
# ---------------------------------------------------------------------------

def test_single_track_noop(tmp_path):
    """Single-track episode: write track_offsets_ms = [0] and exit."""
    ep_dir = tmp_path / "ep01"
    in_dir = ep_dir / "input"
    in_dir.mkdir(parents=True)
    (in_dir / "audio_meta.json").write_text(json.dumps(_audio_meta(1)))

    mod = _load_mod()
    with unittest.mock.patch("sys.argv", ["align_tracks.py", "--ep-dir", str(ep_dir)]):
        mod.main()

    meta = json.loads((in_dir / "audio_meta.json").read_text())
    assert meta["track_offsets_ms"] == [0]
