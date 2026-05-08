#!/usr/bin/env python3
"""Stage 4.1: trim head/tail silence to 200ms. Overwrites cut.wav."""
from __future__ import annotations
import argparse, re, shutil, subprocess, sys, tempfile
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).parent.parent.parent


def _detect_silence_edges(wav: Path, threshold_db: float = -50.0, min_duration: float = 0.1) -> tuple[float, float]:
    """Return (trim_start_sec, trim_end_sec): the region to keep."""
    r = subprocess.run(
        ["ffmpeg", "-i", str(wav),
         "-af", f"silencedetect=n={threshold_db}dB:d={min_duration}",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    stderr = r.stderr

    silence_starts = [float(m) for m in re.findall(r"silence_start: ([\d.]+)", stderr)]
    silence_ends = [float(m) for m in re.findall(r"silence_end: ([\d.]+)", stderr)]

    r2 = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(wav)],
        capture_output=True, text=True, check=True,
    )
    total_dur = float(r2.stdout.strip())

    trim_start = 0.0
    # If silence at beginning: silence_starts[0] ~= 0 and we have a silence_end
    if silence_starts and silence_starts[0] < 0.5 and silence_ends:
        trim_start = max(0.0, silence_ends[0] - 0.2)  # leave 200ms

    trim_end = total_dur
    # If silence at end: last silence_start is near end of file
    if silence_starts and silence_starts[-1] > total_dur - 3.0:
        trim_end = min(total_dur, silence_starts[-1] + 0.2)  # leave 200ms

    return trim_start, trim_end


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep-dir", required=True)
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).parent))
    sys.path.insert(0, str(_repo_root()))
    from lib.ffmpeg_wrap import run_ffmpeg, volumedetect_max_db
    from lib.audio_constants import MIN_OUTPUT_PEAK_DB

    ep_dir = Path(args.ep_dir)
    cut_wav = ep_dir / "4_cut" / "cut.wav"
    if not cut_wav.exists():
        raise FileNotFoundError(f"cut.wav not found at {cut_wav}. Run cut_audio.py first.")

    start_s, end_s = _detect_silence_edges(cut_wav)

    # Only do work if we're actually trimming something meaningful
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(cut_wav)],
        capture_output=True, text=True, check=True,
    )
    total_dur = float(r.stdout.strip())

    if start_s < 0.01 and abs(end_s - total_dur) < 0.01:
        print(f"trim_silences: no significant silence at head/tail, skipping")
        return

    log_dir = ep_dir / "4_cut" / "logs"
    log_dir.mkdir(exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False, dir=ep_dir / "4_cut") as tf:
        tmp = Path(tf.name)

    try:
        run_ffmpeg(
            ["-i", str(cut_wav),
             "-ss", str(start_s), "-to", str(end_s),
             "-c:a", "pcm_s16le", str(tmp)],
            log_path=log_dir / "trim.log",
        )
        shutil.move(str(tmp), str(cut_wav))
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

    peak = volumedetect_max_db(cut_wav)
    if peak <= MIN_OUTPUT_PEAK_DB:
        raise RuntimeError(f"trim_silences: output peak {peak:.1f} dB too low (silence trap)")
    print(f"trim_silences: kept [{start_s:.2f}s, {end_s:.2f}s], peak={peak:.1f} dB")


if __name__ == "__main__":
    main()
