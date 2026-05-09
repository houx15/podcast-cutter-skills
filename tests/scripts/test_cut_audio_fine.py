"""Tests for cut_audio_fine.py — applies cut-timeline deletes to a single
mixed input wav.

Critical invariant: input is the post-coarse-cut wav (single track, already
mixed). Deletes are in THIS wav's timeline, not the original recording's.
No cut→orig translation. No mixing.
"""
import json, re, shutil, subprocess
from pathlib import Path
import pytest

REPO = "/Users/houyuxin/08Coding/podcast-cutter-skills"
SCRIPT = REPO + "/shared/scripts/cut_audio_fine.py"


@pytest.fixture
def tone_wav(tmp_path):
    """10-second 440Hz tone."""
    out = tmp_path / "in.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=10",
         "-af", "volume=8", "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(out)],
        check=True, capture_output=True,
    )
    return out


def _setup_ep(tmp_path, src_wav, deletes):
    ep = tmp_path / "ep01"
    (ep / "4_cut").mkdir(parents=True)
    shutil.copy(src_wav, ep / "4_cut" / "coarse_cut.wav")
    fd = {"deletes": deletes, "user_notes": "", "feedback_for_learning": []}
    (ep / "4_cut" / "fine_deletes.json").write_text(json.dumps(fd))
    return ep


def _duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def test_no_fine_deletes_passes_through(tone_wav, tmp_path):
    ep = _setup_ep(tmp_path, tone_wav, [])
    subprocess.run(
        ["python", SCRIPT, "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO,
    )
    out = ep / "4_cut" / "final_cut.wav"
    assert out.exists()
    assert _duration(out) > 9.0  # full 10s preserved


def test_fine_delete_removes_correct_span(tone_wav, tmp_path):
    """Delete 2-4s of a 10s wav → output is ~8s long."""
    ep = _setup_ep(tmp_path, tone_wav, [
        {"cut_start_ms": 2000, "cut_end_ms": 4000,
         "category": "stutter", "reason": "test", "user_action": "kept"}
    ])
    subprocess.run(
        ["python", SCRIPT, "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO,
    )
    out = ep / "4_cut" / "final_cut.wav"
    assert out.exists()
    d = _duration(out)
    assert 7.7 < d < 8.3, f"expected ~8s, got {d:.2f}s"


def test_rejected_user_action_skipped(tone_wav, tmp_path):
    """Deletes with user_action=rejected_by_user should be ignored."""
    ep = _setup_ep(tmp_path, tone_wav, [
        {"cut_start_ms": 0, "cut_end_ms": 5000,
         "category": "test", "reason": "test", "user_action": "rejected_by_user"}
    ])
    subprocess.run(
        ["python", SCRIPT, "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO,
    )
    out = ep / "4_cut" / "final_cut.wav"
    d = _duration(out)
    assert d > 9.0, f"rejected delete must not apply; got {d:.2f}s"


def test_multiple_segments_no_dropped_audio(tone_wav, tmp_path):
    """Many deletes including a sub-50ms keep — concat fade must not drop content."""
    ep = _setup_ep(tmp_path, tone_wav, [
        {"cut_start_ms": 1000, "cut_end_ms": 2000, "category": "t", "reason": "t", "user_action": "kept"},
        {"cut_start_ms": 2030, "cut_end_ms": 3000, "category": "t", "reason": "t", "user_action": "kept"},
        {"cut_start_ms": 4000, "cut_end_ms": 5000, "category": "t", "reason": "t", "user_action": "kept"},
        {"cut_start_ms": 7000, "cut_end_ms": 7500, "category": "t", "reason": "t", "user_action": "kept"},
    ])
    subprocess.run(
        ["python", SCRIPT, "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO,
    )
    out = ep / "4_cut" / "final_cut.wav"
    d = _duration(out)
    # Expected kept: 0-1000 + 2000-2030 + 3000-4000 + 5000-7000 + 7500-10000
    # = 1.0 + 0.03 + 1.0 + 2.0 + 2.5 = 6.53s
    assert 6.4 < d < 6.7, f"expected ~6.53s, got {d:.2f}s"
