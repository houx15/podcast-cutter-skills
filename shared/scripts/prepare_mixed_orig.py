#!/usr/bin/env python3
"""Stage 1.6 (between transcribe and analyze): prepare input/mixed_orig.wav.

Produces a single mono WAV that mixes all working_track*.wav with the same
track_offsets_ms used by cut_audio. Used by the Stage 3 review UI so the
user can audition proposed cuts against the actual original audio.

This is conceptually `cut_audio` with no deletes — it pre-mixes once so the
review UI can stream a single file instead of mixing on-the-fly.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).parent.parent.parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep-dir", required=True)
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).parent))
    from cut_audio import _build_dual_track_mix
    from lib.ffmpeg_wrap import run_ffmpeg

    ep_dir = Path(args.ep_dir)
    in_dir = ep_dir / "input"
    meta = json.loads((in_dir / "audio_meta.json").read_text())
    out = in_dir / "mixed_orig.wav"
    log_dir = in_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    log = log_dir / "mix_orig.log"

    if meta.get("mode") == "two_track":
        _build_dual_track_mix(in_dir, meta, out, log, run_ffmpeg)
    else:
        # Single track — just copy / re-encode to mono pcm_s16le for the UI
        track_file = in_dir / meta["tracks"][0]["file"]
        run_ffmpeg(
            ["-i", str(track_file), "-ac", "1", "-c:a", "pcm_s16le", str(out)],
            log_path=log,
        )
    print(f"mixed_orig.wav → {out}")


if __name__ == "__main__":
    main()
