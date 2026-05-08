# tests/scripts/test_cut_audio.py
import json, shutil, subprocess
from pathlib import Path
import pytest

REPO = "/Users/houyuxin/08Coding/podcast-cutter-skills"


@pytest.fixture
def tiny_wav(tmp_path):
    """10-second 440Hz tone at audible level."""
    out = tmp_path / "track.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=10",
         "-af", "volume=4", "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(out)],
        check=True, capture_output=True,
    )
    return out


def _setup_ep(tmp_path, wav, deletes):
    ep = tmp_path / "ep01"
    (ep / "input").mkdir(parents=True)
    (ep / "3_review").mkdir(parents=True)
    shutil.copy(wav, ep / "input" / "working_track1.wav")
    meta = {
        "episode_id": "ep01", "mode": "single_track",
        "tracks": [{"file": "working_track1.wav", "duration_ms": 10000, "sample_rate": 44100}],
        "total_duration_ms": 10000,
    }
    (ep / "input" / "audio_meta.json").write_text(json.dumps(meta))
    edited = {"deletes": deletes, "user_notes": "", "feedback_for_learning": []}
    (ep / "3_review" / "delete_segments_edited.json").write_text(json.dumps(edited))
    return ep


def _get_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def test_cut_no_deletes_full_audio(tiny_wav, tmp_path):
    ep = _setup_ep(tmp_path, tiny_wav, [])
    subprocess.run(
        ["python", "shared/scripts/cut_audio.py", "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO,
    )
    cut = ep / "4_cut" / "cut.wav"
    assert cut.exists()
    dur = _get_duration(cut)
    assert dur > 8.0   # full 10s audio preserved


def test_cut_delete_first_2s(tiny_wav, tmp_path):
    ep = _setup_ep(tmp_path, tiny_wav, [
        {"start_ms": 0, "end_ms": 2000, "level": "rough",
         "reason": "test", "source": "ai_rough",
         "user_action": "kept"}
    ])
    subprocess.run(
        ["python", "shared/scripts/cut_audio.py", "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO,
    )
    cut = ep / "4_cut" / "cut.wav"
    assert cut.exists()
    dur = _get_duration(cut)
    assert dur < 9.0   # 2s deleted; will be slightly less due to xfade


def test_cut_rejected_delete_not_applied(tiny_wav, tmp_path):
    """Deletes with user_action=rejected_by_user should be ignored."""
    ep = _setup_ep(tmp_path, tiny_wav, [
        {"start_ms": 0, "end_ms": 5000, "level": "rough",
         "reason": "test", "source": "ai_rough",
         "user_action": "rejected_by_user"}
    ])
    subprocess.run(
        ["python", "shared/scripts/cut_audio.py", "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO,
    )
    cut = ep / "4_cut" / "cut.wav"
    assert cut.exists()
    dur = _get_duration(cut)
    assert dur > 8.0   # rejected delete → full audio preserved
