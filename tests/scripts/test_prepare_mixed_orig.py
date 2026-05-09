"""Tests for prepare_mixed_orig.py — produces input/mixed_orig.wav from
working_track1+2.wav with track_offsets_ms applied.

Used by the Stage 3 review UI so the user can audition proposed cuts in
the original (pre-delete) mixed audio."""
import json, re, shutil, subprocess
from pathlib import Path
import pytest

REPO = "/Users/houyuxin/08Coding/podcast-cutter-skills"
SCRIPT = REPO + "/shared/scripts/prepare_mixed_orig.py"


def _make_wav(out: Path, freq: int, duration_s: float = 5):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         f"sine=frequency={freq}:duration={duration_s}",
         "-af", "volume=8", "-ar", "44100", "-ac", "1",
         "-c:a", "pcm_s16le", str(out)],
        check=True, capture_output=True,
    )


def _segment_max_db(wav: Path, start_s: float, end_s: float) -> float:
    r = subprocess.run(
        ["ffmpeg", "-i", str(wav),
         "-af", f"atrim={start_s}:{end_s},asetpts=PTS-STARTPTS,volumedetect",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    m = re.search(r"max_volume:\s+(-?[\d.]+)\s*dB", r.stderr)
    return float(m.group(1)) if m else -100.0


def _setup_ep(tmp_path, t1_freq=440, t2_freq=880, offsets=(0, 0)):
    ep = tmp_path / "ep01"
    (ep / "input").mkdir(parents=True)
    t1 = ep / "input" / "working_track1.wav"
    t2 = ep / "input" / "working_track2.wav"
    _make_wav(t1, t1_freq)
    _make_wav(t2, t2_freq)
    meta = {
        "episode_id": "ep01", "mode": "two_track",
        "tracks": [
            {"file": "working_track1.wav", "duration_ms": 5000, "sample_rate": 44100},
            {"file": "working_track2.wav", "duration_ms": 5000, "sample_rate": 44100},
        ],
        "total_duration_ms": 5000,
        "track_offsets_ms": list(offsets),
    }
    (ep / "input" / "audio_meta.json").write_text(json.dumps(meta))
    return ep


def test_creates_mixed_orig_wav(tmp_path):
    ep = _setup_ep(tmp_path)
    subprocess.run(
        ["python", SCRIPT, "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO,
    )
    out = ep / "input" / "mixed_orig.wav"
    assert out.exists()
    # Both speakers should be audible somewhere
    assert _segment_max_db(out, 1.0, 4.0) > -25.0


def test_applies_track_offsets(tmp_path):
    """track2 offset of 2000ms means track2 contributes from 2-7s in the mix.
    With a 5s track2 and offset, total mix ~ 7s (longest), and 6.0-6.5s should
    have only track2 (track1 ended at 5s)."""
    ep = _setup_ep(tmp_path, offsets=(0, 2000))
    subprocess.run(
        ["python", SCRIPT, "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO,
    )
    out = ep / "input" / "mixed_orig.wav"
    assert out.exists()
    # Section 6.0-6.5s: only track2 (offset by 2s, ends at 7s) should be there.
    assert _segment_max_db(out, 6.0, 6.5) > -25.0
    # Section 0.5-1.5s: only track1 (track2 hasn't started yet).
    assert _segment_max_db(out, 0.5, 1.5) > -25.0


def test_single_track_mode_copies_track1(tmp_path):
    ep = tmp_path / "ep02"
    (ep / "input").mkdir(parents=True)
    _make_wav(ep / "input" / "working_track1.wav", 440)
    meta = {
        "episode_id": "ep02", "mode": "single_track",
        "tracks": [{"file": "working_track1.wav", "duration_ms": 5000, "sample_rate": 44100}],
        "total_duration_ms": 5000,
    }
    (ep / "input" / "audio_meta.json").write_text(json.dumps(meta))
    subprocess.run(
        ["python", SCRIPT, "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO,
    )
    out = ep / "input" / "mixed_orig.wav"
    assert out.exists()
    assert _segment_max_db(out, 1.0, 4.0) > -25.0
