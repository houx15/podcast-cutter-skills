#!/usr/bin/env python3
"""Stage 5.0: re-time sentences against cut.wav for show-notes generation.

Reads sentences.json + delete_segments_edited.json. Drops sentences that fall
entirely inside a delete region (clipping partial overlaps). Adjusts the
remaining sentences' start_ms / end_ms so they map onto the cut.wav timeline
(the deleted spans are subtracted out). Writes 5_shownotes/cut_transcript.json.

The result is what the agent reads when generating show notes — the timeline
the listener actually hears, with timestamps that line up with cut.wav.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path


def _merge_deletes(deletes: list[dict]) -> list[tuple[int, int]]:
    """Sort + merge overlapping delete spans → list of (start_ms, end_ms)."""
    spans = sorted((int(d["start_ms"]), int(d["end_ms"])) for d in deletes)
    merged: list[tuple[int, int]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def _shift_for(t_ms: int, deletes: list[tuple[int, int]]) -> int:
    """How much to subtract from t_ms to map original → cut timeline.

    Sums the deleted duration that falls strictly before t_ms. If t_ms lies
    inside a delete span, the caller should treat it as out-of-cut.
    """
    shift = 0
    for s, e in deletes:
        if e <= t_ms:
            shift += e - s
        elif s < t_ms < e:
            shift += t_ms - s  # partial — caller decides whether to keep
            break
        else:
            break
    return shift


def _is_inside_delete(t_ms: int, deletes: list[tuple[int, int]]) -> bool:
    for s, e in deletes:
        if s <= t_ms < e:
            return True
        if s > t_ms:
            return False
    return False


def _retime_sentences(sentences: list[dict], deletes: list[tuple[int, int]]) -> list[dict]:
    """Drop sentences whose midpoint falls inside a delete; re-time the rest."""
    out: list[dict] = []
    for s in sentences:
        start = int(s["start_ms"])
        end = int(s["end_ms"])
        midpoint = (start + end) // 2
        if _is_inside_delete(midpoint, deletes):
            continue
        new_start = start - _shift_for(start, deletes)
        new_end = end - _shift_for(end, deletes)
        out.append({
            **s,
            "start_ms": new_start,
            "end_ms": new_end,
            "orig_start_ms": start,
            "orig_end_ms": end,
        })
    # Reassign sequential ids on the cut timeline.
    for i, s in enumerate(out):
        s["id"] = i
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep-dir", required=True)
    args = ap.parse_args()

    ep_dir = Path(args.ep_dir)
    sents_path = ep_dir / "1_transcribe" / "sentences.json"
    deletes_path = ep_dir / "3_review" / "delete_segments_edited.json"
    if not sents_path.exists():
        raise FileNotFoundError(f"sentences.json not found: {sents_path}")
    if not deletes_path.exists():
        raise FileNotFoundError(f"delete_segments_edited.json not found: {deletes_path}")

    sentences = json.loads(sents_path.read_text())["sentences"]
    deletes_raw = json.loads(deletes_path.read_text()).get("deletes", [])
    # Treat user_action == "rejected" as kept (don't delete those).
    deletes_active = [d for d in deletes_raw if d.get("user_action") != "rejected"]
    deletes = _merge_deletes(deletes_active)

    retimed = _retime_sentences(sentences, deletes)
    total_deleted_ms = sum(e - s for s, e in deletes)

    out = {
        "deletes_applied_ms": [list(x) for x in deletes],
        "total_deleted_ms": total_deleted_ms,
        "sentence_count_orig": len(sentences),
        "sentence_count_cut": len(retimed),
        "sentences": retimed,
    }
    out_dir = ep_dir / "5_shownotes"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "cut_transcript.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(
        f"cut_transcript.json: {len(retimed)} sentences "
        f"(dropped {len(sentences) - len(retimed)}), "
        f"total deleted = {total_deleted_ms / 1000:.1f}s"
    )


if __name__ == "__main__":
    main()
