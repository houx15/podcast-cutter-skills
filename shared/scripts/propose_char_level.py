#!/usr/bin/env python3
"""Deterministic character-level cut proposals from words.json.

Replaces the broken propose_cuts.py / propose_cuts_fine.py which mapped char
positions in sentence text to time via ratio (idx / len(text) × duration).
That mapping is fundamentally wrong for Chinese speech because char rate is
not uniform — markers landed seconds away from their actual spoken time.

Every proposal here has start_ms / end_ms derived ONLY from word timestamps
in the input words.json. Marker phrases are matched by walking the global
joined-words string and looking up the exact word indices for the matched
position — never via sentence-text char ratio.

Categories:
  stutter     — 3+ immediate same single-char repetitions by same speaker;
                proposal deletes all but the last instance.
  filler-run  — 4+ consecutive filler-only words (嗯啊呃哦哈呀) by same speaker.
  marker      — exact substring match of self-correction phrase in joined-words
                (Sorry我 / 我在说啥 / 稍等我 / 对不起 / etc.). All chars must be
                spoken by the same speaker (no cross-speaker false matches).
  habit       — run-on use of 就是/这个/那个 by same speaker — 3+ instances
                within a 5s window with span ≤ 2.5s; deletes all but last.

Usage:
  python propose_char_level.py --input-words words.json --output char_level.json
                               [--label coarse|fine]

Output schema:
  {"proposals": [
      {"id": "coarse-0001", "start_ms": ..., "end_ms": ...,
       "category": "stutter|filler-run|marker|habit",
       "speaker": "S1|S2", "reason": "...",
       "confidence": 0.0..1.0, "status": "pending"}
  ]}
"""
from __future__ import annotations
import argparse, json, re
from pathlib import Path

FILLER_CHARS = set("嗯呃啊哦哈呀")
FILLER_TOKENS = FILLER_CHARS | {"嗯嗯", "哈哈", "啊啊"}
STUTTER_BLACKLIST = set("嗯啊呃哦哈对了的")  # already covered by filler-run; don't double-flag
HABIT_TARGETS = {"就是", "这个", "那个"}

MARKER_PHRASES = [
    "Sorry我", "sorry我", "对不起", "我重新说", "我换个说法",
    "稍等我", "等一下", "我刚才说", "我刚说错",
    "我在说啥", "我说错",
]


def stutter_props(words: list[dict]) -> list[dict]:
    """3+ immediate repetitions of same single-char word from same speaker.
    Delete first n-1 instances, keep the last for natural cadence."""
    out = []
    PAD_HEAD = 30
    PAD_TAIL = 50
    i = 0
    while i < len(words) - 2:
        w = words[i]
        if len(w["text"]) != 1 or w["text"] in STUTTER_BLACKLIST:
            i += 1
            continue
        spk = w["speaker"]
        ch = w["text"]
        j = i
        while (j < len(words)
               and words[j]["speaker"] == spk
               and words[j]["text"] == ch):
            j += 1
        run = j - i
        if run >= 3:
            ws = words[i]
            we = words[j - 2]  # last index to delete
            out.append({
                "start_ms": max(0, ws["start_ms"] - PAD_HEAD),
                "end_ms": we["end_ms"] + PAD_TAIL,
                "category": "stutter",
                "speaker": spk,
                "reason": f"口吃 [{spk}]: {ch * run} → 保留最后一个",
                "confidence": 0.85,
            })
            i = j
        else:
            i += 1
    return out


def filler_run_props(words: list[dict]) -> list[dict]:
    """4+ consecutive filler-only words from same speaker."""
    out = []
    PAD_HEAD = 50
    PAD_TAIL = 80
    i = 0
    while i < len(words):
        w = words[i]
        if w["text"] not in FILLER_TOKENS:
            i += 1
            continue
        spk = w["speaker"]
        j = i
        while (j < len(words)
               and words[j]["speaker"] == spk
               and words[j]["text"] in FILLER_TOKENS):
            j += 1
        if j - i >= 4:
            ws = words[i]
            we = words[j - 1]
            chars = "".join(words[k]["text"] for k in range(i, j))
            out.append({
                "start_ms": max(0, ws["start_ms"] - PAD_HEAD),
                "end_ms": we["end_ms"] + PAD_TAIL,
                "category": "filler-run",
                "speaker": spk,
                "reason": f"语气词堆叠 [{spk}]: {chars}",
                "confidence": 0.7,
            })
            i = j
        else:
            i += 1
    return out


def marker_props(words: list[dict]) -> list[dict]:
    """Self-correction phrases — find via global joined-words substring search.

    Builds a positions array mapping each char index in the global joined string
    to its source word, then searches for each marker phrase as an exact substring.
    Proposal start/end are taken from the actual word timestamps at the matched
    span. Phrases that span multiple speakers are dropped (cross-track artifact).
    """
    PAD_HEAD = 80
    PAD_TAIL = 150
    # char-index → word-index map
    positions = []  # positions[i] = char position where word i starts
    char_buf = []
    char_pos = 0
    for w in words:
        positions.append(char_pos)
        char_buf.append(w["text"])
        char_pos += len(w["text"])
    full_text = "".join(char_buf)

    def word_index_at_char(p: int) -> int:
        lo, hi = 0, len(positions) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if positions[mid] <= p:
                lo = mid
            else:
                hi = mid - 1
        return lo

    out = []
    for marker in MARKER_PHRASES:
        start = 0
        while True:
            pos = full_text.find(marker, start)
            if pos < 0:
                break
            ws_idx = word_index_at_char(pos)
            we_idx = word_index_at_char(pos + len(marker) - 1)
            ws = words[ws_idx]
            we = words[we_idx]
            spk = ws["speaker"]
            # All chars within the marker must be spoken by the same speaker
            if all(words[i]["speaker"] == spk for i in range(ws_idx, we_idx + 1)):
                ctx_start = max(0, pos - 6)
                ctx_end = min(len(full_text), pos + len(marker) + 6)
                ctx = full_text[ctx_start:ctx_end]
                out.append({
                    "start_ms": max(0, ws["start_ms"] - PAD_HEAD),
                    "end_ms": we["end_ms"] + PAD_TAIL,
                    "category": "marker",
                    "speaker": spk,
                    "reason": f"自纠/打断 [{spk}]: …{ctx}…",
                    "confidence": 0.75,
                })
            start = pos + len(marker)
    return out


def habit_props(words: list[dict]) -> list[dict]:
    """3+ instances of 就是/这个/那个 within a 5s window by same speaker, span ≤ 2.5s."""
    PAD_HEAD = 30
    PAD_TAIL = 80
    WINDOW_MS = 5000
    MAX_SPAN_MS = 2500
    out = []
    instances: dict[str, list[dict]] = {ch: [] for ch in HABIT_TARGETS}
    for w in words:
        if w["text"] in HABIT_TARGETS:
            instances[w["text"]].append(w)
    for ch, hits in instances.items():
        i = 0
        while i < len(hits):
            spk = hits[i]["speaker"]
            j = i
            while (j < len(hits)
                   and hits[j]["speaker"] == spk
                   and hits[j]["start_ms"] - hits[i]["start_ms"] <= WINDOW_MS):
                j += 1
            if j - i >= 3:
                ws = hits[i]
                we = hits[j - 2]  # last to delete (keep the last)
                if we["end_ms"] - ws["start_ms"] > MAX_SPAN_MS:
                    i = j
                    continue
                out.append({
                    "start_ms": max(0, ws["start_ms"] - PAD_HEAD),
                    "end_ms": we["end_ms"] + PAD_TAIL,
                    "category": "habit",
                    "speaker": spk,
                    "reason": f"口癖堆叠 [{spk}]: {ch} 出现 {j-i} 次（{(hits[j-1]['start_ms']-hits[i]['start_ms'])/1000:.1f}s 内）",
                    "confidence": 0.5,
                })
                i = j
            else:
                i += 1
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-words", required=True,
                    help="path to words.json (or coarse_cut_words.json for fine pass)")
    ap.add_argument("--output", required=True,
                    help="path to write the proposals JSON")
    ap.add_argument("--label", default="coarse", choices=["coarse", "fine"],
                    help="prefix for proposal IDs")
    args = ap.parse_args()

    raw_words = json.loads(Path(args.input_words).read_text())["words"]
    # Filter whitespace-only tokens (Volcano emits these at utterance boundaries
    # with start_ms = -1) — they trip stutter detection on bare spaces.
    words = [w for w in raw_words if w["text"].strip() and w["start_ms"] >= 0]
    proposals = (
        stutter_props(words)
        + filler_run_props(words)
        + marker_props(words)
        + habit_props(words)
    )
    proposals.sort(key=lambda p: p["start_ms"])
    for i, p in enumerate(proposals):
        p["id"] = f"{args.label}-{i:04d}"
        p["status"] = "pending"

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"proposals": proposals}, ensure_ascii=False, indent=2))
    print(f"propose_char_level: {len(proposals)} proposals → {out_path}")
    cats: dict[str, int] = {}
    for p in proposals:
        cats[p["category"]] = cats.get(p["category"], 0) + 1
    for c, n in sorted(cats.items()):
        print(f"  {c}: {n}")


if __name__ == "__main__":
    main()
