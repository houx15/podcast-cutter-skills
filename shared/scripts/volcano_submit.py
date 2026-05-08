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
    ap.add_argument("--audio-url", default=None)
    ap.add_argument("--audio-file", default=None)
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

    if args.audio_url and args.audio_file:
        ap.error("Provide --audio-url or --audio-file, not both.")
    if args.audio_url:
        audio_url = args.audio_url
    elif args.audio_file:
        from lib.upload import select_uploader
        audio_url = select_uploader(cfg).upload(Path(args.audio_file))
    else:
        ap.error("Either --audio-url or --audio-file is required.")

    task_id = str(uuid.uuid4())
    headers = build_submit_headers(cfg.volcano, task_id)
    payload = build_submit_payload(
        audio_url=audio_url,
        audio_format=args.audio_format,
        uid=args.uid,
        enable_speaker_info=(args.track_num == 0),
        hotwords=[],
    )
    resp = requests.post(SUBMIT_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    status_code = resp.headers.get("X-Api-Status-Code", "")
    if status_code != "20000000":
        logid = resp.headers.get("X-Tt-Logid", "")
        raise RuntimeError(
            f"Volcano submit failed: X-Api-Status-Code={status_code} "
            f"X-Tt-Logid={logid} body={resp.text}"
        )

    ep_dir = Path(args.ep_dir)
    out_dir = ep_dir / "1_transcribe"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"task_id_track{args.track_num}.txt").write_text(task_id)
    print(task_id)


if __name__ == "__main__":
    main()
