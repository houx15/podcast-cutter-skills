# 剪播客 (Stages 1–4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the full /podcast-cut-剪播客 skill: prepare audio → Volcano ASR → LLM analysis → review HTML → cut.wav

**Architecture:** 12 scripts under `shared/scripts/`, each a CLI tool (JSON in / JSON out). All share `shared/scripts/lib/` (config, volcano_client, ffmpeg_wrap, upload, json_io). Output lands in `output/<ep>/` with 4 stage subdirs.

**Tech Stack:** Python 3.10+, ffmpeg, openai SDK (ByteDance Ark / doubao), requests, flask, python-dotenv

---

## File map

| Create | Purpose |
|---|---|
| `shared/scripts/prepare_audio.py` | probe input, mono-16bit WAVs, audio_meta.json |
| `shared/scripts/volcano_submit.py` | upload + submit to Volcano v3 AUC |
| `shared/scripts/volcano_query.py` | poll until done, save volcano_raw_*.json |
| `shared/scripts/transcribe_merge.py` | raw JSON → words.json (2-track merge by start_ms) |
| `shared/scripts/make_sentences.py` | words.json → sentences.json |
| `shared/scripts/analyze_rough.py` | LLM rough cuts → rough_cuts.json |
| `shared/scripts/analyze_fine.py` | LLM fine cuts → fine_cuts.json |
| `shared/scripts/self_review.py` | LLM self-review → self_review.json |
| `shared/scripts/cut_audio.py` | delete_segments_edited.json → cut.wav (25ms xfade) |
| `shared/scripts/trim_silences.py` | head/tail 200ms trim, overwrite cut.wav |
| `shared/scripts/generate_review_html.py` | render review_enhanced.html |
| `shared/scripts/review_server.py` | Flask server, PATCH review_state.json |
| `shared/rules/editing/1-核心原则.md` | LLM editing rules |
| `shared/rules/users/default/preferences.yaml` | default user prefs |
| `shared/rules/users/default/hotwords.txt` | default hotwords (empty) |
| `.claude/skills/podcast-cut-剪播客/SKILL.md` | skill definition |
| `docs/剪播客/阶段1-转录.md` | stage 1 detail doc |
| `docs/剪播客/阶段2-分析.md` | stage 2 detail doc |
| `docs/剪播客/阶段3-审查.md` | stage 3 detail doc |
| `docs/剪播客/阶段4-剪辑.md` | stage 4 detail doc |

| Modify | What changes |
|---|---|
| `pyproject.toml` | add openai>=1.0.0, flask>=3.0.0, tos-python-sdk (optional) |
| `shared/scripts/lib/config.py` | add LLMConfig dataclass + llm field on Config |
| `.env.example` | add LLM_API_KEY, LLM_BASE_URL, LLM_MODEL |
| `CHANGELOG.md` | v0.2.0 entry |

---

### Task 1: Dependencies, LLMConfig, and test fixtures

**Files:**
- Modify: `pyproject.toml`
- Modify: `shared/scripts/lib/config.py`
- Modify: `.env.example`
- Modify: `tests/lib/test_config.py`
- Create: `tests/conftest_audio.py` (synthetic 5s WAV fixture shared across tests)

- [ ] **Step 1: Write failing test for LLMConfig**

```python
# tests/lib/test_config.py  (add to existing file)
def test_llm_config_loaded(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "VOLC_API_KEY=testkey\n"
        "LLM_API_KEY=ark-test\n"
        "LLM_BASE_URL=https://ark.example.com/api/v3\n"
        "LLM_MODEL=doubao-test\n"
    )
    from lib.config import load
    cfg = load(env)
    assert cfg.llm.api_key == "ark-test"
    assert cfg.llm.base_url == "https://ark.example.com/api/v3"
    assert cfg.llm.model == "doubao-test"

def test_llm_config_missing_key_raises(tmp_path):
    env = tmp_path / ".env"
    env.write_text("VOLC_API_KEY=testkey\nLLM_BASE_URL=https://x\nLLM_MODEL=m\n")
    from lib.config import load, ConfigError
    with pytest.raises(ConfigError, match="LLM_API_KEY"):
        load(env)
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
cd /Users/houyuxin/08Coding/podcast-cutter-skills
python -m pytest tests/lib/test_config.py::test_llm_config_loaded -xvs 2>&1 | tail -20
```

Expected: `AttributeError` or `ImportError`

- [ ] **Step 3: Add openai and flask to pyproject.toml**

In `[project] dependencies`, add:
```toml
"openai>=1.0.0",
"flask>=3.0.0",
```

Run `pip install -e ".[dev]"` to verify install.

- [ ] **Step 4: Add LLMConfig to config.py**

Add after `S3Config`:
```python
@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    base_url: str
    model: str
```

Add `llm: LLMConfig` field to `Config` dataclass.

Add `_build_llm` function:
```python
def _build_llm(raw: dict[str, str | None]) -> "LLMConfig":
    api_key = _nonempty(raw, "LLM_API_KEY")
    base_url = _nonempty(raw, "LLM_BASE_URL")
    model = _nonempty(raw, "LLM_MODEL")
    if not api_key:
        raise ConfigError("LLM_API_KEY is required")
    if not base_url:
        raise ConfigError("LLM_BASE_URL is required")
    if not model:
        raise ConfigError("LLM_MODEL is required")
    return LLMConfig(api_key=api_key, base_url=base_url, model=model)
```

Update `load()` to call `_build_llm(raw)` and pass `llm=llm` to `Config(...)`.

- [ ] **Step 5: Update .env.example**

Add to `.env.example`:
```
# LLM — ByteDance Ark (doubao), OpenAI-compatible
LLM_API_KEY=
LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
LLM_MODEL=doubao-seed-2-0-code-preview-260215
```

- [ ] **Step 6: Run tests to confirm PASS**

```bash
python -m pytest tests/lib/test_config.py -xvs 2>&1 | tail -20
```

Expected: all green

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml shared/scripts/lib/config.py .env.example tests/lib/test_config.py
git commit -m "feat: add LLMConfig to config.py + openai/flask deps"
```

---

### Task 2: prepare_audio.py

**Files:**
- Create: `shared/scripts/prepare_audio.py`
- Create: `tests/scripts/test_prepare_audio.py`

The script: given 1 or 2 audio files, converts each to mono 16-bit WAV (original sample rate preserved), writes to `output/<ep>/input/working_track*.wav`, writes `audio_meta.json`.

CLI: `python prepare_audio.py --track1 path.wav [--track2 path.wav] --ep-dir output/ep01`

`audio_meta.json`:
```json
{
  "episode_id": "ep01",
  "mode": "two_track",
  "tracks": [{"file": "working_track1.wav", "duration_ms": 7200000, "sample_rate": 44100}],
  "total_duration_ms": 7200000
}
```

- [ ] **Step 1: Write failing tests**

```python
# tests/scripts/test_prepare_audio.py
import subprocess, json
from pathlib import Path
import pytest

@pytest.fixture
def tiny_wav(tmp_path):
    """5-second 44100 Hz mono WAV via ffmpeg."""
    out = tmp_path / "input.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
         "-af", "volume=4", "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(out)],
        check=True, capture_output=True
    )
    return out

def test_single_track_creates_outputs(tiny_wav, tmp_path):
    ep_dir = tmp_path / "output" / "ep01"
    subprocess.run(
        ["python", "shared/scripts/prepare_audio.py",
         "--track1", str(tiny_wav), "--ep-dir", str(ep_dir)],
        check=True, capture_output=True,
        cwd="/Users/houyuxin/08Coding/podcast-cutter-skills"
    )
    assert (ep_dir / "input" / "working_track1.wav").exists()
    meta = json.loads((ep_dir / "input" / "audio_meta.json").read_text())
    assert meta["mode"] == "single_track"
    assert meta["total_duration_ms"] > 0
    assert len(meta["tracks"]) == 1

def test_two_track_creates_both(tiny_wav, tmp_path):
    ep_dir = tmp_path / "output" / "ep01"
    subprocess.run(
        ["python", "shared/scripts/prepare_audio.py",
         "--track1", str(tiny_wav), "--track2", str(tiny_wav),
         "--ep-dir", str(ep_dir)],
        check=True, capture_output=True,
        cwd="/Users/houyuxin/08Coding/podcast-cutter-skills"
    )
    assert (ep_dir / "input" / "working_track1.wav").exists()
    assert (ep_dir / "input" / "working_track2.wav").exists()
    meta = json.loads((ep_dir / "input" / "audio_meta.json").read_text())
    assert meta["mode"] == "two_track"
    assert len(meta["tracks"]) == 2

def test_idempotent_rerun(tiny_wav, tmp_path):
    ep_dir = tmp_path / "output" / "ep01"
    for _ in range(2):
        subprocess.run(
            ["python", "shared/scripts/prepare_audio.py",
             "--track1", str(tiny_wav), "--ep-dir", str(ep_dir)],
            check=True, capture_output=True,
            cwd="/Users/houyuxin/08Coding/podcast-cutter-skills"
        )
    meta = json.loads((ep_dir / "input" / "audio_meta.json").read_text())
    assert meta["mode"] == "single_track"
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
python -m pytest tests/scripts/test_prepare_audio.py -xvs 2>&1 | tail -15
```

Expected: `FileNotFoundError` (script doesn't exist)

- [ ] **Step 3: Implement prepare_audio.py**

```python
#!/usr/bin/env python3
"""Stage 1.0: convert input audio to working WAVs (mono, 16-bit, original SR)."""
from __future__ import annotations
import argparse, json, subprocess
from pathlib import Path

def probe_duration_ms(path: Path) -> int:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True
    )
    return int(float(r.stdout.strip()) * 1000)

def probe_sample_rate(path: Path) -> int:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=sample_rate",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True
    )
    return int(r.stdout.strip())

def convert_to_working_wav(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    sr = probe_sample_rate(src)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src),
         "-ac", "1", "-ar", str(sr), "-c:a", "pcm_s16le", str(dst)],
        check=True, capture_output=True
    )

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--track1", required=True)
    ap.add_argument("--track2", default=None)
    ap.add_argument("--ep-dir", required=True)
    ap.add_argument("--ep-id", default=None)
    args = ap.parse_args()

    ep_dir = Path(args.ep_dir)
    ep_id = args.ep_id or ep_dir.name
    in_dir = ep_dir / "input"
    in_dir.mkdir(parents=True, exist_ok=True)

    tracks = [Path(args.track1)]
    if args.track2:
        tracks.append(Path(args.track2))

    mode = "two_track" if len(tracks) == 2 else "single_track"
    track_metas = []
    for i, src in enumerate(tracks, start=1):
        dst = in_dir / f"working_track{i}.wav"
        convert_to_working_wav(src, dst)
        dur = probe_duration_ms(dst)
        sr = probe_sample_rate(dst)
        track_metas.append({"file": dst.name, "duration_ms": dur, "sample_rate": sr})

    total_ms = max(t["duration_ms"] for t in track_metas)
    meta = {
        "episode_id": ep_id,
        "mode": mode,
        "tracks": track_metas,
        "total_duration_ms": total_ms,
    }
    (in_dir / "audio_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(json.dumps(meta))

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to confirm PASS**

```bash
python -m pytest tests/scripts/test_prepare_audio.py -xvs 2>&1 | tail -15
```

Expected: 3 tests green

- [ ] **Step 5: Commit**

```bash
git add shared/scripts/prepare_audio.py tests/scripts/test_prepare_audio.py
git commit -m "feat: add prepare_audio.py (stage 1.0)"
```

---

### Task 3: volcano_submit.py and volcano_query.py

**Files:**
- Create: `shared/scripts/volcano_submit.py`
- Create: `shared/scripts/volcano_query.py`
- Create: `tests/scripts/test_volcano_scripts.py`

`volcano_submit.py` CLI: `python volcano_submit.py --audio-url URL --audio-format wav --ep-dir output/ep01 --track-num 1`
Writes `output/ep01/1_transcribe/task_id_track1.txt`

`volcano_query.py` CLI: `python volcano_query.py --ep-dir output/ep01 --track-num 1`
Reads task_id_track1.txt, polls until done, writes `volcano_raw_track1.json`

- [ ] **Step 1: Write failing tests**

```python
# tests/scripts/test_volcano_scripts.py
import subprocess, json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

REPO = "/Users/houyuxin/08Coding/podcast-cutter-skills"

def test_submit_writes_task_id(tmp_path, monkeypatch):
    """submit should write task_id_track1.txt in 1_transcribe/."""
    import sys; sys.path.insert(0, f"{REPO}/shared/scripts")
    from lib.config import VolcanoConfig
    import importlib.util, types

    # patch requests.post to return fake task id
    import requests
    fake_resp = MagicMock()
    fake_resp.json.return_value = {"resp": {"task_id": "fake-task-123"}}
    fake_resp.raise_for_status = MagicMock()

    with patch("requests.post", return_value=fake_resp):
        spec = importlib.util.spec_from_file_location(
            "volcano_submit", f"{REPO}/shared/scripts/volcano_submit.py")
        mod = importlib.util.module_from_spec(spec)
        import sys as _sys; _sys.argv = [
            "volcano_submit.py",
            "--audio-url", "https://example.com/audio.wav",
            "--audio-format", "wav",
            "--ep-dir", str(tmp_path),
            "--track-num", "1",
            "--env", f"{REPO}/.env",
        ]
        spec.loader.exec_module(mod)

    task_file = tmp_path / "1_transcribe" / "task_id_track1.txt"
    assert task_file.exists()
    assert task_file.read_text().strip() == "fake-task-123"

def test_query_writes_raw_json(tmp_path):
    """query should poll and write volcano_raw_track1.json."""
    import sys; sys.path.insert(0, f"{REPO}/shared/scripts")
    import requests
    task_dir = tmp_path / "1_transcribe"
    task_dir.mkdir()
    (task_dir / "task_id_track1.txt").write_text("fake-task-123")

    fake_resp = MagicMock()
    fake_resp.json.return_value = {
        "resp": {
            "code": 1000,
            "utterances": [
                {"words": [{"text": "你好", "start_time": 100, "end_time": 500,
                            "confidence": 0.99, "blank_duration": 0}]}
            ]
        }
    }
    fake_resp.raise_for_status = MagicMock()

    with patch("requests.post", return_value=fake_resp):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "volcano_query", f"{REPO}/shared/scripts/volcano_query.py")
        mod = importlib.util.module_from_spec(spec)
        import sys as _sys; _sys.argv = [
            "volcano_query.py",
            "--ep-dir", str(tmp_path),
            "--track-num", "1",
            "--env", f"{REPO}/.env",
        ]
        spec.loader.exec_module(mod)

    raw = json.loads((task_dir / "volcano_raw_track1.json").read_text())
    assert "resp" in raw
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
python -m pytest tests/scripts/test_volcano_scripts.py -xvs 2>&1 | tail -15
```

- [ ] **Step 3: Implement volcano_submit.py**

```python
#!/usr/bin/env python3
"""Stage 1.2a: upload URL + submit to Volcano AUC big-model ASR."""
from __future__ import annotations
import argparse, json
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
    import sys; sys.path.insert(0, str(Path(__file__).parent))
    from lib.config import load
    from lib.volcano_client import build_submit_headers, build_submit_payload, SUBMIT_URL
    import uuid

    cfg = load(env_path)
    task_id = str(uuid.uuid4())
    headers = build_submit_headers(cfg.volcano, task_id)
    payload = build_submit_payload(
        audio_url=args.audio_url,
        audio_format=args.audio_format,
        uid=args.uid,
        enable_speaker_info=(args.track_num == 0),  # only for merged single-track
        hotwords=[],
        resource_id=cfg.volcano.resource_id,
    )
    resp = requests.post(SUBMIT_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    returned_task_id = data["resp"]["task_id"]

    ep_dir = Path(args.ep_dir)
    out_dir = ep_dir / "1_transcribe"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"task_id_track{args.track_num}.txt").write_text(returned_task_id)
    print(returned_task_id)

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Implement volcano_query.py**

```python
#!/usr/bin/env python3
"""Stage 1.2b: poll Volcano AUC until done, write volcano_raw_track*.json."""
from __future__ import annotations
import argparse, json, time
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
    import sys; sys.path.insert(0, str(Path(__file__).parent))
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
        status = classify_status(data["resp"]["code"])
        if status == QueryStatus.DONE:
            out = ep_dir / "1_transcribe" / f"volcano_raw_track{args.track_num}.json"
            out.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            print(f"Done → {out}")
            return
        if status == QueryStatus.FAILED:
            raise RuntimeError(f"Volcano task failed: {data}")
        time.sleep(args.interval)

    raise TimeoutError(f"Volcano task {task_id} did not complete in {args.max_attempts} attempts")

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to confirm PASS**

```bash
python -m pytest tests/scripts/test_volcano_scripts.py -xvs 2>&1 | tail -20
```

- [ ] **Step 6: Commit**

```bash
git add shared/scripts/volcano_submit.py shared/scripts/volcano_query.py tests/scripts/test_volcano_scripts.py
git commit -m "feat: add volcano_submit.py and volcano_query.py (stage 1.2)"
```

---

### Task 4: transcribe_merge.py

**Files:**
- Create: `shared/scripts/transcribe_merge.py`
- Create: `tests/scripts/test_transcribe_merge.py`

CLI: `python transcribe_merge.py --ep-dir output/ep01`
Reads `volcano_raw_track*.json`, writes `words.json`.

Two-track: each track's words get `speaker = S1` / `S2`, streams merged by `start_ms`.
Single-track: speaker from Volcano `enable_speaker_info` (`word_info.speaker_info`), default `S1`.

Volcano raw utterance → word mapping:
- `text` → `text`
- `start_time` (ms int) → `start_ms`
- `end_time` (ms int) → `end_ms`
- `confidence` → `confidence`
- `blank_duration` (ms) → `blank_after_ms`
- `emotion` → `emotion` (may not be present)
- `lang` or `lid` → `lid`

- [ ] **Step 1: Write failing tests**

```python
# tests/scripts/test_transcribe_merge.py
import json, subprocess
from pathlib import Path
import pytest

REPO = "/Users/houyuxin/08Coding/podcast-cutter-skills"

def _raw(task_id="t1", words=None):
    words = words or [{"text": "你", "start_time": 100, "end_time": 300,
                        "confidence": 0.9, "blank_duration": 50}]
    return {"resp": {"code": 1000, "task_id": task_id,
                     "utterances": [{"words": words}]}}

def test_single_track_words_json(tmp_path):
    ep = tmp_path / "ep01"
    td = ep / "1_transcribe"
    td.mkdir(parents=True)
    (td / "volcano_raw_track1.json").write_text(json.dumps(_raw()))

    subprocess.run(
        ["python", "shared/scripts/transcribe_merge.py", "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO
    )

    words = json.loads((td / "words.json").read_text())
    assert words["source"]["mode"] == "single_track"
    assert len(words["words"]) == 1
    assert words["words"][0]["speaker"] == "S1"
    assert words["words"][0]["start_ms"] == 100
    assert words["words"][0]["text"] == "你"

def test_two_track_merge_sorted(tmp_path):
    ep = tmp_path / "ep01"
    td = ep / "1_transcribe"
    td.mkdir(parents=True)
    raw1 = _raw("t1", [{"text": "A", "start_time": 200, "end_time": 400,
                         "confidence": 0.9, "blank_duration": 0}])
    raw2 = _raw("t2", [{"text": "B", "start_time": 100, "end_time": 300,
                         "confidence": 0.8, "blank_duration": 0}])
    (td / "volcano_raw_track1.json").write_text(json.dumps(raw1))
    (td / "volcano_raw_track2.json").write_text(json.dumps(raw2))

    subprocess.run(
        ["python", "shared/scripts/transcribe_merge.py", "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO
    )

    words = json.loads((td / "words.json").read_text())
    assert words["source"]["mode"] == "two_track"
    assert words["words"][0]["text"] == "B"   # start_ms=100 first
    assert words["words"][0]["speaker"] == "S2"
    assert words["words"][1]["speaker"] == "S1"
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
python -m pytest tests/scripts/test_transcribe_merge.py -xvs 2>&1 | tail -15
```

- [ ] **Step 3: Implement transcribe_merge.py**

```python
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
```

- [ ] **Step 4: Run tests to confirm PASS**

```bash
python -m pytest tests/scripts/test_transcribe_merge.py -xvs 2>&1 | tail -15
```

- [ ] **Step 5: Commit**

```bash
git add shared/scripts/transcribe_merge.py tests/scripts/test_transcribe_merge.py
git commit -m "feat: add transcribe_merge.py (stage 1.3)"
```

---

### Task 5: make_sentences.py

**Files:**
- Create: `shared/scripts/make_sentences.py`
- Create: `tests/scripts/test_make_sentences.py`

CLI: `python make_sentences.py --ep-dir output/ep01`
Reads `words.json`, writes `sentences.json`.

Grouping rule: new sentence when `blank_after_ms >= 500` OR speaker changes OR sentence length >= 50 chars. Each sentence: id, speaker, start_ms, end_ms, word_idx_start, word_idx_end, text.

- [ ] **Step 1: Write failing tests**

```python
# tests/scripts/test_make_sentences.py
import json, subprocess
from pathlib import Path

REPO = "/Users/houyuxin/08Coding/podcast-cutter-skills"

def _words_json(tmp_path, words):
    ep = tmp_path / "ep01"
    td = ep / "1_transcribe"
    td.mkdir(parents=True)
    data = {
        "episode_id": "ep01", "duration_ms": 10000,
        "source": {"tracks": ["t1.wav"], "mode": "single_track"},
        "speakers": [{"id": "S1", "name": None, "track": "t1.wav"}],
        "words": words
    }
    (td / "words.json").write_text(json.dumps(data))
    return ep

def _w(idx, speaker, start, end, text, blank=0):
    return {"idx": idx, "speaker": speaker, "start_ms": start,
            "end_ms": end, "text": text, "confidence": 0.9,
            "blank_after_ms": blank, "emotion": None, "lid": None}

def test_single_sentence(tmp_path):
    ep = _words_json(tmp_path, [
        _w(0, "S1", 0, 500, "你好", 100),
        _w(1, "S1", 600, 1000, "世界", 0),
    ])
    subprocess.run(
        ["python", "shared/scripts/make_sentences.py", "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO
    )
    sents = json.loads((ep / "1_transcribe" / "sentences.json").read_text())
    assert len(sents["sentences"]) == 1
    assert sents["sentences"][0]["text"] == "你好世界"

def test_speaker_change_splits(tmp_path):
    ep = _words_json(tmp_path, [
        _w(0, "S1", 0, 500, "你好", 0),
        _w(1, "S2", 600, 1000, "世界", 0),
    ])
    subprocess.run(
        ["python", "shared/scripts/make_sentences.py", "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO
    )
    sents = json.loads((ep / "1_transcribe" / "sentences.json").read_text())
    assert len(sents["sentences"]) == 2

def test_long_pause_splits(tmp_path):
    ep = _words_json(tmp_path, [
        _w(0, "S1", 0, 500, "你好", 600),  # 600ms pause → split
        _w(1, "S1", 1100, 1500, "世界", 0),
    ])
    subprocess.run(
        ["python", "shared/scripts/make_sentences.py", "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO
    )
    sents = json.loads((ep / "1_transcribe" / "sentences.json").read_text())
    assert len(sents["sentences"]) == 2
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
python -m pytest tests/scripts/test_make_sentences.py -xvs 2>&1 | tail -15
```

- [ ] **Step 3: Implement make_sentences.py**

```python
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
    words = json.loads((td / "words.json").read_text())["words"]

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
```

- [ ] **Step 4: Run tests to confirm PASS**

```bash
python -m pytest tests/scripts/test_make_sentences.py -xvs 2>&1 | tail -15
```

- [ ] **Step 5: Commit**

```bash
git add shared/scripts/make_sentences.py tests/scripts/test_make_sentences.py
git commit -m "feat: add make_sentences.py (stage 1.4)"
```

---

### Task 6: Editing rules and user preferences

**Files:**
- Create: `shared/rules/editing/1-核心原则.md`
- Create: `shared/rules/users/default/preferences.yaml`
- Create: `shared/rules/users/default/hotwords.txt`

No tests needed (data files). Create and commit.

- [ ] **Step 1: Create editing rules**

`shared/rules/editing/1-核心原则.md`:
```markdown
# 播客剪辑核心原则

## 应删除的内容（rough pass）
1. **录前/录后闲聊**: 录音开始后主题正式开始前的闲聊、调试麦克风的内容
2. **明显口误+自我纠正**: 说错后立刻纠正，保留纠正后版本，删去口误部分
3. **长停顿**: 超过3秒的静音或语气词填充（"那个...那个...那个"重复超过2次）
4. **与主题完全无关的题外话**: 外卖、手机响、旁白等明显与内容无关的插入

## 应删除的内容（fine pass）
1. **口头禅/语气词**: 高频重复的"嗯"、"啊"、"对对对"、"然后然后然后"
2. **冗余解释**: 同一观点在30秒内用几乎相同的措辞重复两次，删去重复
3. **犹豫填充**: "怎么说呢"、"就是那种"开头但无实质内容的句子

## 不应删除的内容
1. **情感停顿**: 说到动情处的沉默、笑声
2. **自然思考停顿**: 提问后的停顿、回忆时的停顿（<1.5s）
3. **对话节奏词**: 互相呼应的"对"、"是的"、"嗯嗯"不超过1秒的
4. **强调重复**: 故意重复以强调语气（"这很重要，很重要"）

## 剪辑风格
- 保留真实感，不追求播音腔流畅度
- 保留讲者个性（方言词、个人口头禅，除非密集到影响理解）
- 宁可少删，不要误删（confidence 阈值 0.7）
```

`shared/rules/users/default/preferences.yaml`:
```yaml
user_id: default
language: zh-CN
style: natural  # natural | polished
aggressiveness: moderate  # conservative | moderate | aggressive
min_confidence: 0.7
max_delete_ratio: 0.4  # never delete more than 40% of audio
preserve_laughter: true
preserve_emotional_pauses: true
```

`shared/rules/users/default/hotwords.txt`:
```
# One hotword per line. Feeds Volcano corpus.context.hotwords.
# Example:
# 字节跳动
# 豆包
```

- [ ] **Step 2: Commit**

```bash
git add shared/rules/
git commit -m "feat: add editing rules and default user preferences"
```

---

### Task 7: analyze_rough.py

**Files:**
- Create: `shared/scripts/analyze_rough.py`
- Create: `tests/scripts/test_analyze_rough.py`

CLI: `python analyze_rough.py --ep-dir output/ep01 --env .env`
Reads sentences.json + editing rules, calls LLM (ByteDance Ark / doubao), writes `rough_cuts.json`.

LLM call: `openai.OpenAI(api_key=cfg.llm.api_key, base_url=cfg.llm.base_url)`. Model: `cfg.llm.model`.

System prompt = rules file content. User prompt = serialized sentences. Response = JSON with `deletes` array.

- [ ] **Step 1: Write failing tests**

```python
# tests/scripts/test_analyze_rough.py
import json, sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

REPO = "/Users/houyuxin/08Coding/podcast-cutter-skills"
sys.path.insert(0, f"{REPO}/shared/scripts")

def _sentences_json(tmp_path):
    ep = tmp_path / "ep01"
    td = ep / "1_transcribe"
    td.mkdir(parents=True)
    ad = ep / "2_analysis"
    ad.mkdir(parents=True)
    sents = {"sentences": [
        {"id": 0, "speaker": "S1", "start_ms": 0, "end_ms": 5000,
         "word_idx_start": 0, "word_idx_end": 10, "text": "这是录前闲聊内容"},
        {"id": 1, "speaker": "S1", "start_ms": 6000, "end_ms": 60000,
         "word_idx_start": 11, "word_idx_end": 200, "text": "正式内容开始了"},
    ]}
    (td / "sentences.json").write_text(json.dumps(sents))
    return ep

def test_rough_cuts_written(tmp_path, monkeypatch):
    ep = _sentences_json(tmp_path)
    fake_content = json.dumps({"deletes": [
        {"start_ms": 0, "end_ms": 5000, "level": "rough",
         "reason": "录前闲聊", "source": "ai_rough",
         "confidence": 0.9, "evidence_word_idx": [0, 10]}
    ]})
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = fake_content

    with patch("openai.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = mock_resp
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "analyze_rough", f"{REPO}/shared/scripts/analyze_rough.py")
        mod = importlib.util.module_from_spec(spec)
        sys.argv = ["analyze_rough.py", "--ep-dir", str(ep), "--env", f"{REPO}/.env"]
        spec.loader.exec_module(mod)

    cuts = json.loads((ep / "2_analysis" / "rough_cuts.json").read_text())
    assert len(cuts["deletes"]) == 1
    assert cuts["deletes"][0]["level"] == "rough"
    assert cuts["deletes"][0]["source"] == "ai_rough"

def test_rough_cuts_schema_validated(tmp_path, monkeypatch):
    """Invalid LLM response (missing required field) should raise."""
    ep = _sentences_json(tmp_path)
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = json.dumps({"deletes": [
        {"start_ms": 0, "end_ms": 5000}  # missing level/reason/source
    ]})
    with patch("openai.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = mock_resp
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "analyze_rough2", f"{REPO}/shared/scripts/analyze_rough.py")
        mod = importlib.util.module_from_spec(spec)
        sys.argv = ["analyze_rough.py", "--ep-dir", str(ep), "--env", f"{REPO}/.env"]
        with pytest.raises((ValueError, KeyError, SystemExit)):
            spec.loader.exec_module(mod)
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
python -m pytest tests/scripts/test_analyze_rough.py::test_rough_cuts_written -xvs 2>&1 | tail -20
```

- [ ] **Step 3: Implement analyze_rough.py**

```python
#!/usr/bin/env python3
"""Stage 2.1: LLM rough cut analysis → rough_cuts.json."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

def _repo_root() -> Path:
    return Path(__file__).parent.parent.parent

REQUIRED_DELETE_FIELDS = {"start_ms", "end_ms", "level", "reason", "source", "confidence"}

def _load_rules(rules_dir: Path) -> str:
    parts = []
    for md in sorted(rules_dir.glob("*.md")):
        parts.append(md.read_text())
    return "\n\n---\n\n".join(parts)

def _validate_deletes(deletes: list[dict]) -> None:
    for d in deletes:
        missing = REQUIRED_DELETE_FIELDS - set(d.keys())
        if missing:
            raise ValueError(f"Delete entry missing fields: {missing}. Got: {d}")
        if d.get("level") not in ("rough", "fine"):
            raise ValueError(f"Delete level must be 'rough' or 'fine', got: {d.get('level')}")

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep-dir", required=True)
    ap.add_argument("--env", default=None)
    ap.add_argument("--rules-dir", default=None)
    ap.add_argument("--user-prefs", default=None)
    args = ap.parse_args()

    repo = _repo_root()
    env_path = Path(args.env) if args.env else repo / ".env"
    rules_dir = Path(args.rules_dir) if args.rules_dir else repo / "shared/rules/editing"

    sys.path.insert(0, str(Path(__file__).parent))
    from lib.config import load
    import openai

    cfg = load(env_path)
    ep_dir = Path(args.ep_dir)
    td = ep_dir / "1_transcribe"
    ad = ep_dir / "2_analysis"
    ad.mkdir(parents=True, exist_ok=True)

    sentences = json.loads((td / "sentences.json").read_text())["sentences"]
    rules_text = _load_rules(rules_dir)

    system_prompt = f"""你是一个播客剪辑助手，负责粗剪分析。
根据以下剪辑规则，找出应该删除的片段（rough level）。

{rules_text}

输出严格的JSON，格式：
{{
  "deletes": [
    {{
      "start_ms": <整数毫秒>,
      "end_ms": <整数毫秒>,
      "level": "rough",
      "reason": "<删除原因>",
      "source": "ai_rough",
      "confidence": <0.0-1.0>,
      "evidence_word_idx": [<起始词idx>, <结束词idx>]
    }}
  ]
}}

只输出JSON，不要任何解释。"""

    user_prompt = f"以下是播客句子列表（按时间顺序）：\n\n{json.dumps(sentences, ensure_ascii=False, indent=2)}"

    client = openai.OpenAI(api_key=cfg.llm.api_key, base_url=cfg.llm.base_url)
    response = client.chat.completions.create(
        model=cfg.llm.model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
    )
    content = response.choices[0].message.content.strip()
    # strip markdown code fences if present
    if content.startswith("```"):
        content = "\n".join(content.split("\n")[1:])
        if content.endswith("```"):
            content = content[:-3]

    result = json.loads(content)
    _validate_deletes(result["deletes"])

    (ad / "rough_cuts.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"rough_cuts.json: {len(result['deletes'])} deletes")

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to confirm PASS**

```bash
python -m pytest tests/scripts/test_analyze_rough.py -xvs 2>&1 | tail -20
```

- [ ] **Step 5: Commit**

```bash
git add shared/scripts/analyze_rough.py tests/scripts/test_analyze_rough.py
git commit -m "feat: add analyze_rough.py (stage 2.1)"
```

---

### Task 8: analyze_fine.py

**Files:**
- Create: `shared/scripts/analyze_fine.py`
- Create: `tests/scripts/test_analyze_fine.py`

Nearly identical to analyze_rough.py, but:
- reads rough_cuts.json as additional context
- focuses on word-level filler (口头禅, 语气词)
- level = "fine", source = "ai_fine"
- output: fine_cuts.json

- [ ] **Step 1: Write failing tests**

```python
# tests/scripts/test_analyze_fine.py
import json, sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

REPO = "/Users/houyuxin/08Coding/podcast-cutter-skills"
sys.path.insert(0, f"{REPO}/shared/scripts")

def _setup_ep(tmp_path):
    ep = tmp_path / "ep01"
    td = ep / "1_transcribe"
    td.mkdir(parents=True)
    ad = ep / "2_analysis"
    ad.mkdir(parents=True)
    sents = {"sentences": [
        {"id": 0, "speaker": "S1", "start_ms": 0, "end_ms": 5000,
         "word_idx_start": 0, "word_idx_end": 5, "text": "嗯嗯嗯对对对"}
    ]}
    (td / "sentences.json").write_text(json.dumps(sents))
    words = {"words": [
        {"idx": i, "speaker": "S1", "start_ms": i*500, "end_ms": i*500+400,
         "text": c, "confidence": 0.9, "blank_after_ms": 0,
         "emotion": None, "lid": None}
        for i, c in enumerate(["嗯", "嗯", "嗯", "对", "对"])
    ], "episode_id": "ep01", "duration_ms": 5000,
       "source": {"tracks": ["t1.wav"], "mode": "single_track"},
       "speakers": [{"id": "S1", "name": None, "track": "t1.wav"}]}
    (td / "words.json").write_text(json.dumps(words))
    rough = {"deletes": []}
    (ad / "rough_cuts.json").write_text(json.dumps(rough))
    return ep

def test_fine_cuts_written(tmp_path):
    ep = _setup_ep(tmp_path)
    fake_content = json.dumps({"deletes": [
        {"start_ms": 0, "end_ms": 1500, "level": "fine",
         "reason": "重复语气词", "source": "ai_fine",
         "confidence": 0.85, "evidence_word_idx": [0, 2]}
    ]})
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = fake_content

    with patch("openai.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = mock_resp
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "analyze_fine", f"{REPO}/shared/scripts/analyze_fine.py")
        mod = importlib.util.module_from_spec(spec)
        sys.argv = ["analyze_fine.py", "--ep-dir", str(ep), "--env", f"{REPO}/.env"]
        spec.loader.exec_module(mod)

    cuts = json.loads((ep / "2_analysis" / "fine_cuts.json").read_text())
    assert cuts["deletes"][0]["level"] == "fine"
    assert cuts["deletes"][0]["source"] == "ai_fine"
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
python -m pytest tests/scripts/test_analyze_fine.py -xvs 2>&1 | tail -15
```

- [ ] **Step 3: Implement analyze_fine.py**

Same pattern as analyze_rough.py. Key differences:
- Also loads `words.json` for word-level context
- Also loads `rough_cuts.json` to know what's already marked rough
- level = "fine", source = "ai_fine"
- System prompt focuses on word-level filler, fillers, 口头禅

```python
#!/usr/bin/env python3
"""Stage 2.2: LLM fine cut analysis → fine_cuts.json."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

def _repo_root() -> Path:
    return Path(__file__).parent.parent.parent

REQUIRED_DELETE_FIELDS = {"start_ms", "end_ms", "level", "reason", "source", "confidence"}

def _load_rules(rules_dir: Path) -> str:
    return "\n\n---\n\n".join(md.read_text() for md in sorted(rules_dir.glob("*.md")))

def _validate_deletes(deletes: list[dict]) -> None:
    for d in deletes:
        missing = REQUIRED_DELETE_FIELDS - set(d.keys())
        if missing:
            raise ValueError(f"Delete entry missing fields: {missing}")
        if d.get("level") not in ("rough", "fine"):
            raise ValueError(f"Delete level must be 'rough' or 'fine'")

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep-dir", required=True)
    ap.add_argument("--env", default=None)
    ap.add_argument("--rules-dir", default=None)
    args = ap.parse_args()

    repo = _repo_root()
    env_path = Path(args.env) if args.env else repo / ".env"
    rules_dir = Path(args.rules_dir) if args.rules_dir else repo / "shared/rules/editing"

    sys.path.insert(0, str(Path(__file__).parent))
    from lib.config import load
    import openai

    cfg = load(env_path)
    ep_dir = Path(args.ep_dir)
    td = ep_dir / "1_transcribe"
    ad = ep_dir / "2_analysis"
    ad.mkdir(parents=True, exist_ok=True)

    sentences = json.loads((td / "sentences.json").read_text())["sentences"]
    words = json.loads((td / "words.json").read_text())["words"]
    rough = json.loads((ad / "rough_cuts.json").read_text())
    rules_text = _load_rules(rules_dir)

    system_prompt = f"""你是一个播客精剪助手，负责词级别的精剪分析。
粗剪已经标记了大段删除，现在需要找出剩余内容中的词级别口头禅、语气词等应删除的细节。

{rules_text}

已标记的粗剪区间（fine pass中请跳过这些区间内的内容）：
{json.dumps(rough['deletes'], ensure_ascii=False)}

输出严格的JSON，格式：
{{
  "deletes": [
    {{
      "start_ms": <整数毫秒>,
      "end_ms": <整数毫秒>,
      "level": "fine",
      "reason": "<删除原因>",
      "source": "ai_fine",
      "confidence": <0.0-1.0>,
      "evidence_word_idx": [<起始词idx>, <结束词idx>]
    }}
  ]
}}

只输出JSON，不要任何解释。"""

    user_prompt = (
        f"句子列表：\n{json.dumps(sentences, ensure_ascii=False, indent=2)}\n\n"
        f"词列表（前200个）：\n{json.dumps(words[:200], ensure_ascii=False, indent=2)}"
    )

    client = openai.OpenAI(api_key=cfg.llm.api_key, base_url=cfg.llm.base_url)
    response = client.chat.completions.create(
        model=cfg.llm.model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
    )
    content = response.choices[0].message.content.strip()
    if content.startswith("```"):
        content = "\n".join(content.split("\n")[1:])
        if content.endswith("```"):
            content = content[:-3]

    result = json.loads(content)
    _validate_deletes(result["deletes"])

    (ad / "fine_cuts.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"fine_cuts.json: {len(result['deletes'])} deletes")

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to confirm PASS**

```bash
python -m pytest tests/scripts/test_analyze_fine.py -xvs 2>&1 | tail -15
```

- [ ] **Step 5: Commit**

```bash
git add shared/scripts/analyze_fine.py tests/scripts/test_analyze_fine.py
git commit -m "feat: add analyze_fine.py (stage 2.2)"
```

---

### Task 9: self_review.py

**Files:**
- Create: `shared/scripts/self_review.py`
- Create: `tests/scripts/test_self_review.py`

CLI: `python self_review.py --ep-dir output/ep01 --env .env`
Reads rough_cuts.json + fine_cuts.json + sentences.json + rules.
Asks LLM to evaluate the proposed deletions: are they justified? Any false positives? Any missed cuts?
Writes `self_review.json` (same schema as rough_cuts.json but level="fine", source="self_review").

- [ ] **Step 1: Write failing tests**

```python
# tests/scripts/test_self_review.py
import json, sys
from pathlib import Path
from unittest.mock import patch, MagicMock

REPO = "/Users/houyuxin/08Coding/podcast-cutter-skills"
sys.path.insert(0, f"{REPO}/shared/scripts")

def _setup_ep(tmp_path):
    ep = tmp_path / "ep01"
    (ep / "1_transcribe").mkdir(parents=True)
    (ep / "2_analysis").mkdir(parents=True)
    sents = {"sentences": [{"id": 0, "speaker": "S1", "start_ms": 0,
              "end_ms": 5000, "word_idx_start": 0, "word_idx_end": 5, "text": "测试"}]}
    (ep / "1_transcribe" / "sentences.json").write_text(json.dumps(sents))
    (ep / "2_analysis" / "rough_cuts.json").write_text(json.dumps({"deletes": []}))
    (ep / "2_analysis" / "fine_cuts.json").write_text(json.dumps({"deletes": []}))
    return ep

def test_self_review_written(tmp_path):
    ep = _setup_ep(tmp_path)
    fake = json.dumps({"deletes": [], "flags": [], "summary": "No issues found."})
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = fake

    with patch("openai.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = mock_resp
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "self_review", f"{REPO}/shared/scripts/self_review.py")
        mod = importlib.util.module_from_spec(spec)
        sys.argv = ["self_review.py", "--ep-dir", str(ep), "--env", f"{REPO}/.env"]
        spec.loader.exec_module(mod)

    result = json.loads((ep / "2_analysis" / "self_review.json").read_text())
    assert "deletes" in result
    assert "summary" in result
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
python -m pytest tests/scripts/test_self_review.py -xvs 2>&1 | tail -15
```

- [ ] **Step 3: Implement self_review.py**

```python
#!/usr/bin/env python3
"""Stage 2.3: LLM self-review of rough+fine cuts → self_review.json."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

def _repo_root() -> Path:
    return Path(__file__).parent.parent.parent

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep-dir", required=True)
    ap.add_argument("--env", default=None)
    args = ap.parse_args()

    repo = _repo_root()
    env_path = Path(args.env) if args.env else repo / ".env"
    sys.path.insert(0, str(Path(__file__).parent))
    from lib.config import load
    import openai

    cfg = load(env_path)
    ep_dir = Path(args.ep_dir)
    td = ep_dir / "1_transcribe"
    ad = ep_dir / "2_analysis"

    sentences = json.loads((td / "sentences.json").read_text())["sentences"]
    rough = json.loads((ad / "rough_cuts.json").read_text())
    fine = json.loads((ad / "fine_cuts.json").read_text())

    system_prompt = """你是一个严格的播客剪辑质检员，负责审查AI提出的剪辑建议。
请评估rough_cuts和fine_cuts中的每个删除建议：
1. 是否有误删（false positive）—— 不该删的被删了？
2. 是否有遗漏（false negative）—— 应该删的没删？
3. 给出综合评估

输出JSON格式：
{
  "deletes": [  // 补充建议删除但之前遗漏的（source="self_review"，level="fine"）
    {"start_ms": <ms>, "end_ms": <ms>, "level": "fine",
     "reason": "<reason>", "source": "self_review", "confidence": <0-1>,
     "evidence_word_idx": [start, end]}
  ],
  "flags": [  // 建议取消的删除
    {"start_ms": <ms>, "end_ms": <ms>, "flag": "false_positive", "reason": "<reason>"}
  ],
  "summary": "<总体评估，1-3句>"
}
只输出JSON。"""

    user_prompt = (
        f"句子列表：\n{json.dumps(sentences, ensure_ascii=False, indent=2)}\n\n"
        f"粗剪建议：\n{json.dumps(rough['deletes'], ensure_ascii=False)}\n\n"
        f"精剪建议：\n{json.dumps(fine['deletes'], ensure_ascii=False)}"
    )

    client = openai.OpenAI(api_key=cfg.llm.api_key, base_url=cfg.llm.base_url)
    response = client.chat.completions.create(
        model=cfg.llm.model,
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": user_prompt}],
        temperature=0.1,
    )
    content = response.choices[0].message.content.strip()
    if content.startswith("```"):
        content = "\n".join(content.split("\n")[1:])
        if content.endswith("```"):
            content = content[:-3]

    result = json.loads(content)
    (ad / "self_review.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"self_review.json written. Summary: {result.get('summary','')}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to confirm PASS**

```bash
python -m pytest tests/scripts/test_self_review.py -xvs 2>&1 | tail -15
```

- [ ] **Step 5: Commit**

```bash
git add shared/scripts/self_review.py tests/scripts/test_self_review.py
git commit -m "feat: add self_review.py (stage 2.3)"
```

---

### Task 10: generate_review_html.py and review_server.py

**Files:**
- Create: `shared/scripts/generate_review_html.py`
- Create: `shared/scripts/review_server.py`
- Create: `shared/templates/review_enhanced.html`
- Create: `tests/scripts/test_review_server.py`

`generate_review_html.py`: reads sentences.json, words.json, rough_cuts.json, fine_cuts.json, self_review.json; writes `3_review/review_enhanced.html` by filling `shared/templates/review_enhanced.html`.

`review_server.py`: Flask app. `GET /state` returns review_state.json. `PATCH /state` updates it (user edits). `POST /export` writes delete_segments_edited.json.

- [ ] **Step 1: Write failing tests**

```python
# tests/scripts/test_review_server.py
import json, sys
from pathlib import Path
import pytest

REPO = "/Users/houyuxin/08Coding/podcast-cutter-skills"
sys.path.insert(0, f"{REPO}/shared/scripts")

def _setup_ep(tmp_path):
    ep = tmp_path / "ep01"
    rev = ep / "3_review"
    rev.mkdir(parents=True)
    state = {"deletes": [
        {"start_ms": 0, "end_ms": 5000, "level": "rough",
         "reason": "test", "source": "ai_rough", "user_action": "kept"}
    ]}
    (rev / "review_state.json").write_text(json.dumps(state))
    return ep

def test_get_state(tmp_path):
    ep = _setup_ep(tmp_path)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "review_server", f"{REPO}/shared/scripts/review_server.py")
    mod = importlib.util.module_from_spec(spec)
    sys.argv = ["review_server.py", "--ep-dir", str(ep), "--no-serve"]
    spec.loader.exec_module(mod)

    client = mod.app.test_client()
    resp = client.get("/state")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "deletes" in data

def test_patch_state(tmp_path):
    ep = _setup_ep(tmp_path)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "review_server2", f"{REPO}/shared/scripts/review_server.py")
    mod = importlib.util.module_from_spec(spec)
    sys.argv = ["review_server.py", "--ep-dir", str(ep), "--no-serve"]
    spec.loader.exec_module(mod)

    client = mod.app.test_client()
    new_state = {"deletes": [
        {"start_ms": 0, "end_ms": 5000, "level": "rough",
         "reason": "test", "source": "ai_rough", "user_action": "rejected_by_user"}
    ]}
    resp = client.patch("/state", json=new_state)
    assert resp.status_code == 200
    saved = json.loads((ep / "3_review" / "review_state.json").read_text())
    assert saved["deletes"][0]["user_action"] == "rejected_by_user"

def test_export_creates_delete_segments(tmp_path):
    ep = _setup_ep(tmp_path)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "review_server3", f"{REPO}/shared/scripts/review_server.py")
    mod = importlib.util.module_from_spec(spec)
    sys.argv = ["review_server.py", "--ep-dir", str(ep), "--no-serve"]
    spec.loader.exec_module(mod)

    client = mod.app.test_client()
    resp = client.post("/export", json={"user_notes": "test notes", "feedback_for_learning": []})
    assert resp.status_code == 200
    exported = json.loads((ep / "3_review" / "delete_segments_edited.json").read_text())
    assert "deletes" in exported
    assert exported["user_notes"] == "test notes"
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
python -m pytest tests/scripts/test_review_server.py -xvs 2>&1 | tail -15
```

- [ ] **Step 3: Implement review_server.py**

```python
#!/usr/bin/env python3
"""Stage 3.0: Flask server for file-backed review state."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

from flask import Flask, jsonify, request

app = Flask(__name__)
_ep_dir: Path = Path(".")

@app.route("/state", methods=["GET"])
def get_state():
    state_file = _ep_dir / "3_review" / "review_state.json"
    if not state_file.exists():
        return jsonify({"deletes": []}), 200
    return jsonify(json.loads(state_file.read_text())), 200

@app.route("/state", methods=["PATCH"])
def patch_state():
    data = request.get_json()
    state_file = _ep_dir / "3_review" / "review_state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return jsonify({"ok": True}), 200

@app.route("/export", methods=["POST"])
def export():
    body = request.get_json() or {}
    state_file = _ep_dir / "3_review" / "review_state.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else {"deletes": []}
    out = {
        "deletes": state["deletes"],
        "user_notes": body.get("user_notes", ""),
        "feedback_for_learning": body.get("feedback_for_learning", []),
    }
    out_file = _ep_dir / "3_review" / "delete_segments_edited.json"
    out_file.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    return jsonify({"ok": True, "path": str(out_file)}), 200

def main() -> None:
    global _ep_dir
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep-dir", required=True)
    ap.add_argument("--port", type=int, default=5050)
    ap.add_argument("--no-serve", action="store_true", help="init only, no server start (for tests)")
    args = ap.parse_args()
    _ep_dir = Path(args.ep_dir)
    if not args.no_serve:
        app.run(host="127.0.0.1", port=args.port, debug=False)

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Implement generate_review_html.py (simple HTML output)**

```python
#!/usr/bin/env python3
"""Stage 3.0: Generate review_enhanced.html for human review."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def _repo_root() -> Path:
    return Path(__file__).parent.parent.parent

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh">
<head><meta charset="UTF-8"><title>播客剪辑审查</title>
<style>
body { font-family: sans-serif; max-width: 900px; margin: 2em auto; }
.delete { background: #ffe0e0; border-left: 4px solid #c00; padding: 8px; margin: 8px 0; }
.sentence { padding: 4px 0; border-bottom: 1px solid #eee; }
.timestamp { color: #888; font-size: 0.85em; }
.speaker { font-weight: bold; margin-right: 8px; }
button { margin: 4px; padding: 6px 14px; cursor: pointer; }
</style>
</head>
<body>
<h1>播客剪辑审查</h1>
<p>Episode: <strong>{episode_id}</strong> | 句子数: {sent_count} | 建议删除: {delete_count}</p>
<h2>删除建议</h2>
{delete_html}
<h2>完整文本</h2>
{transcript_html}
<script>
const SERVER = 'http://127.0.0.1:5050';
async function getState() {{
  const r = await fetch(SERVER + '/state'); return r.json();
}}
async function patchState(state) {{
  await fetch(SERVER + '/state', {{method:'PATCH', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify(state)}});
}}
</script>
</body></html>"""

def _ms_to_ts(ms: int) -> str:
    s = ms // 1000
    return f"{s//60:02d}:{s%60:02d}"

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep-dir", required=True)
    args = ap.parse_args()

    ep_dir = Path(args.ep_dir)
    td = ep_dir / "1_transcribe"
    ad = ep_dir / "2_analysis"
    rd = ep_dir / "3_review"
    rd.mkdir(parents=True, exist_ok=True)

    sentences = json.loads((td / "sentences.json").read_text())["sentences"]
    rough = json.loads((ad / "rough_cuts.json").read_text())["deletes"]
    fine = json.loads((ad / "fine_cuts.json").read_text())["deletes"]
    sr = json.loads((ad / "self_review.json").read_text()) if (ad / "self_review.json").exists() else {}
    all_deletes = rough + fine + sr.get("deletes", [])

    delete_html = ""
    for d in all_deletes:
        delete_html += (
            f'<div class="delete">'
            f'[{_ms_to_ts(d["start_ms"])} - {_ms_to_ts(d["end_ms"])}] '
            f'<b>{d["level"]}</b> ({d["source"]}, conf={d.get("confidence","?"):.2f}): '
            f'{d["reason"]}'
            f'</div>\n'
        )

    transcript_html = ""
    for s in sentences:
        transcript_html += (
            f'<div class="sentence">'
            f'<span class="speaker">{s["speaker"]}</span>'
            f'<span class="timestamp">{_ms_to_ts(s["start_ms"])}</span> '
            f'{s["text"]}'
            f'</div>\n'
        )

    html = HTML_TEMPLATE.format(
        episode_id=ep_dir.name,
        sent_count=len(sentences),
        delete_count=len(all_deletes),
        delete_html=delete_html,
        transcript_html=transcript_html,
    )
    (rd / "review_enhanced.html").write_text(html, encoding="utf-8")
    print(f"review_enhanced.html written ({len(sentences)} sentences, {len(all_deletes)} deletes)")

    # initialize review_state.json from all deletes
    state_file = rd / "review_state.json"
    if not state_file.exists():
        state_deletes = [{**d, "user_action": "kept"} for d in all_deletes]
        state_file.write_text(json.dumps({"deletes": state_deletes}, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to confirm PASS**

```bash
python -m pytest tests/scripts/test_review_server.py -xvs 2>&1 | tail -20
```

- [ ] **Step 6: Commit**

```bash
git add shared/scripts/generate_review_html.py shared/scripts/review_server.py tests/scripts/test_review_server.py
git commit -m "feat: add generate_review_html.py and review_server.py (stage 3.0)"
```

---

### Task 11: cut_audio.py

**Files:**
- Create: `shared/scripts/cut_audio.py`
- Create: `tests/scripts/test_cut_audio.py`

CLI: `python cut_audio.py --ep-dir output/ep01`
Reads: `input/working_track1.wav` (or merged), `3_review/delete_segments_edited.json`, `input/audio_meta.json`
Computes KEEP ranges = `[0, duration_ms] - merge(deletes)`, splices with 25ms acrossfade.
Output: `4_cut/cut.wav`. Verifies `max_volume > -10 dB` via `ffmpeg_wrap.volumedetect_max_db`.

- [ ] **Step 1: Write failing tests**

```python
# tests/scripts/test_cut_audio.py
import json, subprocess
from pathlib import Path
import pytest

REPO = "/Users/houyuxin/08Coding/podcast-cutter-skills"

@pytest.fixture
def tiny_wav(tmp_path):
    out = tmp_path / "track.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=10",
         "-af", "volume=4", "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(out)],
        check=True, capture_output=True
    )
    return out

def _setup_ep(tmp_path, wav, deletes):
    ep = tmp_path / "ep01"
    (ep / "input").mkdir(parents=True)
    (ep / "3_review").mkdir(parents=True)
    (ep / "4_cut").mkdir(parents=True)
    import shutil
    shutil.copy(wav, ep / "input" / "working_track1.wav")
    meta = {"episode_id": "ep01", "mode": "single_track",
            "tracks": [{"file": "working_track1.wav", "duration_ms": 10000, "sample_rate": 44100}],
            "total_duration_ms": 10000}
    (ep / "input" / "audio_meta.json").write_text(json.dumps(meta))
    edited = {"deletes": deletes, "user_notes": "", "feedback_for_learning": []}
    (ep / "3_review" / "delete_segments_edited.json").write_text(json.dumps(edited))
    return ep

def test_cut_no_deletes_full_audio(tiny_wav, tmp_path):
    ep = _setup_ep(tmp_path, tiny_wav, [])
    subprocess.run(
        ["python", "shared/scripts/cut_audio.py", "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO
    )
    cut = ep / "4_cut" / "cut.wav"
    assert cut.exists()
    # duration should be ~10s
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(cut)],
        capture_output=True, text=True, check=True
    )
    assert float(r.stdout.strip()) > 8.0

def test_cut_delete_first_2s(tiny_wav, tmp_path):
    ep = _setup_ep(tmp_path, tiny_wav, [
        {"start_ms": 0, "end_ms": 2000, "level": "rough",
         "reason": "test", "source": "ai_rough", "user_action": "kept"}
    ])
    subprocess.run(
        ["python", "shared/scripts/cut_audio.py", "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO
    )
    cut = ep / "4_cut" / "cut.wav"
    assert cut.exists()
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(cut)],
        capture_output=True, text=True, check=True
    )
    assert float(r.stdout.strip()) < 9.0  # shorter than original
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
python -m pytest tests/scripts/test_cut_audio.py -xvs 2>&1 | tail -15
```

- [ ] **Step 3: Implement cut_audio.py**

```python
#!/usr/bin/env python3
"""Stage 4.0: delete_segments_edited.json → cut.wav (25ms acrossfade per splice)."""
from __future__ import annotations
import argparse, json, subprocess, tempfile, shutil
from pathlib import Path

XFADE_MS = 25

def _repo_root() -> Path:
    return Path(__file__).parent.parent.parent

def _merge_deletes(deletes: list[dict]) -> list[tuple[int, int]]:
    """Merge overlapping/adjacent delete intervals."""
    intervals = sorted((d["start_ms"], d["end_ms"]) for d in deletes)
    merged = []
    for s, e in intervals:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged

def _keep_ranges(duration_ms: int, deletes: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Invert delete ranges to get keep ranges."""
    keeps = []
    cur = 0
    for s, e in deletes:
        if cur < s:
            keeps.append((cur, s))
        cur = max(cur, e)
    if cur < duration_ms:
        keeps.append((cur, duration_ms))
    return keeps

def _ms_to_sec(ms: int) -> float:
    return ms / 1000.0

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep-dir", required=True)
    ap.add_argument("--track-num", type=int, default=1)
    args = ap.parse_args()

    sys.path_insert = None
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from lib.ffmpeg_wrap import run_ffmpeg, volumedetect_max_db
    from lib.audio_constants import SPLICE_XFADE_MS, MIN_OUTPUT_PEAK_DB

    ep_dir = Path(args.ep_dir)
    in_dir = ep_dir / "input"
    meta = json.loads((in_dir / "audio_meta.json").read_text())
    duration_ms = meta["total_duration_ms"]

    track_file = in_dir / f"working_track{args.track_num}.wav"
    edited = json.loads((ep_dir / "3_review" / "delete_segments_edited.json").read_text())
    # only include deletes user kept or edited (not rejected_by_user)
    active_deletes = [d for d in edited["deletes"] if d.get("user_action") != "rejected_by_user"]
    merged = _merge_deletes(active_deletes)
    keeps = _keep_ranges(duration_ms, merged)

    out_dir = ep_dir / "4_cut"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "cut.wav"
    log_dir = out_dir / "logs"
    log_dir.mkdir(exist_ok=True)

    if not keeps:
        raise ValueError("No audio kept after applying deletes")

    if len(keeps) == 1:
        s, e = keeps[0]
        run_ffmpeg(
            ["-y", "-i", str(track_file),
             "-ss", str(_ms_to_sec(s)), "-to", str(_ms_to_sec(e)),
             "-c:a", "pcm_s16le", str(out_file)],
            log_path=log_dir / "cut.log"
        )
    else:
        xfade_s = SPLICE_XFADE_MS / 1000.0
        with tempfile.TemporaryDirectory() as td:
            # extract each keep segment
            segments = []
            for i, (s, e) in enumerate(keeps):
                seg = Path(td) / f"seg{i:04d}.wav"
                subprocess.run(
                    ["ffmpeg", "-y", "-i", str(track_file),
                     "-ss", str(_ms_to_sec(s)), "-to", str(_ms_to_sec(e)),
                     "-c:a", "pcm_s16le", str(seg)],
                    check=True, capture_output=True
                )
                segments.append(seg)

            # build filter_complex with acrossfade
            inputs = "".join(f"[{i}:a]" for i in range(len(segments)))
            # chain acrossfade: [0][1]acrossfade=d=...[a01]; [a01][2]acrossfade=...[a012]; ...
            fc_parts = []
            prev_label = "[0:a]"
            for i in range(1, len(segments)):
                out_label = f"[a{i}]"
                fc_parts.append(
                    f"{prev_label}[{i}:a]acrossfade=d={xfade_s}:c1=tri:c2=tri{out_label}"
                )
                prev_label = out_label

            filter_complex = ";".join(fc_parts)
            cmd = ["-y"]
            for seg in segments:
                cmd.extend(["-i", str(seg)])
            cmd.extend([
                "-filter_complex", filter_complex,
                "-map", prev_label,
                "-c:a", "pcm_s16le", str(out_file)
            ])
            run_ffmpeg(cmd, log_path=log_dir / "cut.log")

    peak = volumedetect_max_db(out_file)
    if peak <= MIN_OUTPUT_PEAK_DB:
        raise RuntimeError(f"cut.wav peak {peak:.1f} dB ≤ {MIN_OUTPUT_PEAK_DB} dB (silence trap)")
    print(f"cut.wav: {len(keeps)} segments, peak={peak:.1f} dB")

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to confirm PASS**

```bash
python -m pytest tests/scripts/test_cut_audio.py -xvs 2>&1 | tail -20
```

- [ ] **Step 5: Commit**

```bash
git add shared/scripts/cut_audio.py tests/scripts/test_cut_audio.py
git commit -m "feat: add cut_audio.py (stage 4.0, 25ms acrossfade)"
```

---

### Task 12: trim_silences.py

**Files:**
- Create: `shared/scripts/trim_silences.py`
- Create: `tests/scripts/test_trim_silences.py`

CLI: `python trim_silences.py --ep-dir output/ep01`
Reads `4_cut/cut.wav`. Trims leading and trailing silence to 200ms max. Overwrites `4_cut/cut.wav`.

Strategy: use ffmpeg `silencedetect` to find silence start/end, then trim with `-ss`/`-to`. Always leave at least 200ms of audio at head and tail.

- [ ] **Step 1: Write failing tests**

```python
# tests/scripts/test_trim_silences.py
import subprocess, shutil
from pathlib import Path
import pytest

REPO = "/Users/houyuxin/08Coding/podcast-cutter-skills"

@pytest.fixture
def silence_then_tone(tmp_path):
    """2s silence + 5s tone + 2s silence."""
    out = tmp_path / "cut.wav"
    subprocess.run(
        ["ffmpeg", "-y",
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
         "-filter_complex",
         "[0:a]atrim=duration=2[s0];[2:a]atrim=duration=2[s2];[s0][1:a][s2]concat=n=3:v=0:a=1,volume=4[out]",
         "-map", "[out]", "-c:a", "pcm_s16le", str(out)],
        check=True, capture_output=True
    )
    return out

def test_trim_removes_head_tail_silence(silence_then_tone, tmp_path):
    ep = tmp_path / "ep01"
    cut_dir = ep / "4_cut"
    cut_dir.mkdir(parents=True)
    shutil.copy(silence_then_tone, cut_dir / "cut.wav")

    subprocess.run(
        ["python", "shared/scripts/trim_silences.py", "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO
    )
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(cut_dir / "cut.wav")],
        capture_output=True, text=True, check=True
    )
    dur = float(r.stdout.strip())
    assert dur < 7.0  # was 9s, now shorter (silence trimmed)
    assert dur > 5.0  # but tone preserved
```

- [ ] **Step 2: Run to confirm FAIL**

```bash
python -m pytest tests/scripts/test_trim_silences.py -xvs 2>&1 | tail -15
```

- [ ] **Step 3: Implement trim_silences.py**

```python
#!/usr/bin/env python3
"""Stage 4.1: trim head/tail silence to 200ms. Overwrites cut.wav."""
from __future__ import annotations
import argparse, re, shutil, subprocess, tempfile
from pathlib import Path

TRIM_HEAD_TAIL_MS = 200

def _detect_silence_edges(wav: Path) -> tuple[float, float]:
    """Return (first_nonsilent_sec, last_nonsilent_sec) in the file."""
    r = subprocess.run(
        ["ffmpeg", "-i", str(wav), "-af", "silencedetect=n=-50dB:d=0.1",
         "-f", "null", "-"],
        capture_output=True, text=True
    )
    stderr = r.stderr
    silence_starts = [float(m) for m in re.findall(r"silence_start: ([\d.]+)", stderr)]
    silence_ends = [float(m) for m in re.findall(r"silence_end: ([\d.]+)", stderr)]

    r2 = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(wav)],
        capture_output=True, text=True, check=True
    )
    total_dur = float(r2.stdout.strip())

    start_trim = 0.0
    if silence_starts and silence_starts[0] < 0.1 and silence_ends:
        start_trim = max(0.0, silence_ends[0] - TRIM_HEAD_TAIL_MS / 1000.0)

    end_trim = total_dur
    if silence_starts and silence_starts[-1] > total_dur - 3.0:
        end_trim = min(total_dur, silence_starts[-1] + TRIM_HEAD_TAIL_MS / 1000.0)

    return start_trim, end_trim

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep-dir", required=True)
    args = ap.parse_args()

    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from lib.ffmpeg_wrap import run_ffmpeg, volumedetect_max_db
    from lib.audio_constants import MIN_OUTPUT_PEAK_DB

    ep_dir = Path(args.ep_dir)
    cut_wav = ep_dir / "4_cut" / "cut.wav"
    if not cut_wav.exists():
        raise FileNotFoundError(f"{cut_wav} not found")

    start_s, end_s = _detect_silence_edges(cut_wav)
    log_dir = ep_dir / "4_cut" / "logs"
    log_dir.mkdir(exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        tmp = Path(tf.name)

    run_ffmpeg(
        ["-y", "-i", str(cut_wav),
         "-ss", str(start_s), "-to", str(end_s),
         "-c:a", "pcm_s16le", str(tmp)],
        log_path=log_dir / "trim.log"
    )
    shutil.move(str(tmp), str(cut_wav))

    peak = volumedetect_max_db(cut_wav)
    if peak <= MIN_OUTPUT_PEAK_DB:
        raise RuntimeError(f"trim_silences: output peak {peak:.1f} dB too low")
    print(f"trim_silences: trimmed to [{start_s:.2f}s, {end_s:.2f}s], peak={peak:.1f} dB")

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to confirm PASS**

```bash
python -m pytest tests/scripts/test_trim_silences.py -xvs 2>&1 | tail -15
```

- [ ] **Step 5: Commit**

```bash
git add shared/scripts/trim_silences.py tests/scripts/test_trim_silences.py
git commit -m "feat: add trim_silences.py (stage 4.1)"
```

---

### Task 13: SKILL.md + docs + CHANGELOG

**Files:**
- Create: `.claude/skills/podcast-cut-剪播客/SKILL.md`
- Create: `docs/剪播客/阶段1-转录.md`
- Create: `docs/剪播客/阶段2-分析.md`
- Create: `docs/剪播客/阶段3-审查.md`
- Create: `docs/剪播客/阶段4-剪辑.md`
- Modify: `CHANGELOG.md`

No tests needed. Create and commit.

- [ ] **Step 1: Create SKILL.md**

`.claude/skills/podcast-cut-剪播客/SKILL.md`:
```markdown
# /podcast-cut-剪播客

将原始录音转录、分析、审查并剪成 cut.wav。

## 用法

```
/podcast-cut-剪播客 --track1 recordings/track1.wav [--track2 recordings/track2.wav] --ep-id 2026-05-08-ep01
```

## 流程（stages 1–4）

| 阶段 | 脚本 | 输出 |
|---|---|---|
| 1.0 prepare | `prepare_audio.py` | `input/working_track*.wav`, `audio_meta.json` |
| 1.1 upload | `lib/upload.py` | 音频URL |
| 1.2 ASR | `volcano_submit.py` + `volcano_query.py` | `volcano_raw_track*.json` |
| 1.3 merge | `transcribe_merge.py` | `words.json` |
| 1.4 sentences | `make_sentences.py` | `sentences.json` |
| 2.1 rough | `analyze_rough.py` | `rough_cuts.json` |
| 2.2 fine | `analyze_fine.py` | `fine_cuts.json` |
| 2.3 self-review | `self_review.py` | `self_review.json` |
| 3.0 review | `generate_review_html.py` + `review_server.py` | `review_enhanced.html` |
| 3.1 export | (手动) | `delete_segments_edited.json` |
| 4.0 cut | `cut_audio.py` | `cut.wav` |
| 4.1 trim | `trim_silences.py` | `cut.wav`（覆盖写） |

## 前提

- 已运行 `/podcast-cut-安装`
- `.env` 已配置（VOLC_API_KEY 或 VOLC_APP_KEY+VOLC_ACCESS_KEY；LLM_API_KEY/BASE_URL/MODEL）

## 各阶段详情

- [阶段1 转录](../../docs/剪播客/阶段1-转录.md)
- [阶段2 分析](../../docs/剪播客/阶段2-分析.md)
- [阶段3 审查](../../docs/剪播客/阶段3-审查.md)
- [阶段4 剪辑](../../docs/剪播客/阶段4-剪辑.md)
```

- [ ] **Step 2: Create stage docs**

`docs/剪播客/阶段1-转录.md`: Brief description of prepare_audio → upload → volcano_submit → volcano_query → transcribe_merge → make_sentences. Include words.json and sentences.json schema references. Error codes: Volcano 4xxx = bad key, 5xxx = server error, retry with backoff.

`docs/剪播客/阶段2-分析.md`: LLM analysis flow. Rules loading from `shared/rules/editing/`. Output schemas for rough_cuts.json, fine_cuts.json, self_review.json.

`docs/剪播客/阶段3-审查.md`: review_server.py usage. Open review_enhanced.html in browser. Edit deletes. POST /export to write delete_segments_edited.json.

`docs/剪播客/阶段4-剪辑.md`: cut_audio.py logic: KEEP-ranges = [0, duration] - merge(deletes). 25ms acrossfade. trim_silences.py head/tail 200ms. volumedetect guard (-10 dB threshold).

- [ ] **Step 3: Update CHANGELOG.md**

Add at top:
```markdown
## [0.2.0] — 2026-05-08

### Added
- `prepare_audio.py`: stage 1.0 audio preparation (mono WAV + audio_meta.json)
- `volcano_submit.py` + `volcano_query.py`: stage 1.2 Volcano v3 AUC ASR
- `transcribe_merge.py`: stage 1.3 raw JSON → words.json (2-track merge)
- `make_sentences.py`: stage 1.4 words.json → sentences.json
- `analyze_rough.py`: stage 2.1 LLM rough cuts (doubao/Ark)
- `analyze_fine.py`: stage 2.2 LLM fine cuts
- `self_review.py`: stage 2.3 LLM self-review
- `generate_review_html.py` + `review_server.py`: stage 3.0 review HTML + Flask server
- `cut_audio.py`: stage 4.0 sample-accurate splice with 25ms acrossfade
- `trim_silences.py`: stage 4.1 head/tail silence trim (200ms)
- `.claude/skills/podcast-cut-剪播客/SKILL.md`: skill definition
- `shared/rules/editing/` + `shared/rules/users/default/`: editing rules and user prefs
- `LLMConfig` added to `lib/config.py`; `openai` and `flask` added to dependencies
```

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/podcast-cut-剪播客/ docs/剪播客/ CHANGELOG.md
git commit -m "docs: add podcast-cut-剪播客 SKILL.md, stage docs, CHANGELOG v0.2.0"
```

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest tests/ -x --tb=short 2>&1 | tail -30
```

Expected: all tests green

- [ ] **Step 6: Tag and push**

```bash
git tag v0.2.0
git push origin main --tags
```
