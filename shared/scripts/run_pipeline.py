#!/usr/bin/env python3
"""Single entry point for the podcast cutting pipeline.

First run (stages 1-3, pauses at human review):
    python shared/scripts/run_pipeline.py \\
        --ep-dir output/2026-05-08-ep01 \\
        --track1 recordings/host.wav \\
        [--track2 recordings/guest.wav] \\
        [--align clap|timestamp|transcript] \\
        [--t1 10:00:00 --t2 10:00:03]

After review (export delete_segments_edited.json in browser, then):
    python shared/scripts/run_pipeline.py --ep-dir output/2026-05-08-ep01 --resume

Stages are skipped if their output already exists — safe to re-run.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYTHON = sys.executable


def _repo_root() -> Path:
    return Path(__file__).parent.parent.parent


def _scripts() -> Path:
    return Path(__file__).parent


def _run(cmd: list[str], label: str) -> None:
    print(f"\n[pipeline] {label}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"Stage failed (exit {result.returncode}): {label}")


def _done(path: Path) -> bool:
    return path.exists()


def main() -> None:
    ap = argparse.ArgumentParser(description="Podcast cutting pipeline.")
    ap.add_argument("--ep-dir", required=True, help="Episode output directory.")
    ap.add_argument("--track1", default=None, help="Path to track 1 recording.")
    ap.add_argument("--track2", default=None, help="Path to track 2 recording (optional).")
    ap.add_argument("--ep-id", default=None, help="Episode ID (defaults to ep-dir name).")
    ap.add_argument("--align", choices=["clap", "timestamp", "transcript"],
                    default=None, help="Track alignment mode (two-track only).")
    ap.add_argument("--t1", default=None, help="Track 1 wall-clock start time HH:MM:SS.")
    ap.add_argument("--t2", default=None, help="Track 2 wall-clock start time HH:MM:SS.")
    ap.add_argument("--resume", action="store_true", help="Skip to stage 4 after human review.")
    args = ap.parse_args()

    ep = Path(args.ep_dir)
    sc = _scripts()

    # ── Resume path ──────────────────────────────────────────────────────────
    if args.resume:
        delete_file = ep / "3_review" / "delete_segments_edited.json"
        self_review = ep / "2_analysis" / "self_review.json"

        if delete_file.exists():
            # Post-human-review: stage 4
            if not _done(ep / "4_cut" / "cut.wav"):
                _run([PYTHON, str(sc / "cut_audio.py"), "--ep-dir", str(ep)], "4.0 cut audio")
            _run([PYTHON, str(sc / "trim_silences.py"), "--ep-dir", str(ep)], "4.1 trim silences")
            print(f"\n[pipeline] Done. Output: {ep / '4_cut' / 'cut.wav'}")
            return

        if self_review.exists():
            # Post-agent-analysis: stage 3.0
            html = ep / "3_review" / "review_enhanced.html"
            if not _done(html):
                _run([PYTHON, str(sc / "generate_review_html.py"), "--ep-dir", str(ep)],
                     "3.0 generate review HTML")
            print(f"""
[pipeline] ────────────────────────────────────────────────────────────
  Analysis complete. Human review required.

  Review file : {ep / '3_review' / 'review_enhanced.html'}
  Start server: python shared/scripts/review_server.py --ep-dir {ep} --port 5050

  Steps:
    1. Start the review server (command above)
    2. Open the review file in your browser
    3. Review suggested cuts — accept, reject, or adjust
    4. Click Export (saves delete_segments_edited.json automatically)
    5. Run this to finish:
         python shared/scripts/run_pipeline.py --ep-dir {ep} --resume
[pipeline] ────────────────────────────────────────────────────────────
""")
            return

        # Neither: analysis not complete
        ctx = ep / "2_analysis" / "analysis_context.md"
        print(f"[pipeline] ERROR: Agent analysis not complete.")
        print(f"  Read {ctx} and write rough_cuts.json, fine_cuts.json, self_review.json")
        print(f"  Then run: python shared/scripts/run_pipeline.py --ep-dir {ep} --resume")
        sys.exit(1)
        return

    # ── Stage 1.0: prepare audio ─────────────────────────────────────────────
    if not _done(ep / "input" / "audio_meta.json"):
        if not args.track1:
            ap.error("--track1 is required for a new episode.")
        cmd = [PYTHON, str(sc / "prepare_audio.py"), "--ep-dir", str(ep),
               "--track1", args.track1]
        if args.track2:
            cmd += ["--track2", args.track2]
        if args.ep_id:
            cmd += ["--ep-id", args.ep_id]
        _run(cmd, "1.0 prepare audio")

    meta = json.loads((ep / "input" / "audio_meta.json").read_text())
    n_tracks = len(meta.get("tracks", []))
    two_track = n_tracks >= 2

    # ── Stage 1.05: align (clap / timestamp — before ASR) ───────────────────
    if two_track and "track_offsets_ms" not in meta and args.align in ("clap", "timestamp"):
        cmd = [PYTHON, str(sc / "align_tracks.py"), "--ep-dir", str(ep)]
        if args.align == "clap":
            cmd.append("--clap")
        else:
            if not args.t1 or not args.t2:
                ap.error("--t1 and --t2 are required for --align timestamp.")
            cmd += ["--t1", args.t1, "--t2", args.t2]
        _run(cmd, "1.05 align tracks (pre-ASR)")

    # ── Stage 1.2: ASR per track ─────────────────────────────────────────────
    for i in range(1, n_tracks + 1):
        if not _done(ep / "1_transcribe" / f"volcano_raw_track{i}.json"):
            wav = ep / "input" / f"working_track{i}.wav"
            _run([PYTHON, str(sc / "volcano_submit.py"),
                  "--audio-file", str(wav),
                  "--track-num", str(i),
                  "--ep-dir", str(ep)], f"1.2a ASR submit track{i}")
            _run([PYTHON, str(sc / "volcano_query.py"),
                  "--track-num", str(i),
                  "--ep-dir", str(ep)], f"1.2b ASR query track{i}")

    # ── Stage 1.05: align (transcript — after ASR) ───────────────────────────
    meta = json.loads((ep / "input" / "audio_meta.json").read_text())
    if two_track and "track_offsets_ms" not in meta and args.align not in ("clap", "timestamp"):
        _run([PYTHON, str(sc / "align_tracks.py"), "--ep-dir", str(ep)],
             "1.05 align tracks (transcript, post-ASR)")

    # ── Stage 1.3: merge transcription ───────────────────────────────────────
    if not _done(ep / "1_transcribe" / "words.json"):
        _run([PYTHON, str(sc / "transcribe_merge.py"), "--ep-dir", str(ep)], "1.3 transcribe merge")

    # ── Stage 1.4: sentences ─────────────────────────────────────────────────
    if not _done(ep / "1_transcribe" / "sentences.json"):
        _run([PYTHON, str(sc / "make_sentences.py"), "--ep-dir", str(ep)], "1.4 make sentences")

    # ── Stage 2.0: build analysis context ────────────────────────────────────
    if not _done(ep / "2_analysis" / "analysis_context.md"):
        _run([PYTHON, str(sc / "build_analysis_context.py"), "--ep-dir", str(ep)],
             "2.0 build analysis context")

    # ── Pause: agent analysis ─────────────────────────────────────────────────
    print(f"""
[pipeline] ────────────────────────────────────────────────────────────
  Transcription complete. Agent analysis required.

  Context file: {ep / '2_analysis' / 'analysis_context.md'}

  As the orchestrating agent, read the context file and write:
    - {ep / '2_analysis' / 'rough_cuts.json'}
    - {ep / '2_analysis' / 'fine_cuts.json'}
    - {ep / '2_analysis' / 'self_review.json'}

  Then resume:
    python shared/scripts/run_pipeline.py --ep-dir {ep} --resume
[pipeline] ────────────────────────────────────────────────────────────
""")


if __name__ == "__main__":
    main()
