#!/usr/bin/env python3
"""Stage 1.3: Volcano raw JSON(s) → words.json."""
from __future__ import annotations
import argparse, json
from pathlib import Path


def _parse_words_from_raw(raw: dict, speaker: str) -> list[dict]:
    words = []
    idx = 0
    for utt in raw.get("resp", {}).get("utterances", []):
        for w in utt.get("words", []):
            words.append({
                "idx": idx,
                "speaker": speaker,
                "start_ms": w["start_time"],
                "end_ms": w["end_time"],
                "text": w["text"],
                "confidence": w.get("confidence", 1.0),
                "blank_after_ms": w.get("blank_duration", 0),
                "emotion": w.get("emotion"),
                "lid": w.get("lang") or w.get("lid"),
            })
            idx += 1
    return words


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep-dir", required=True)
    ap.add_argument("--ep-id", default=None)
    args = ap.parse_args()

    ep_dir = Path(args.ep_dir)
    td = ep_dir / "1_transcribe"
    ep_id = args.ep_id or ep_dir.name

    track_files = sorted(td.glob("volcano_raw_track*.json"))
    if not track_files:
        raise FileNotFoundError(f"No volcano_raw_track*.json in {td}")

    all_words = []
    speakers = []
    track_names = []
    for i, tf in enumerate(track_files, start=1):
        raw = json.loads(tf.read_text())
        speaker = f"S{i}"
        speakers.append({"id": speaker, "name": None, "track": f"working_track{i}.wav"})
        track_names.append(f"working_track{i}.wav")
        words = _parse_words_from_raw(raw, speaker)
        all_words.extend(words)

    mode = "two_track" if len(track_files) >= 2 else "single_track"
    all_words.sort(key=lambda w: w["start_ms"])
    for i, w in enumerate(all_words):
        w["idx"] = i

    # probe total duration from audio_meta.json if present
    meta_file = ep_dir / "input" / "audio_meta.json"
    duration_ms = all_words[-1]["end_ms"] if all_words else 0
    if meta_file.exists():
        meta = json.loads(meta_file.read_text())
        duration_ms = meta.get("total_duration_ms", duration_ms)

    out = {
        "episode_id": ep_id,
        "duration_ms": duration_ms,
        "source": {"tracks": track_names, "mode": mode},
        "speakers": speakers,
        "words": all_words,
    }
    (td / "words.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"words.json: {len(all_words)} words, mode={mode}")


if __name__ == "__main__":
    main()
