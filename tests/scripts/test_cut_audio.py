# tests/scripts/test_cut_audio.py
import json, re, shutil, subprocess
from pathlib import Path
import pytest

REPO = "/Users/houyuxin/08Coding/podcast-cutter-skills"


@pytest.fixture
def tiny_wav(tmp_path):
    """10-second 440Hz tone at audible level."""
    out = tmp_path / "track.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=10",
         "-af", "volume=8", "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(out)],
        check=True, capture_output=True,
    )
    return out


def _half_silent_wav(out: Path, freq: int, tone_first_half: bool) -> None:
    """10s wav: tone at `freq` either in first or second 5s half."""
    if tone_first_half:
        af = "volume=8,apad=pad_dur=5"
    else:
        af = "volume=8,adelay=5000|5000"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration=5",
         "-af", af, "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(out)],
        check=True, capture_output=True,
    )


def _segment_max_db(wav: Path, start_s: float, end_s: float) -> float:
    """Max volume in [start_s, end_s) of `wav`. Uses atrim filter (input -ss/-to
    don't restrict volumedetect's measurement window correctly)."""
    r = subprocess.run(
        ["ffmpeg", "-i", str(wav),
         "-af", f"atrim={start_s}:{end_s},asetpts=PTS-STARTPTS,volumedetect",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    m = re.search(r"max_volume:\s+(-?[\d.]+)\s*dB", r.stderr)
    return float(m.group(1)) if m else -100.0


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


def _setup_ep_dual(tmp_path, t1_wav, t2_wav, deletes, offsets=(0, 0)):
    ep = tmp_path / "ep_dual"
    (ep / "input").mkdir(parents=True)
    (ep / "3_review").mkdir(parents=True)
    shutil.copy(t1_wav, ep / "input" / "working_track1.wav")
    shutil.copy(t2_wav, ep / "input" / "working_track2.wav")
    meta = {
        "episode_id": "ep_dual", "mode": "two_track",
        "tracks": [
            {"file": "working_track1.wav", "duration_ms": 10000, "sample_rate": 44100},
            {"file": "working_track2.wav", "duration_ms": 10000, "sample_rate": 44100},
        ],
        "total_duration_ms": 10000,
        "track_offsets_ms": list(offsets),
    }
    (ep / "input" / "audio_meta.json").write_text(json.dumps(meta))
    edited = {"deletes": deletes, "user_notes": "", "feedback_for_learning": []}
    (ep / "3_review" / "delete_segments_edited.json").write_text(json.dumps(edited))
    return ep


def test_cut_dual_track_includes_both_speakers(tmp_path):
    """two_track mode: cut.wav must contain audio from BOTH tracks.

    track1 = 440Hz tone in 0–5s + silence 5–10s.
    track2 = silence 0–5s + 880Hz tone 5–10s.
    Mixed cut.wav must have signal in both halves; if cut_audio drops track2
    (the bug we are fixing), the second half would be silence.
    """
    t1 = tmp_path / "t1.wav"
    t2 = tmp_path / "t2.wav"
    _half_silent_wav(t1, 440, tone_first_half=True)
    _half_silent_wav(t2, 880, tone_first_half=False)
    ep = _setup_ep_dual(tmp_path, t1, t2, [])
    subprocess.run(
        ["python", "shared/scripts/cut_audio.py", "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO,
    )
    cut = ep / "4_cut" / "cut.wav"
    assert cut.exists()
    first_half_db = _segment_max_db(cut, 0.5, 4.5)
    second_half_db = _segment_max_db(cut, 5.5, 9.5)
    assert first_half_db > -25.0, f"track1 missing from cut: first half max={first_half_db}dB"
    assert second_half_db > -25.0, f"track2 missing from cut: second half max={second_half_db}dB"


def test_cut_preserves_duration_with_many_segments_and_short_keeps(tiny_wav, tmp_path):
    """Regression: with many keeps including a sub-50ms one, cut.wav must
    keep all kept content — chained acrossfade was silently dropping ~half
    the audio when any segment was shorter than 2× the xfade duration."""
    # 10s tone, deletes that produce 5 keeps, one of them very short (30ms)
    deletes = [
        {"start_ms": 1000, "end_ms": 2000, "level": "rough", "reason": "t",
         "source": "test", "user_action": "kept"},
        # Tiny keep: 2000-2030ms (only 30ms)
        {"start_ms": 2030, "end_ms": 3000, "level": "rough", "reason": "t",
         "source": "test", "user_action": "kept"},
        {"start_ms": 4000, "end_ms": 5000, "level": "rough", "reason": "t",
         "source": "test", "user_action": "kept"},
        {"start_ms": 7000, "end_ms": 7500, "level": "rough", "reason": "t",
         "source": "test", "user_action": "kept"},
    ]
    ep = _setup_ep(tmp_path, tiny_wav, deletes)
    subprocess.run(
        ["python", "shared/scripts/cut_audio.py", "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO,
    )
    cut = ep / "4_cut" / "cut.wav"
    dur = _get_duration(cut)
    # Expected kept: 0-1000 + 2000-2030 + 3000-4000 + 5000-7000 + 7500-10000
    # = 1.0 + 0.03 + 1.0 + 2.0 + 2.5 = 6.53s
    assert 6.4 <= dur <= 6.7, f"expected ~6.53s, got {dur:.2f}s (likely chain bug)"


def test_cut_dual_track_applies_offset(tmp_path):
    """track_offsets_ms shifts track2 forward in the mix.

    track1 = tone in 0–5s, silence 5–10s.
    track2 = tone in 0–5s, silence 5–10s; offset = [0, 3000].
    Mixed timeline: track1 contributes 0–5s, track2 contributes 3–8s.
    With both summed, audio extends through 8s; the 8.5–9.5s window must be near silent.
    """
    t1 = tmp_path / "t1.wav"
    t2 = tmp_path / "t2.wav"
    _half_silent_wav(t1, 440, tone_first_half=True)
    _half_silent_wav(t2, 880, tone_first_half=True)
    ep = _setup_ep_dual(tmp_path, t1, t2, [], offsets=(0, 3000))
    subprocess.run(
        ["python", "shared/scripts/cut_audio.py", "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO,
    )
    cut = ep / "4_cut" / "cut.wav"
    assert cut.exists()
    around_4_db = _segment_max_db(cut, 4.0, 4.5)   # both tracks present here
    around_7_db = _segment_max_db(cut, 6.5, 7.5)   # only track2 (shifted) here
    quiet_db = _segment_max_db(cut, 8.5, 9.5)      # both tracks silent here
    assert around_4_db > -25.0
    assert around_7_db > -25.0
    assert quiet_db < -40.0, f"expected silence after both tones end, got {quiet_db}dB"
