#!/usr/bin/env python3
"""Stage 1.2a: submit audio URL to Volcano AUC v3 big-model ASR."""
from __future__ import annotations
import argparse, sys, uuid
from pathlib import Path

import requests


def _repo_root() -> Path:
    return Path(__file__).parent.parent.parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio-url", required=True)
    ap.add_argument("--audio-format", default="wav")
    ap.add_argument("--ep-dir", required=True)
    ap.add_argument("--track-num", type=int, default=1)
    ap.add_argument("--env", default=None)
    ap.add_argument("--uid", default="podcast_cutter")
    args = ap.parse_args()

    env_path = Path(args.env) if args.env else _repo_root() / ".env"
    sys.path.insert(0, str(Path(__file__).parent))
    from lib.config import load
    from lib.volcano_client import build_submit_headers, build_submit_payload, SUBMIT_URL

    cfg = load(env_path)
    task_id = str(uuid.uuid4())
    headers = build_submit_headers(cfg.volcano, task_id)
    payload = build_submit_payload(
        audio_url=args.audio_url,
        audio_format=args.audio_format,
        uid=args.uid,
        enable_speaker_info=(args.track_num == 0),
        hotwords=[],
    )
    resp = requests.post(SUBMIT_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    returned_task_id = resp.json()["resp"]["task_id"]

    ep_dir = Path(args.ep_dir)
    out_dir = ep_dir / "1_transcribe"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"task_id_track{args.track_num}.txt").write_text(returned_task_id)
    print(returned_task_id)


main()
