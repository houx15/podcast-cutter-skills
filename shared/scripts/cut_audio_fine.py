#!/usr/bin/env python3
"""Stage 4.5: apply CUT-timeline fine deletes to coarse_cut.wav → final_cut.wav.

Single mixed input (no dual-track mixing — that already happened in Stage 4.0).
Reads `4_cut/fine_deletes.json` whose `cut_start_ms` / `cut_end_ms` are in the
COARSE_CUT.wav timeline. Applies the same per-segment fade + concat splice
logic as `cut_audio.py` (the chained-acrossfade-dropping-audio bug fix).

This script is the bottom half of the timeline-isolation fix: fine deletes
never get translated to the original timeline; they apply directly to the
coarse cut. Re-running iterations doesn't accumulate drift.
"""
from __future__ import annotations
import argparse, json, subprocess, sys, tempfile
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).parent.parent.parent


def _merge_intervals(deletes: list[dict]) -> list[tuple[int, int]]:
    intervals = sorted((d["cut_start_ms"], d["cut_end_ms"]) for d in deletes)
    merged: list[list[int]] = []
    for s, e in intervals:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def _keep_ranges(duration_ms: int, deletes: list[tuple[int, int]]) -> list[tuple[int, int]]:
    keeps = []
    cur = 0
    for s, e in deletes:
        if cur < s:
            keeps.append((cur, s))
        cur = max(cur, e)
    if cur < duration_ms:
        keeps.append((cur, duration_ms))
    return keeps


def _ffprobe_duration_ms(path: Path) -> int:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return int(float(r.stdout.strip()) * 1000)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep-dir", required=True)
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).parent))
    sys.path.insert(0, str(_repo_root()))
    from lib.ffmpeg_wrap import run_ffmpeg, volumedetect_max_db
    from lib.audio_constants import SPLICE_XFADE_MS

    ep = Path(args.ep_dir)
    in_wav = ep / "4_cut" / "coarse_cut.wav"
    if not in_wav.exists():
        # Fall back to cut.wav for compatibility with the legacy single-pass flow
        legacy = ep / "4_cut" / "cut.wav"
        if legacy.exists():
            in_wav = legacy
        else:
            raise FileNotFoundError(
                f"{in_wav} not found. Run cut_audio.py first to produce coarse_cut.wav."
            )

    fd_path = ep / "4_cut" / "fine_deletes.json"
    if not fd_path.exists():
        raise FileNotFoundError(f"{fd_path} not found.")

    fine = json.loads(fd_path.read_text())
    active = [d for d in fine.get("deletes", []) if d.get("user_action") != "rejected_by_user"]
    duration_ms = _ffprobe_duration_ms(in_wav)
    merged = _merge_intervals(active)
    keeps = _keep_ranges(duration_ms, merged)
    if not keeps:
        raise ValueError("No audio kept after fine deletes — all coarse_cut.wav deleted")

    out_file = ep / "4_cut" / "final_cut.wav"
    log_dir = ep / "4_cut" / "logs"
    log_dir.mkdir(exist_ok=True)
    xfade_s = SPLICE_XFADE_MS / 1000.0

    with tempfile.TemporaryDirectory() as td:
        if len(keeps) == 1:
            s_ms, e_ms = keeps[0]
            run_ffmpeg(
                ["-i", str(in_wav),
                 "-ss", str(s_ms / 1000.0), "-to", str(e_ms / 1000.0),
                 "-c:a", "pcm_s16le", str(out_file)],
                log_path=log_dir / "cut_fine.log",
            )
        else:
            segments = []
            for i, (s_ms, e_ms) in enumerate(keeps):
                seg = Path(td) / f"seg{i:04d}.wav"
                subprocess.run(
                    ["ffmpeg", "-y", "-hide_banner", "-i", str(in_wav),
                     "-ss", str(s_ms / 1000.0), "-to", str(e_ms / 1000.0),
                     "-c:a", "pcm_s16le", str(seg)],
                    check=True, capture_output=True,
                )
                segments.append((seg, (e_ms - s_ms) / 1000.0))

            fc_parts = []
            labels = []
            for i, (seg, dur) in enumerate(segments):
                fd = min(xfade_s, dur / 2)
                fade_filters = []
                if fd > 0.001 and i > 0:
                    fade_filters.append(f"afade=t=in:st=0:d={fd:.3f}")
                if fd > 0.001 and i < len(segments) - 1:
                    fade_filters.append(f"afade=t=out:st={dur - fd:.3f}:d={fd:.3f}")
                lbl = f"[s{i}]"
                if fade_filters:
                    fc_parts.append(f"[{i}:a]{','.join(fade_filters)}{lbl}")
                else:
                    fc_parts.append(f"[{i}:a]anull{lbl}")
                labels.append(lbl)
            fc_parts.append(
                f"{''.join(labels)}concat=n={len(segments)}:v=0:a=1[out]"
            )
            cmd = []
            for seg, _ in segments:
                cmd.extend(["-i", str(seg)])
            cmd.extend([
                "-filter_complex", ";".join(fc_parts),
                "-map", "[out]",
                "-c:a", "pcm_s16le", str(out_file),
            ])
            run_ffmpeg(cmd, log_path=log_dir / "cut_fine.log")

    peak = volumedetect_max_db(out_file)
    print(f"final_cut.wav: {len(keeps)} segment(s), peak={peak:.1f} dB → {out_file}")


if __name__ == "__main__":
    main()
