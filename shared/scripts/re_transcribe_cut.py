#!/usr/bin/env python3
"""Stage 4.2: re-ASR cut.wav for fine-cut (精修) review.

The Stage-1 transcript is from the raw recording. After the coarse cut, sentences
that span cut boundaries carry stale text (the deleted-region words remain in the
sentence text). For accurate fine-cut review, we re-run Volcano ASR on cut.wav
itself. Output is on the cut.wav timeline (no offset), so editorial proposals
land where the audio actually plays.

Outputs:
  4_cut/cut_volcano_raw.json — raw Volcano response
  4_cut/cut_words.json        — flat words on cut.wav timeline
  4_cut/cut_sentences.json    — segmented sentences on cut.wav timeline
"""
from __future__ import annotations
import argparse, importlib.util, json, sys, time, uuid
from pathlib import Path

import requests


def _repo_root() -> Path:
    return Path(__file__).parent.parent.parent


def _import_make_sentences():
    path = Path(__file__).parent / "make_sentences.py"
    spec = importlib.util.spec_from_file_location("make_sentences", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _parse_words(raw: dict) -> list[dict]:
    """Volcano AUC v3 response → flat word list (preserves diarized speaker)."""
    result = raw.get("result") or {}
    words: list[dict] = []
    for utt in result.get("utterances", []):
        spk_id = utt.get("speaker") or utt.get("speaker_id") or 1
        speaker = f"S{spk_id}" if not str(spk_id).startswith("S") else str(spk_id)
        for w in utt.get("words", []):
            words.append({
                "idx": 0,  # reassigned after sort
                "speaker": speaker,
                "start_ms": w["start_time"],
                "end_ms": w["end_time"],
                "text": w["text"],
                "confidence": w.get("confidence", 1.0),
                "blank_after_ms": w.get("blank_duration", 0),
                "emotion": w.get("emotion"),
                "lid": w.get("lang") or w.get("lid"),
            })
    words.sort(key=lambda w: w["start_ms"])
    for i, w in enumerate(words):
        w["idx"] = i
    return words


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep-dir", required=True)
    ap.add_argument("--env", default=None)
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--max-attempts", type=int, default=360)
    ap.add_argument("--skip-asr", action="store_true",
                    help="skip Volcano calls; just re-parse existing cut_volcano_raw.json")
    args = ap.parse_args()

    env_path = Path(args.env) if args.env else _repo_root() / ".env"
    sys.path.insert(0, str(Path(__file__).parent))
    from lib.config import load
    from lib.volcano_client import (
        build_submit_headers, build_submit_payload, SUBMIT_URL,
        build_query_headers, QUERY_URL, QueryStatus, classify_status,
    )
    from lib.upload import select_uploader

    ep = Path(args.ep_dir)
    # Prefer coarse_cut.wav (new flow); fall back to legacy cut.wav.
    cut_wav = ep / "4_cut" / "coarse_cut.wav"
    if not cut_wav.exists():
        cut_wav = ep / "4_cut" / "cut.wav"
    if not cut_wav.exists():
        raise FileNotFoundError(
            f"No coarse_cut.wav or cut.wav in {ep / '4_cut'}/. Run cut_audio.py first."
        )

    out_dir = ep / "4_cut"
    raw_path = out_dir / "cut_volcano_raw.json"

    if not args.skip_asr:
        cfg = load(env_path)

        # 1. Upload cut.wav (reuses S3/TOS uploader chain)
        size_mb = cut_wav.stat().st_size / 1e6
        print(f"[re_asr] Uploading cut.wav ({size_mb:.0f} MB)...")
        audio_url = select_uploader(cfg).upload(cut_wav)
        print(f"[re_asr]   → {audio_url}")

        # 2. Submit with speaker diarization (cut.wav is mono mix of 2 speakers)
        task_id = str(uuid.uuid4())
        headers = build_submit_headers(cfg.volcano, task_id)
        payload = build_submit_payload(
            audio_url=audio_url,
            audio_format="wav",
            uid="podcast_cutter_re_asr",
            enable_speaker_info=True,
            hotwords=[],
        )
        r = requests.post(SUBMIT_URL, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        code = r.headers.get("X-Api-Status-Code", "")
        if code != "20000000":
            logid = r.headers.get("X-Tt-Logid", "")
            raise RuntimeError(
                f"Volcano submit failed: status={code} logid={logid} body={r.text}"
            )
        (out_dir / "cut_task_id.txt").write_text(task_id)
        print(f"[re_asr] task_id={task_id}, polling...")

        # 3. Poll until done
        for attempt in range(args.max_attempts):
            qh = build_query_headers(cfg.volcano, task_id)
            qr = requests.post(QUERY_URL, headers=qh, json={}, timeout=30)
            qr.raise_for_status()
            qc = qr.headers.get("X-Api-Status-Code", "")
            qstatus = classify_status(qc)
            if qstatus is QueryStatus.SUCCESS:
                raw_path.write_text(json.dumps(qr.json(), ensure_ascii=False, indent=2))
                print(f"[re_asr] done → {raw_path}")
                break
            if qstatus is QueryStatus.HARD_FAIL:
                logid = qr.headers.get("X-Tt-Logid", "")
                raise RuntimeError(
                    f"Volcano task failed: status={qc} logid={logid} body={qr.text}"
                )
            if attempt % 6 == 5:
                print(f"[re_asr]   ... attempt {attempt+1}, still pending (status={qc})")
            if args.interval > 0:
                time.sleep(args.interval)
        else:
            raise TimeoutError(f"Volcano did not complete in {args.max_attempts} attempts")

    # 4. Parse raw → cut_words.json
    raw = json.loads(raw_path.read_text())
    words = _parse_words(raw)
    speakers = sorted({w["speaker"] for w in words})
    duration_ms = max((w["end_ms"] for w in words), default=0)
    cut_words = {
        "episode_id": ep.name,
        "duration_ms": duration_ms,
        "source": {"file": "cut.wav", "mode": "re_asr_post_cut"},
        "speakers": [{"id": s} for s in speakers],
        "words": words,
    }
    (out_dir / "cut_words.json").write_text(
        json.dumps(cut_words, ensure_ascii=False, indent=2)
    )
    print(f"[re_asr] cut_words.json: {len(words)} words, speakers={speakers}")

    # 5. Segment → cut_sentences.json (reuse make_sentences logic)
    ms_mod = _import_make_sentences()
    by_spk: dict[str, list[dict]] = {}
    for w in words:
        by_spk.setdefault(w["speaker"], []).append(w)
    sentences: list[dict] = []
    for spk_words in by_spk.values():
        sentences.extend(ms_mod._segment_one_speaker(spk_words))
    sentences.sort(key=lambda s: s["start_ms"])
    for i, s in enumerate(sentences):
        s["id"] = i
    (out_dir / "cut_sentences.json").write_text(
        json.dumps({"sentences": sentences}, ensure_ascii=False, indent=2)
    )
    print(f"[re_asr] cut_sentences.json: {len(sentences)} sentences")


if __name__ == "__main__":
    main()
