#!/usr/bin/env python3
"""Stage 4.0: delete_segments_edited.json → cut.wav (25ms acrossfade per splice)."""
from __future__ import annotations
import argparse, json, subprocess, sys, tempfile
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).parent.parent.parent


def _merge_deletes(deletes: list[dict]) -> list[tuple[int, int]]:
    intervals = sorted((d["start_ms"], d["end_ms"]) for d in deletes)
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep-dir", required=True)
    ap.add_argument("--track-num", type=int, default=1)
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).parent))
    sys.path.insert(0, str(_repo_root()))
    from lib.ffmpeg_wrap import run_ffmpeg, volumedetect_max_db, FFmpegError
    from lib.audio_constants import SPLICE_XFADE_MS, MIN_OUTPUT_PEAK_DB

    ep_dir = Path(args.ep_dir)
    in_dir = ep_dir / "input"
    meta = json.loads((in_dir / "audio_meta.json").read_text())
    duration_ms = meta["total_duration_ms"]

    track_file = in_dir / f"working_track{args.track_num}.wav"
    edited = json.loads((ep_dir / "3_review" / "delete_segments_edited.json").read_text())
    active_deletes = [d for d in edited["deletes"] if d.get("user_action") != "rejected_by_user"]
    merged = _merge_deletes(active_deletes)
    keeps = _keep_ranges(duration_ms, merged)

    if not keeps:
        raise ValueError("No audio kept after applying deletes — all audio deleted")

    out_dir = ep_dir / "4_cut"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "cut.wav"
    log_dir = out_dir / "logs"
    log_dir.mkdir(exist_ok=True)

    xfade_s = SPLICE_XFADE_MS / 1000.0

    if len(keeps) == 1:
        s_ms, e_ms = keeps[0]
        run_ffmpeg(
            ["-i", str(track_file),
             "-ss", str(s_ms / 1000.0), "-to", str(e_ms / 1000.0),
             "-c:a", "pcm_s16le", str(out_file)],
            log_path=log_dir / "cut.log",
        )
    else:
        with tempfile.TemporaryDirectory() as td:
            segments = []
            for i, (s_ms, e_ms) in enumerate(keeps):
                seg = Path(td) / f"seg{i:04d}.wav"
                subprocess.run(
                    ["ffmpeg", "-y", "-hide_banner", "-i", str(track_file),
                     "-ss", str(s_ms / 1000.0), "-to", str(e_ms / 1000.0),
                     "-c:a", "pcm_s16le", str(seg)],
                    check=True, capture_output=True,
                )
                segments.append(seg)

            prev_label = "[0:a]"
            fc_parts = []
            for i in range(1, len(segments)):
                out_label = f"[a{i}]"
                fc_parts.append(
                    f"{prev_label}[{i}:a]acrossfade=d={xfade_s}:c1=tri:c2=tri{out_label}"
                )
                prev_label = out_label

            filter_complex = ";".join(fc_parts)
            cmd = []  # run_ffmpeg adds -y itself
            for seg in segments:
                cmd.extend(["-i", str(seg)])
            cmd.extend([
                "-filter_complex", filter_complex,
                "-map", prev_label,
                "-c:a", "pcm_s16le", str(out_file),
            ])
            run_ffmpeg(cmd, log_path=log_dir / "cut.log")

    peak = volumedetect_max_db(out_file)
    print(f"cut.wav: {len(keeps)} segment(s), peak={peak:.1f} dB → {out_file}")


if __name__ == "__main__":
    main()
