#!/usr/bin/env python3
"""Stage 1.4: words.json → sentences.json."""
from __future__ import annotations
import argparse, json
from pathlib import Path

PAUSE_THRESHOLD_MS = 500
MAX_SENT_CHARS = 50


def _flush(buf: list[dict], sent_id: int) -> dict:
    return {
        "id": sent_id,
        "speaker": buf[0]["speaker"],
        "start_ms": buf[0]["start_ms"],
        "end_ms": buf[-1]["end_ms"],
        "word_idx_start": buf[0]["idx"],
        "word_idx_end": buf[-1]["idx"],
        "text": "".join(w["text"] for w in buf),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep-dir", required=True)
    args = ap.parse_args()

    ep_dir = Path(args.ep_dir)
    td = ep_dir / "1_transcribe"
    words_data = json.loads((td / "words.json").read_text())
    words = words_data["words"]

    sentences = []
    buf: list[dict] = []
    for w in words:
        if buf:
            cur_len = sum(len(x["text"]) for x in buf)
            split = (
                w["speaker"] != buf[-1]["speaker"]
                or buf[-1]["blank_after_ms"] >= PAUSE_THRESHOLD_MS
                or cur_len >= MAX_SENT_CHARS
            )
            if split:
                sentences.append(_flush(buf, len(sentences)))
                buf = []
        buf.append(w)
    if buf:
        sentences.append(_flush(buf, len(sentences)))

    out = {"sentences": sentences}
    (td / "sentences.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"sentences.json: {len(sentences)} sentences")


if __name__ == "__main__":
    main()
