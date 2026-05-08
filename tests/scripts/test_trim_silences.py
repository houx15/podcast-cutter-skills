# tests/scripts/test_trim_silences.py
import json, shutil, subprocess
from pathlib import Path
import pytest

REPO = "/Users/houyuxin/08Coding/podcast-cutter-skills"


@pytest.fixture
def silence_then_tone(tmp_path):
    """2s silence + 5s tone + 2s silence."""
    out = tmp_path / "cut.wav"
    subprocess.run(
        ["ffmpeg", "-y",
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
         "-filter_complex",
         "[0:a]atrim=duration=2[s0];[2:a]atrim=duration=2[s2];"
         "[s0][1:a][s2]concat=n=3:v=0:a=1,volume=4[out]",
         "-map", "[out]", "-c:a", "pcm_s16le", str(out)],
        check=True, capture_output=True,
    )
    return out


@pytest.fixture
def pure_tone(tmp_path):
    """5s tone, no silence at edges."""
    out = tmp_path / "cut.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
         "-af", "volume=4", "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(out)],
        check=True, capture_output=True,
    )
    return out


def _setup_ep(tmp_path, wav):
    ep = tmp_path / "ep01"
    cut_dir = ep / "4_cut"
    cut_dir.mkdir(parents=True)
    shutil.copy(wav, cut_dir / "cut.wav")
    return ep


def _get_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def test_trim_removes_head_tail_silence(silence_then_tone, tmp_path):
    ep = _setup_ep(tmp_path, silence_then_tone)
    subprocess.run(
        ["python", "shared/scripts/trim_silences.py", "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO,
    )
    dur = _get_duration(ep / "4_cut" / "cut.wav")
    assert dur < 7.5   # was ~9s, silence trimmed (leaving ~200ms at each end)
    assert dur > 5.0   # tone preserved


def test_no_trim_when_no_silence(pure_tone, tmp_path):
    ep = _setup_ep(tmp_path, pure_tone)
    original_dur = _get_duration(ep / "4_cut" / "cut.wav")
    subprocess.run(
        ["python", "shared/scripts/trim_silences.py", "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO,
    )
    dur = _get_duration(ep / "4_cut" / "cut.wav")
    assert abs(dur - original_dur) < 0.1   # unchanged
