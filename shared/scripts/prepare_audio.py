#!/usr/bin/env python3
"""Stage 1.0: convert input audio to working WAVs (mono, 16-bit, original SR)."""
from __future__ import annotations
import argparse, json, subprocess
from pathlib import Path

def probe_duration_ms(path: Path) -> int:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True
    )
    return int(float(r.stdout.strip()) * 1000)

def probe_sample_rate(path: Path) -> int:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=sample_rate",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True
    )
    return int(r.stdout.strip())

def convert_to_working_wav(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    sr = probe_sample_rate(src)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src),
         "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le", str(dst)],
        check=True, capture_output=True
    )

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--track1", required=True)
    ap.add_argument("--track2", default=None)
    ap.add_argument("--ep-dir", required=True)
    ap.add_argument("--ep-id", default=None)
    args = ap.parse_args()

    ep_dir = Path(args.ep_dir)
    ep_id = args.ep_id or ep_dir.name
    in_dir = ep_dir / "input"
    in_dir.mkdir(parents=True, exist_ok=True)

    tracks = [Path(args.track1)]
    if args.track2:
        tracks.append(Path(args.track2))

    mode = "two_track" if len(tracks) == 2 else "single_track"
    track_metas = []
    for i, src in enumerate(tracks, start=1):
        dst = in_dir / f"working_track{i}.wav"
        convert_to_working_wav(src, dst)
        dur = probe_duration_ms(dst)
        sr = probe_sample_rate(dst)
        track_metas.append({"file": dst.name, "duration_ms": dur, "sample_rate": sr})

    total_ms = max(t["duration_ms"] for t in track_metas)
    meta = {
        "episode_id": ep_id,
        "mode": mode,
        "tracks": track_metas,
        "total_duration_ms": total_ms,
    }
    (in_dir / "audio_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(json.dumps(meta))

if __name__ == "__main__":
    main()
