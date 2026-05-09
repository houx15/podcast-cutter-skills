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


def _build_dual_track_mix(in_dir: Path, meta: dict, out_path: Path, log_path: Path, run_ffmpeg) -> None:
    """Mix all working_track*.wav into a single mono wav, applying track_offsets_ms.

    Each track i is delayed by offsets[i] ms (adelay), then summed via amix with
    normalize=1 (each input scaled by 1/N) to keep peaks safe across overlap.
    """
    tracks = meta["tracks"]
    n = len(tracks)
    offsets = list(meta.get("track_offsets_ms") or [])
    while len(offsets) < n:
        offsets.append(0)

    cmd: list[str] = []
    for t in tracks:
        cmd.extend(["-i", str(in_dir / t["file"])])

    filter_parts = []
    mix_labels = []
    for i, off in enumerate(offsets[:n]):
        if off > 0:
            filter_parts.append(f"[{i}:a]adelay={off}|{off}[a{i}]")
            mix_labels.append(f"[a{i}]")
        else:
            mix_labels.append(f"[{i}:a]")
    filter_parts.append(
        f"{''.join(mix_labels)}amix=inputs={n}:duration=longest:dropout_transition=0[out]"
    )

    cmd.extend([
        "-filter_complex", ";".join(filter_parts),
        "-map", "[out]",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        str(out_path),
    ])
    run_ffmpeg(cmd, log_path=log_path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep-dir", required=True)
    ap.add_argument("--track-num", type=int, default=1,
                    help="single_track mode only: which working_track*.wav to cut")
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).parent))
    sys.path.insert(0, str(_repo_root()))
    from lib.ffmpeg_wrap import run_ffmpeg, volumedetect_max_db, FFmpegError
    from lib.audio_constants import SPLICE_XFADE_MS, MIN_OUTPUT_PEAK_DB

    ep_dir = Path(args.ep_dir)
    in_dir = ep_dir / "input"
    meta = json.loads((in_dir / "audio_meta.json").read_text())
    duration_ms = meta["total_duration_ms"]
    mode = meta.get("mode", "single_track")

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

    with tempfile.TemporaryDirectory() as td:
        if mode == "two_track":
            track_file = Path(td) / "mixed.wav"
            _build_dual_track_mix(in_dir, meta, track_file, log_dir / "mix.log", run_ffmpeg)
        else:
            track_file = in_dir / f"working_track{args.track_num}.wav"

        if len(keeps) == 1:
            s_ms, e_ms = keeps[0]
            run_ffmpeg(
                ["-i", str(track_file),
                 "-ss", str(s_ms / 1000.0), "-to", str(e_ms / 1000.0),
                 "-c:a", "pcm_s16le", str(out_file)],
                log_path=log_dir / "cut.log",
            )
        else:
            # Per-segment fade-in/out + concat filter. Replaces the previous
            # acrossfade chain, which silently dropped content when very short
            # segments (≤2× xfade duration) appeared in the chain — a 60-input
            # chain with one 0.03s segment lost ~6 minutes of audio.
            segments = []
            for i, (s_ms, e_ms) in enumerate(keeps):
                seg = Path(td) / f"seg{i:04d}.wav"
                subprocess.run(
                    ["ffmpeg", "-y", "-hide_banner", "-i", str(track_file),
                     "-ss", str(s_ms / 1000.0), "-to", str(e_ms / 1000.0),
                     "-c:a", "pcm_s16le", str(seg)],
                    check=True, capture_output=True,
                )
                segments.append((seg, (e_ms - s_ms) / 1000.0))

            fc_parts = []
            labels = []
            for i, (seg, dur) in enumerate(segments):
                # Cap the fade at half the segment so very short segments still
                # work. A 30ms segment gets a 15ms fade-in and 15ms fade-out.
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
            run_ffmpeg(cmd, log_path=log_dir / "cut.log")

    peak = volumedetect_max_db(out_file)
    print(f"cut.wav: mode={mode}, {len(keeps)} segment(s), peak={peak:.1f} dB → {out_file}")


if __name__ == "__main__":
    main()
