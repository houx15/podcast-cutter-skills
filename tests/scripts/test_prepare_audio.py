import subprocess, json
from pathlib import Path
import pytest

REPO = "/Users/houyuxin/08Coding/podcast-cutter-skills"

@pytest.fixture
def tiny_wav(tmp_path):
    """5-second 44100 Hz mono WAV via ffmpeg."""
    out = tmp_path / "input.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
         "-af", "volume=4", "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(out)],
        check=True, capture_output=True
    )
    return out

def test_single_track_creates_outputs(tiny_wav, tmp_path):
    ep_dir = tmp_path / "output" / "ep01"
    subprocess.run(
        ["python", "shared/scripts/prepare_audio.py",
         "--track1", str(tiny_wav), "--ep-dir", str(ep_dir)],
        check=True, capture_output=True, cwd=REPO
    )
    assert (ep_dir / "input" / "working_track1.wav").exists()
    meta = json.loads((ep_dir / "input" / "audio_meta.json").read_text())
    assert meta["mode"] == "single_track"
    assert meta["total_duration_ms"] > 0
    assert len(meta["tracks"]) == 1

def test_two_track_creates_both(tiny_wav, tmp_path):
    ep_dir = tmp_path / "output" / "ep01"
    subprocess.run(
        ["python", "shared/scripts/prepare_audio.py",
         "--track1", str(tiny_wav), "--track2", str(tiny_wav),
         "--ep-dir", str(ep_dir)],
        check=True, capture_output=True, cwd=REPO
    )
    assert (ep_dir / "input" / "working_track1.wav").exists()
    assert (ep_dir / "input" / "working_track2.wav").exists()
    meta = json.loads((ep_dir / "input" / "audio_meta.json").read_text())
    assert meta["mode"] == "two_track"
    assert len(meta["tracks"]) == 2

def test_idempotent_rerun(tiny_wav, tmp_path):
    ep_dir = tmp_path / "output" / "ep01"
    for _ in range(2):
        subprocess.run(
            ["python", "shared/scripts/prepare_audio.py",
             "--track1", str(tiny_wav), "--ep-dir", str(ep_dir)],
            check=True, capture_output=True, cwd=REPO
        )
    meta = json.loads((ep_dir / "input" / "audio_meta.json").read_text())
    assert meta["mode"] == "single_track"
