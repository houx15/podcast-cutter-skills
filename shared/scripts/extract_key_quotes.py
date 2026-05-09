#!/usr/bin/env python3
"""Stage 6: extract per-speaker key-sentence audio clips from cut.wav.

The agent writes `6_clips/picks.json` listing 5-10 quotable spans per speaker.
This script slices each from cut.wav and saves them to per-speaker folders so
the user can audition and pick a few for cold opens / promo snippets / preview
clips at the start of the published episode.

Input format (`6_clips/picks.json`):
{
  "picks": [
    {"speaker": "S1", "cut_start_ms": 12345, "cut_end_ms": 23456,
     "label": "AI是船是河流", "text": "在AI这条湍急的河流里..."},
    ...
  ]
}

Output:
  6_clips/S1/01-AI是船是河流.wav   (with 100ms head/tail breathing room)
  6_clips/S1/02-...wav
  6_clips/S2/01-...wav
  6_clips/manifest.json
"""
from __future__ import annotations
import argparse, json, re, subprocess
from pathlib import Path

PAD_MS = 100  # leave 100ms breath at each end of the clip


def _slug(label: str, max_len: int = 40) -> str:
    """Turn a Chinese/English label into a filesystem-safe filename fragment."""
    s = re.sub(r'[\s/\\:*?"<>|]+', "-", label.strip())
    return s[:max_len] or "clip"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep-dir", required=True)
    ap.add_argument("--picks", default=None,
                    help="path to picks.json (default: <ep>/6_clips/picks.json)")
    args = ap.parse_args()

    ep = Path(args.ep_dir)
    # Prefer final_cut.wav (post fine-pass); fall back to cut.wav (legacy single-pass).
    cut_wav = ep / "4_cut" / "final_cut.wav"
    if not cut_wav.exists():
        cut_wav = ep / "4_cut" / "cut.wav"
    if not cut_wav.exists():
        raise FileNotFoundError(
            f"No final_cut.wav or cut.wav in {ep / '4_cut'}/. Run cut_audio_fine.py or cut_audio.py first."
        )

    out_root = ep / "6_clips"
    out_root.mkdir(parents=True, exist_ok=True)
    picks_path = Path(args.picks) if args.picks else (out_root / "picks.json")
    if not picks_path.exists():
        raise FileNotFoundError(
            f"{picks_path} not found. Agent should write picks.json with "
            f"the chosen quotes before running this script."
        )

    picks = json.loads(picks_path.read_text())["picks"]

    # Probe cut.wav duration so we can clamp pads
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(cut_wav)],
        capture_output=True, text=True, check=True,
    )
    total_dur_ms = int(float(r.stdout.strip()) * 1000)

    # Group by speaker, preserve agent's pick order
    by_speaker: dict[str, list[dict]] = {}
    for p in picks:
        by_speaker.setdefault(p["speaker"], []).append(p)

    manifest_entries = []
    log_dir = out_root / "logs"
    log_dir.mkdir(exist_ok=True)

    for speaker, items in by_speaker.items():
        spk_dir = out_root / speaker
        # Wipe and recreate so re-runs are clean
        if spk_dir.exists():
            for f in spk_dir.glob("*.wav"):
                f.unlink()
        spk_dir.mkdir(parents=True, exist_ok=True)

        for i, p in enumerate(items, start=1):
            cs = max(0, p["cut_start_ms"] - PAD_MS)
            ce = min(total_dur_ms, p["cut_end_ms"] + PAD_MS)
            if ce <= cs:
                print(f"[skip] {speaker} #{i:02d}: invalid span {cs}-{ce}")
                continue

            label = _slug(p.get("label", f"clip{i:02d}"))
            out_wav = spk_dir / f"{i:02d}-{label}.wav"
            log_path = log_dir / f"{speaker}-{i:02d}.log"

            # Extract — input-side seek so the fade filter's t=0 lines up with
            # the start of the extracted span (output-side -ss leaves the fade
            # operating on the source timeline → silent output).
            fade_dur = 0.025
            af = (
                f"afade=t=in:st=0:d={fade_dur},"
                f"afade=t=out:st={(ce-cs)/1000.0 - fade_dur:.3f}:d={fade_dur}"
            )
            cmd = [
                "ffmpeg", "-y", "-hide_banner",
                "-ss", f"{cs/1000.0:.3f}",
                "-to", f"{ce/1000.0:.3f}",
                "-i", str(cut_wav),
                "-af", af,
                "-c:a", "pcm_s16le",
                str(out_wav),
            ]
            with log_path.open("w") as logf:
                logf.write("$ " + " ".join(cmd) + "\n")
                proc = subprocess.run(cmd, capture_output=True, text=True)
                logf.write(proc.stderr)
            if proc.returncode != 0:
                print(f"[err]  {speaker} #{i:02d}: ffmpeg rc={proc.returncode}, see {log_path}")
                continue

            dur_s = (ce - cs) / 1000.0
            print(f"[ok]   {speaker} #{i:02d}: {dur_s:5.1f}s → {out_wav.name}")
            manifest_entries.append({
                "speaker": speaker,
                "index": i,
                "label": p.get("label", ""),
                "text": p.get("text", ""),
                "cut_start_ms": p["cut_start_ms"],
                "cut_end_ms": p["cut_end_ms"],
                "padded_start_ms": cs,
                "padded_end_ms": ce,
                "duration_ms": ce - cs,
                "file": str(out_wav.relative_to(ep)),
            })

    (out_root / "manifest.json").write_text(
        json.dumps({"clips": manifest_entries}, ensure_ascii=False, indent=2)
    )
    print(f"\nmanifest.json: {len(manifest_entries)} clips → {out_root / 'manifest.json'}")


if __name__ == "__main__":
    main()
