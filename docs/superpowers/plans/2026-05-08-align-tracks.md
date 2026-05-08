# Track Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `align_tracks.py` (stage 1.05) to compute the timing offset between two recording tracks and persist it in `audio_meta.json`, then update `transcribe_merge.py` to apply that offset when building `words.json`.

**Architecture:** Three auto-detected modes — clap (peak transient in WAV), timestamp (user-supplied wall-clock start times), and transcript (difflib sequence matching on Volcano raw words). All modes write `track_offsets_ms` to `audio_meta.json`; `transcribe_merge.py` shifts each track's word timestamps accordingly before sorting and merging. No WAV files are modified.

**Tech Stack:** Python 3.10+, ffmpeg subprocess (clap mode), difflib (transcript mode), existing `lib/config.py` + `lib/json_io.py` patterns.

---

## File Structure

- Create: `shared/scripts/align_tracks.py`
- Modify: `shared/scripts/transcribe_merge.py` — read `track_offsets_ms`, shift words before merge
- Modify: `shared/test_fixtures/tiny_2track/` — already has two WAVs; add a clap fixture
- Create: `shared/test_fixtures/tiny_2track_offset/` — two WAVs with known 500ms offset for integration test
- Create: `tests/scripts/test_align_tracks.py`
- Modify: `tests/scripts/test_transcribe_merge.py` — add offset test

---

## `audio_meta.json` schema addition

`prepare_audio.py` writes this file. After `align_tracks.py` runs, it adds `track_offsets_ms`:

```json
{
  "episode_id": "...",
  "total_duration_ms": 60000,
  "tracks": [...],
  "track_offsets_ms": [0, 3000]
}
```

`track_offsets_ms[i]` = milliseconds by which track `i+1`'s wall-clock start lags behind the earliest track. Track with the smallest start time gets offset 0; others are positive. Applying the offset means adding `track_offsets_ms[i]` to every word's `start_ms` / `end_ms` from that track.

---

## Task 1: align_tracks.py

**Files:**
- Create: `shared/scripts/align_tracks.py`
- Create: `tests/scripts/test_align_tracks.py`
- Create: `shared/test_fixtures/tiny_2track_offset/` (two synthetic WAVs: track1 is silence+tone, track2 is same but starts 500ms later)

### Step 1 — Write the failing tests

```python
# tests/scripts/test_align_tracks.py
import importlib.util, json, subprocess, sys
from pathlib import Path
import pytest

SCRIPTS = Path(__file__).parent.parent.parent / "shared" / "scripts"
FIXTURES = Path(__file__).parent.parent.parent / "shared" / "test_fixtures"

def _load_script():
    spec = importlib.util.spec_from_file_location("align_tracks", SCRIPTS / "align_tracks.py")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS))
    spec.loader.exec_module(mod)
    return mod

# ── Test 1: timestamp mode ───────────────────────────────────────────────────
def test_timestamp_offset(tmp_path):
    mod = _load_script()
    ep_dir = tmp_path / "ep"
    in_dir = ep_dir / "input"
    in_dir.mkdir(parents=True)
    # seed audio_meta with two tracks
    meta = {
        "episode_id": "test",
        "total_duration_ms": 60000,
        "tracks": [
            {"file": "working_track1.wav", "duration_ms": 60000, "sample_rate": 44100},
            {"file": "working_track2.wav", "duration_ms": 60000, "sample_rate": 44100},
        ],
    }
    (in_dir / "audio_meta.json").write_text(json.dumps(meta))
    # track1 started at 10:00:00, track2 at 10:00:03 → track2 is 3000ms behind
    sys.argv = ["align_tracks.py", "--ep-dir", str(ep_dir), "--t1", "10:00:00", "--t2", "10:00:03"]
    mod.main()
    result = json.loads((in_dir / "audio_meta.json").read_text())
    assert result["track_offsets_ms"] == [0, 3000]

# ── Test 2: transcript mode ───────────────────────────────────────────────────
def test_transcript_offset(tmp_path):
    mod = _load_script()
    ep_dir = tmp_path / "ep"
    td = ep_dir / "1_transcribe"
    in_dir = ep_dir / "input"
    td.mkdir(parents=True)
    in_dir.mkdir(parents=True)

    # track1 has words starting at 0ms; track2 has same words but +500ms
    def _raw(start_offset_ms):
        words = [
            {"text": "你好", "start_time": 1000 + start_offset_ms, "end_time": 1300 + start_offset_ms, "confidence": 0.9, "blank_duration": 50},
            {"text": "我们", "start_time": 1400 + start_offset_ms, "end_time": 1700 + start_offset_ms, "confidence": 0.9, "blank_duration": 50},
            {"text": "今天", "start_time": 1800 + start_offset_ms, "end_time": 2100 + start_offset_ms, "confidence": 0.9, "blank_duration": 50},
            {"text": "讨论", "start_time": 2200 + start_offset_ms, "end_time": 2500 + start_offset_ms, "confidence": 0.9, "blank_duration": 50},
        ]
        return {"resp": {"utterances": [{"words": words}]}}

    (td / "volcano_raw_track1.json").write_text(json.dumps(_raw(0)))
    (td / "volcano_raw_track2.json").write_text(json.dumps(_raw(500)))
    meta = {"episode_id": "test", "total_duration_ms": 60000, "tracks": [
        {"file": "working_track1.wav", "duration_ms": 60000, "sample_rate": 44100},
        {"file": "working_track2.wav", "duration_ms": 60000, "sample_rate": 44100},
    ]}
    (in_dir / "audio_meta.json").write_text(json.dumps(meta))

    sys.argv = ["align_tracks.py", "--ep-dir", str(ep_dir)]
    mod.main()
    result = json.loads((in_dir / "audio_meta.json").read_text())
    offsets = result["track_offsets_ms"]
    assert offsets[0] == 0
    assert abs(offsets[1] - 500) < 50  # within 50ms tolerance

# ── Test 3: single-track is a no-op ─────────────────────────────────────────
def test_single_track_noop(tmp_path):
    mod = _load_script()
    ep_dir = tmp_path / "ep"
    in_dir = ep_dir / "input"
    in_dir.mkdir(parents=True)
    meta = {"episode_id": "test", "total_duration_ms": 60000,
            "tracks": [{"file": "working_track1.wav", "duration_ms": 60000, "sample_rate": 44100}]}
    (in_dir / "audio_meta.json").write_text(json.dumps(meta))
    sys.argv = ["align_tracks.py", "--ep-dir", str(ep_dir)]
    mod.main()
    result = json.loads((in_dir / "audio_meta.json").read_text())
    assert result["track_offsets_ms"] == [0]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/scripts/test_align_tracks.py -v
```
Expected: `ModuleNotFoundError` or `FileNotFoundError` — script does not exist yet.

- [ ] **Step 3: Implement `align_tracks.py`**

```python
#!/usr/bin/env python3
"""Stage 1.05: compute timing offset between tracks, write track_offsets_ms to audio_meta.json.

Three modes (auto-detected):
  --t1 / --t2     wall-clock timestamps → timestamp mode
  --clap          detect first sharp transient in each WAV → clap mode
  (default)       match word sequences from volcano_raw_track*.json → transcript mode

Output: audio_meta.json gains {"track_offsets_ms": [0, N, ...]}
  offset[i] = ms by which track i+1 lags behind the earliest track.
  Applying offset: add offset[i] to each word's start_ms / end_ms from that track.
"""
from __future__ import annotations

import argparse
import difflib
import json
import struct
import subprocess
import sys
from pathlib import Path


# ── Timestamp mode ────────────────────────────────────────────────────────────

def _parse_ts(ts: str) -> int:
    """Parse HH:MM:SS or HH:MM:SS.mmm to milliseconds."""
    parts = ts.split(":")
    h, m = int(parts[0]), int(parts[1])
    s = float(parts[2])
    return int((h * 3600 + m * 60 + s) * 1000)


def _offsets_from_timestamps(ts_list: list[str]) -> list[int]:
    ms_list = [_parse_ts(t) for t in ts_list]
    base = min(ms_list)
    return [v - base for v in ms_list]


# ── Clap mode ─────────────────────────────────────────────────────────────────

def _find_peak_ms(wav_path: Path, search_seconds: int = 30) -> int:
    """Return ms position of the loudest sample in the first `search_seconds`."""
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(wav_path),
        "-t", str(search_seconds),
        "-af", "aresample=16000",
        "-f", "s16le", "-ac", "1", "pipe:1",
    ]
    result = subprocess.run(cmd, capture_output=True, check=True)
    if not result.stdout:
        raise RuntimeError(f"No audio data from {wav_path}")
    count = len(result.stdout) // 2
    samples = struct.unpack(f"{count}h", result.stdout[:count * 2])
    peak_idx = max(range(len(samples)), key=lambda i: abs(samples[i]))
    return int(peak_idx / 16000 * 1000)


def _offsets_from_clap(wav_paths: list[Path]) -> list[int]:
    peaks = [_find_peak_ms(p) for p in wav_paths]
    base = min(peaks)
    return [p - base for p in peaks]


# ── Transcript mode ───────────────────────────────────────────────────────────

def _load_words_from_raw(raw: dict) -> list[dict]:
    words = []
    for utt in raw.get("resp", {}).get("utterances", []):
        for w in utt.get("words", []):
            words.append({"text": w["text"], "start_ms": w["start_time"], "end_ms": w["end_time"]})
    return words


def _infer_offset_pair(words1: list[dict], words2: list[dict]) -> int:
    """Compute offset = words2.start_ms - words1.start_ms for matching sequences.

    Returns the median offset across all matching blocks of >= 3 consecutive words.
    Returns 0 if no matching blocks found (safe default: no shift).
    """
    texts1 = [w["text"] for w in words1]
    texts2 = [w["text"] for w in words2]
    matcher = difflib.SequenceMatcher(None, texts1, texts2, autojunk=False)
    offsets: list[int] = []
    for block in matcher.get_matching_blocks():
        if block.size < 3:
            continue
        t1 = words1[block.a]["start_ms"]
        t2 = words2[block.b]["start_ms"]
        offsets.append(t2 - t1)
    if not offsets:
        print("[align] WARNING: no matching word sequences found; defaulting to offset=0", file=sys.stderr)
        return 0
    offsets.sort()
    median = offsets[len(offsets) // 2]
    print(f"[align] transcript mode: {len(offsets)} matching blocks, median offset = {median} ms")
    return median


def _offsets_from_transcripts(raw_files: list[Path]) -> list[int]:
    all_words = [_load_words_from_raw(json.loads(p.read_text())) for p in raw_files]
    if len(all_words) < 2:
        return [0]
    # compute offset of each track vs track 0
    raw_offsets = [0]
    for i in range(1, len(all_words)):
        raw_offsets.append(_infer_offset_pair(all_words[0], all_words[i]))
    base = min(raw_offsets)
    return [o - base for o in raw_offsets]


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Compute inter-track timing offsets.")
    ap.add_argument("--ep-dir", required=True)
    ap.add_argument("--clap", action="store_true", help="Clap mode: find loudest transient in each WAV.")
    ap.add_argument("--t1", default=None, help="Wall-clock start time of track 1 (HH:MM:SS).")
    ap.add_argument("--t2", default=None, help="Wall-clock start time of track 2 (HH:MM:SS).")
    args = ap.parse_args()

    ep_dir = Path(args.ep_dir)
    in_dir = ep_dir / "input"
    meta_path = in_dir / "audio_meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"audio_meta.json not found in {in_dir}. Run prepare_audio.py first.")
    meta = json.loads(meta_path.read_text())
    n_tracks = len(meta.get("tracks", []))

    if n_tracks < 2:
        print("[align] single-track episode; nothing to align.")
        meta["track_offsets_ms"] = [0]
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
        return

    # detect mode
    if args.t1 is not None or args.t2 is not None:
        if args.t1 is None or args.t2 is None:
            ap.error("--t1 and --t2 must both be provided for timestamp mode.")
        ts_args = [args.t1, args.t2]
        if n_tracks > 2:
            ap.error("Timestamp mode only supports 2 tracks via --t1/--t2.")
        offsets = _offsets_from_timestamps(ts_args)
        print(f"[align] timestamp mode: offsets = {offsets} ms")
    elif args.clap:
        wav_paths = [in_dir / t["file"] for t in meta["tracks"]]
        for p in wav_paths:
            if not p.exists():
                raise FileNotFoundError(f"WAV not found: {p}. Run prepare_audio.py first.")
        offsets = _offsets_from_clap(wav_paths)
        print(f"[align] clap mode: offsets = {offsets} ms")
    else:
        td = ep_dir / "1_transcribe"
        raw_files = sorted(td.glob("volcano_raw_track*.json"))
        if not raw_files:
            raise FileNotFoundError(
                f"No volcano_raw_track*.json in {td}. "
                "Run volcano_submit.py + volcano_query.py first, or use --clap / --t1 / --t2."
            )
        offsets = _offsets_from_transcripts(raw_files)
        print(f"[align] transcript mode: offsets = {offsets} ms")

    meta["track_offsets_ms"] = offsets
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"[align] wrote track_offsets_ms={offsets} to {meta_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/scripts/test_align_tracks.py -v
```
Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add shared/scripts/align_tracks.py tests/scripts/test_align_tracks.py
git commit -m "feat: add align_tracks.py (stage 1.05) — clap, timestamp, transcript modes"
```

---

## Task 2: Update `transcribe_merge.py` to apply offsets

**Files:**
- Modify: `shared/scripts/transcribe_merge.py`
- Modify: `tests/scripts/test_transcribe_merge.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/scripts/test_transcribe_merge.py`:

```python
def test_track_offsets_applied(tmp_path):
    """track_offsets_ms in audio_meta.json shifts word timestamps before merge."""
    import importlib.util, sys, json
    from pathlib import Path

    SCRIPTS = Path(__file__).parent.parent.parent / "shared" / "scripts"
    spec = importlib.util.spec_from_file_location("transcribe_merge", SCRIPTS / "transcribe_merge.py")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS))
    spec.loader.exec_module(mod)

    ep_dir = tmp_path / "ep"
    td = ep_dir / "1_transcribe"
    in_dir = ep_dir / "input"
    td.mkdir(parents=True)
    in_dir.mkdir(parents=True)

    # track1: word at 0ms; track2: same word at 0ms but track2 starts 500ms later
    raw1 = {"resp": {"utterances": [{"words": [
        {"text": "嗯", "start_time": 0, "end_time": 300, "confidence": 0.9, "blank_duration": 50},
    ]}]}}
    raw2 = {"resp": {"utterances": [{"words": [
        {"text": "对", "start_time": 0, "end_time": 300, "confidence": 0.9, "blank_duration": 50},
    ]}]}}
    (td / "volcano_raw_track1.json").write_text(json.dumps(raw1))
    (td / "volcano_raw_track2.json").write_text(json.dumps(raw2))

    # offset: track2 lags 500ms
    meta = {
        "episode_id": "test", "total_duration_ms": 5000,
        "tracks": [
            {"file": "working_track1.wav", "duration_ms": 5000, "sample_rate": 44100},
            {"file": "working_track2.wav", "duration_ms": 5000, "sample_rate": 44100},
        ],
        "track_offsets_ms": [0, 500],
    }
    (in_dir / "audio_meta.json").write_text(json.dumps(meta))

    sys.argv = ["transcribe_merge.py", "--ep-dir", str(ep_dir)]
    mod.main()

    words_json = json.loads((td / "words.json").read_text())
    words = words_json["words"]
    # S1 word: still at 0ms (no shift); S2 word: shifted to 500ms
    s1 = next(w for w in words if w["speaker"] == "S1")
    s2 = next(w for w in words if w["speaker"] == "S2")
    assert s1["start_ms"] == 0
    assert s2["start_ms"] == 500
    # merged order: S1 first
    assert words[0]["speaker"] == "S1"
    assert words[1]["speaker"] == "S2"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/scripts/test_transcribe_merge.py::test_track_offsets_applied -v
```
Expected: FAIL — offset not applied yet.

- [ ] **Step 3: Update `transcribe_merge.py`**

In `main()`, after loading `audio_meta.json`, read `track_offsets_ms`. Apply to each track's words before extending `all_words`.

Replace the loop in `main()`:

```python
    # load offsets from audio_meta.json (written by align_tracks.py)
    meta_file = ep_dir / "input" / "audio_meta.json"
    meta = {}
    if meta_file.exists():
        meta = json.loads(meta_file.read_text())
    offsets = meta.get("track_offsets_ms", [0] * len(track_files))
    # pad with zeros if fewer offsets than tracks
    while len(offsets) < len(track_files):
        offsets.append(0)

    all_words = []
    speakers = []
    track_names = []
    for i, tf in enumerate(track_files, start=1):
        raw = json.loads(tf.read_text())
        speaker = f"S{i}"
        speakers.append({"id": speaker, "name": None, "track": f"working_track{i}.wav"})
        track_names.append(f"working_track{i}.wav")
        shift = offsets[i - 1]
        words = _parse_words_from_raw(raw, speaker)
        if shift:
            for w in words:
                w["start_ms"] += shift
                w["end_ms"] += shift
        all_words.extend(words)
```

Also remove the redundant `meta_file` read that currently happens after the loop (it now happens before). Replace the `duration_ms` probe:

```python
    all_words.sort(key=lambda w: w["start_ms"])
    for i, w in enumerate(all_words):
        w["idx"] = i

    duration_ms = all_words[-1]["end_ms"] if all_words else 0
    duration_ms = meta.get("total_duration_ms", duration_ms)
```

Full updated `main()` for clarity:

```python
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

    meta_file = ep_dir / "input" / "audio_meta.json"
    meta = json.loads(meta_file.read_text()) if meta_file.exists() else {}
    offsets = meta.get("track_offsets_ms", [0] * len(track_files))
    while len(offsets) < len(track_files):
        offsets.append(0)

    all_words: list[dict] = []
    speakers: list[dict] = []
    track_names: list[str] = []
    for i, tf in enumerate(track_files, start=1):
        raw = json.loads(tf.read_text())
        speaker = f"S{i}"
        speakers.append({"id": speaker, "name": None, "track": f"working_track{i}.wav"})
        track_names.append(f"working_track{i}.wav")
        shift = offsets[i - 1]
        words = _parse_words_from_raw(raw, speaker)
        if shift:
            for w in words:
                w["start_ms"] += shift
                w["end_ms"] += shift
        all_words.extend(words)

    mode = "two_track" if len(track_files) >= 2 else "single_track"
    all_words.sort(key=lambda w: w["start_ms"])
    for i, w in enumerate(all_words):
        w["idx"] = i

    duration_ms = all_words[-1]["end_ms"] if all_words else 0
    duration_ms = meta.get("total_duration_ms", duration_ms)

    out = {
        "episode_id": ep_id,
        "duration_ms": duration_ms,
        "source": {"tracks": track_names, "mode": mode},
        "speakers": speakers,
        "words": all_words,
    }
    (td / "words.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"words.json: {len(all_words)} words, mode={mode}, offsets={offsets}")
```

- [ ] **Step 4: Run all transcribe_merge tests**

```bash
python -m pytest tests/scripts/test_transcribe_merge.py -v
```
Expected: all 4 tests pass (3 existing + 1 new).

- [ ] **Step 5: Run full suite to check for regressions**

```bash
python -m pytest tests/ -q
```
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add shared/scripts/transcribe_merge.py tests/scripts/test_transcribe_merge.py
git commit -m "feat: apply track_offsets_ms in transcribe_merge.py"
```

---

## Pipeline placement

`align_tracks.py` fits between `prepare_audio.py` and `volcano_submit.py` for clap/timestamp modes, or between `volcano_query.py` and `transcribe_merge.py` for transcript mode:

```
prepare_audio.py
align_tracks.py --clap          ← if recording had a sync clap
align_tracks.py --t1 T --t2 T  ← if you know recorder start times
volcano_submit.py
volcano_query.py
align_tracks.py                 ← (no flags) transcript inference
transcribe_merge.py             ← reads track_offsets_ms, shifts words
make_sentences.py
...
```

Skipping `align_tracks.py` entirely is safe — `transcribe_merge.py` defaults to `[0, 0, ...]` if `track_offsets_ms` is absent.
