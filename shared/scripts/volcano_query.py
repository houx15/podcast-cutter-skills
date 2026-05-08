#!/usr/bin/env python3
"""Stage 1.2b: poll Volcano AUC until done, write volcano_raw_track*.json."""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path

import requests


def _repo_root() -> Path:
    return Path(__file__).parent.parent.parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep-dir", required=True)
    ap.add_argument("--track-num", type=int, default=1)
    ap.add_argument("--env", default=None)
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--max-attempts", type=int, default=360)
    args = ap.parse_args()

    env_path = Path(args.env) if args.env else _repo_root() / ".env"
    sys.path.insert(0, str(Path(__file__).parent))
    from lib.config import load
    from lib.volcano_client import (
        build_query_headers, QUERY_URL, QueryStatus, classify_status
    )

    cfg = load(env_path)
    ep_dir = Path(args.ep_dir)
    task_id = (ep_dir / "1_transcribe" / f"task_id_track{args.track_num}.txt").read_text().strip()

    for attempt in range(args.max_attempts):
        headers = build_query_headers(cfg.volcano, task_id)
        payload = {"user": {"uid": "podcast_cutter"}, "request": {"id": task_id}}
        resp = requests.post(QUERY_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        code = str(data["resp"]["code"])
        status = classify_status(code)
        if status is QueryStatus.SUCCESS:
            out = ep_dir / "1_transcribe" / f"volcano_raw_track{args.track_num}.json"
            out.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            print(f"Done -> {out}")
            return
        if status is QueryStatus.HARD_FAIL:
            raise RuntimeError(f"Volcano task failed code={code}: {data}")
        if args.interval > 0:
            time.sleep(args.interval)

    raise TimeoutError(f"Volcano task {task_id} did not complete in {args.max_attempts} attempts")


main()
