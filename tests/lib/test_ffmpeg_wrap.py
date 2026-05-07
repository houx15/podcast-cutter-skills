"""Tests for shared.scripts.lib.ffmpeg_wrap."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from shared.scripts.lib import audio_constants, ffmpeg_wrap

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg not installed"
)


def _silence_input(tmp_path: Path) -> Path:
    """Use the committed silence fixture rather than re-synthesizing."""
    fixture = (
        Path(__file__).resolve().parent.parent.parent
        / "shared/test_fixtures/silence_only/silence_5s.wav"
    )
    if not fixture.exists():
        pytest.skip("silence fixture not committed yet (Task 1 not run)")
    target = tmp_path / "silence.wav"
    shutil.copy(fixture, target)
    return target


def _tone_input(tmp_path: Path) -> Path:
    """A 1 kHz sine boosted to ~-6 dBFS; safely above the -10 dB silence trap."""
    out = tmp_path / "tone.wav"
    ffmpeg_wrap.run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:duration=2",
            "-af",
            "volume=4",
            "-c:a",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(out),
        ],
        log_path=tmp_path / "tone.log",
        skip_volumedetect=True,
    )
    return out


def test_volumedetect_parses_max_volume(tmp_path: Path) -> None:
    audio = _tone_input(tmp_path)
    peak = ffmpeg_wrap.volumedetect_max_db(audio)
    assert peak > audio_constants.MIN_OUTPUT_PEAK_DB


def test_run_ffmpeg_raises_when_output_is_silence(tmp_path: Path) -> None:
    """The whole point: a successful ffmpeg run that produces silence is a failure."""
    silence_in = _silence_input(tmp_path)
    silence_out = tmp_path / "out.wav"
    with pytest.raises(ffmpeg_wrap.FFmpegError) as exc:
        ffmpeg_wrap.run_ffmpeg(
            ["-i", str(silence_in), "-c:a", "copy", str(silence_out)],
            log_path=tmp_path / "ffmpeg.log",
        )
    assert "silence" in str(exc.value).lower() or "-91" in str(exc.value)


def test_run_ffmpeg_succeeds_for_audible_output(tmp_path: Path) -> None:
    out = tmp_path / "tone.wav"
    ffmpeg_wrap.run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:duration=1",
            "-af",
            "volume=4",
            "-c:a",
            "pcm_s16le",
            str(out),
        ],
        log_path=tmp_path / "tone.log",
    )
    assert out.exists()


def test_run_ffmpeg_writes_log_and_surfaces_last_lines_on_failure(
    tmp_path: Path,
) -> None:
    log = tmp_path / "ffmpeg.log"
    with pytest.raises(ffmpeg_wrap.FFmpegError) as exc:
        ffmpeg_wrap.run_ffmpeg(
            ["-i", "/no/such/file.wav", str(tmp_path / "out.wav")],
            log_path=log,
        )
    assert log.exists()
    text = exc.value.tail
    assert text  # last 20 lines surfaced
    assert "/no/such/file" in log.read_text()
