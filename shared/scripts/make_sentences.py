#!/usr/bin/env python3
"""Stage 1.4: words.json → sentences.json.

For dual-track recordings, each speaker's track is transcribed independently
and the streams are merged by timestamp. Splitting sentences on every speaker
change would shred dual-track audio into single-character fragments (S1 says
'好', S2 says '好' simultaneously, etc.). Instead, segment each speaker's
stream independently and merge the resulting sentences by start_ms.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path

PAUSE_THRESHOLD_MS = 500
MAX_SENT_CHARS = 50


def _flush(buf: list[dict]) -> dict:
    """Emit a sentence record. `word_indices` is the explicit list of GLOBAL
    word indices that compose this sentence's text — needed for dual-track
    where one speaker's words interleave with another's by timestamp.
    `word_idx_start/end` describe only the global TIME range and may include
    other-speaker words; never use them to reconstruct text."""
    return {
        "id": -1,  # reassigned after final sort
        "speaker": buf[0]["speaker"],
        "start_ms": buf[0]["start_ms"],
        "end_ms": buf[-1]["end_ms"],
        "word_idx_start": buf[0]["idx"],
        "word_idx_end": buf[-1]["idx"],
        "word_indices": [w["idx"] for w in buf],
        "text": "".join(w["text"] for w in buf),
    }


def _segment_one_speaker(speaker_words: list[dict]) -> list[dict]:
    """Segment one speaker's word stream by pause / max-length."""
    sentences = []
    buf: list[dict] = []
    for w in speaker_words:
        if not w["text"].strip():
            # Volcano emits whitespace-only tokens at utterance boundaries —
            # treat them as a forced split rather than letting them inflate length.
            if buf:
                sentences.append(_flush(buf))
                buf = []
            continue
        if buf:
            cur_len = sum(len(x["text"]) for x in buf)
            split = (
                buf[-1]["blank_after_ms"] >= PAUSE_THRESHOLD_MS
                or cur_len >= MAX_SENT_CHARS
            )
            if split:
                sentences.append(_flush(buf))
                buf = []
        buf.append(w)
    if buf:
        sentences.append(_flush(buf))
    return sentences


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep-dir", required=True)
    args = ap.parse_args()

    ep_dir = Path(args.ep_dir)
    td = ep_dir / "1_transcribe"
    words_data = json.loads((td / "words.json").read_text())
    words = words_data["words"]

    by_speaker: dict[str, list[dict]] = {}
    for w in words:
        by_speaker.setdefault(w["speaker"], []).append(w)

    sentences: list[dict] = []
    for spk_words in by_speaker.values():
        sentences.extend(_segment_one_speaker(spk_words))

    sentences.sort(key=lambda s: s["start_ms"])
    for i, s in enumerate(sentences):
        s["id"] = i

    out = {"sentences": sentences}
    (td / "sentences.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"sentences.json: {len(sentences)} sentences")


if __name__ == "__main__":
    main()
