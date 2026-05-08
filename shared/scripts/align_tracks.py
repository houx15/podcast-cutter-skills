#!/usr/bin/env python3
"""Stage 1.05: compute timing offset between tracks, write track_offsets_ms to audio_meta.json.

Three modes (auto-detected):
  --t1 / --t2     wall-clock timestamps → timestamp mode
  --clap          detect first sharp transient in each WAV → clap mode
  (default)       match word sequences from volcano_raw_track*.json → transcript mode

Output: audio_meta.json gains {"track_offsets_ms": [0, N, ...]}
  offset[i] = ms by which track i+1 lags behind the earliest track.
  Applying offset: add offset[i] to each word's start_ms / end_ms from that track.
"""
from __future__ import annotations

import argparse
import difflib
import json
import struct
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_hms(s: str) -> int:
    """Parse HH:MM:SS or HH:MM:SS.mmm into milliseconds."""
    parts = s.split(".")
    ms_frac = int(parts[1].ljust(3, "0")[:3]) if len(parts) == 2 else 0
    h, m, sec = parts[0].split(":")
    return int(h) * 3_600_000 + int(m) * 60_000 + int(sec) * 1_000 + ms_frac


def _sorted_median(values: list[float]) -> float:
    """Return median of a list (assumes list is non-empty)."""
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


# ---------------------------------------------------------------------------
# Mode implementations
# ---------------------------------------------------------------------------

def _timestamp_offsets(t1_str: str, t2_str: str) -> list[int]:
    t1_ms = _parse_hms(t1_str)
    t2_ms = _parse_hms(t2_str)
    mn = min(t1_ms, t2_ms)
    return [t1_ms - mn, t2_ms - mn]


def _clap_offsets(in_dir: Path, n_tracks: int) -> list[int]:
    SAMPLE_RATE = 16000
    CLIP_SECS = 30
    peaks: list[int] = []

    for i in range(1, n_tracks + 1):
        wav = in_dir / f"working_track{i}.wav"
        if not wav.exists():
            raise FileNotFoundError(f"WAV not found for clap mode: {wav}")

        proc = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(wav),
                "-t", str(CLIP_SECS),
                "-af", f"aresample={SAMPLE_RATE}",
                "-f", "s16le",
                "-ac", "1",
                "pipe:1",
            ],
            check=True,
            capture_output=True,
        )
        raw = proc.stdout
        n_samples = len(raw) // 2
        if n_samples == 0:
            raise RuntimeError(f"No audio samples decoded from {wav} — is the file valid?")
        samples = struct.unpack(f"{n_samples}h", raw[: n_samples * 2])
        peak_idx = max(range(n_samples), key=lambda k: abs(samples[k]))
        peak_ms = int(peak_idx * 1000 / SAMPLE_RATE)
        peaks.append(peak_ms)

    mn = min(peaks)
    return [p - mn for p in peaks]


def _words_from_raw(raw: dict) -> list[dict]:
    words = []
    for utt in raw.get("resp", {}).get("utterances", []):
        for w in utt.get("words", []):
            words.append(
                {
                    "text": w["text"],
                    "start_ms": w["start_time"],
                    "end_ms": w["end_time"],
                }
            )
    return words


def _transcript_offsets(td: Path, n_tracks: int) -> list[int]:
    track_files = sorted(td.glob("volcano_raw_track*.json"))
    if not track_files:
        raise FileNotFoundError(
            f"No volcano_raw_track*.json in {td}. "
            "Run volcano_submit.py + volcano_query.py first, or use --clap / --t1 / --t2."
        )

    tracks_words = []
    for tf in track_files:
        raw = json.loads(tf.read_text())
        tracks_words.append(_words_from_raw(raw))

    # Track 0 is the reference; compute offset for each other track vs track 0
    offsets: list[float] = [0.0]

    ref_words = tracks_words[0]
    ref_texts = [w["text"] for w in ref_words]

    for other_words in tracks_words[1:]:
        other_texts = [w["text"] for w in other_words]

        matcher = difflib.SequenceMatcher(None, ref_texts, other_texts, autojunk=False)
        deltas: list[float] = []
        for block in matcher.get_matching_blocks():
            if block.size < 3:
                continue
            ref_start_ms = ref_words[block.a]["start_ms"]
            other_start_ms = other_words[block.b]["start_ms"]
            deltas.append(other_start_ms - ref_start_ms)

        if not deltas:
            print(
                "[align] WARNING: no matching blocks found for transcript alignment; defaulting offset to 0.",
                file=sys.stderr,
            )
            offsets.append(0.0)
        else:
            offsets.append(_sorted_median(deltas))

    # Normalise so earliest track gets 0
    mn = min(offsets)
    return [round(o - mn) for o in offsets]


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Stage 1.05: align multi-track recordings.")
    ap.add_argument("--ep-dir", required=True, help="Episode directory")
    ap.add_argument("--clap", action="store_true", help="Use clap-detection mode")
    ap.add_argument("--t1", default=None, help="Wall-clock start time for track 1 (HH:MM:SS[.mmm])")
    ap.add_argument("--t2", default=None, help="Wall-clock start time for track 2 (HH:MM:SS[.mmm])")
    args = ap.parse_args()

    # Validate --t1/--t2 pair
    if (args.t1 is None) != (args.t2 is None):
        ap.error("--t1 and --t2 must be provided together.")

    ep_dir = Path(args.ep_dir)
    in_dir = ep_dir / "input"
    meta_path = in_dir / "audio_meta.json"

    if not meta_path.exists():
        raise FileNotFoundError(
            f"audio_meta.json not found in {in_dir}. Run prepare_audio.py first."
        )

    meta = json.loads(meta_path.read_text())
    n_tracks = len(meta.get("tracks", []))

    # Single-track short-circuit
    if n_tracks < 2:
        print("[align] single-track episode; nothing to align.")
        meta["track_offsets_ms"] = [0]
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
        return

    # Determine mode and compute offsets
    if args.t1 is not None:
        mode = "timestamp"
        offsets = _timestamp_offsets(args.t1, args.t2)
    elif args.clap:
        mode = "clap"
        offsets = _clap_offsets(in_dir, n_tracks)
    else:
        mode = "transcript"
        td = ep_dir / "1_transcribe"
        offsets = _transcript_offsets(td, n_tracks)

    print(f"[align] {mode} mode: offsets = {offsets} ms")
    meta["track_offsets_ms"] = offsets
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
