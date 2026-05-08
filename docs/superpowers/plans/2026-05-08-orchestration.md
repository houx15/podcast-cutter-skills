# Orchestration Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the podcast-cutter pipeline into a single callable skill: two commands (`run_pipeline.py` + `--resume`) replace 12 manual script invocations, and the skill SKILL.md is updated to match.

**Architecture:** `run_pipeline.py` orchestrates all stages in sequence, using subprocess for isolation. Each stage is skipped if its output already exists (idempotency). `volcano_submit.py` gains `--audio-file` to handle upload internally. SKILL.md is rewritten to show the two-command interface. A mirror skill is added for Codex.

**Tech Stack:** Python 3.10+, subprocess, existing `lib/upload.select_uploader`, existing per-stage scripts unchanged except `volcano_submit.py`.

---

## File Structure

- Create: `shared/scripts/run_pipeline.py` — orchestrates all stages
- Modify: `shared/scripts/volcano_submit.py` — add `--audio-file` (upload internally, then submit)
- Create: `tests/scripts/test_run_pipeline.py` — 4 tests
- Modify: `tests/scripts/test_volcano_scripts.py` — add test for `--audio-file`
- Modify: `.claude/skills/podcast-cut-剪播客/SKILL.md` — rewrite to two-command interface
- Create: `.codex/skills/podcast-cut-剪播客/SKILL.md` — Codex mirror

---

## Task 1: `volcano_submit.py` — add `--audio-file` with internal upload

**Files:**
- Modify: `shared/scripts/volcano_submit.py`
- Modify: `tests/scripts/test_volcano_scripts.py`

The upload gap: `volcano_submit.py` requires `--audio-url` but `run_pipeline.py` needs to pass a local file. Fix: add `--audio-file`; when given, call `lib.upload.select_uploader(cfg).upload(path)` to get the URL, then proceed as before. `--audio-url` still works for manual use. Exactly one of the two must be provided.

- [ ] **Step 1: Write the failing test**

Add to `tests/scripts/test_volcano_scripts.py` (read the file first — follow the existing importlib + `unittest.mock.patch` pattern):

```python
def test_submit_with_audio_file(tmp_path):
    """--audio-file triggers upload and uses returned URL for submission."""
    import importlib.util, sys, json, unittest.mock
    from pathlib import Path

    SCRIPTS = Path(__file__).resolve().parents[2] / "shared" / "scripts"
    spec = importlib.util.spec_from_file_location("volcano_submit", SCRIPTS / "volcano_submit.py")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS))
    spec.loader.exec_module(mod)

    ep_dir = tmp_path / "ep"
    audio_file = tmp_path / "track1.wav"
    audio_file.write_bytes(b"RIFF" + b"\x00" * 40)  # minimal non-empty file

    fake_url = "https://example.com/track1.wav"
    fake_task_id = "task-abc-123"
    fake_resp = {"resp": {"task_id": fake_task_id}}

    with unittest.mock.patch("sys.argv", [
        "volcano_submit.py",
        "--audio-file", str(audio_file),
        "--ep-dir", str(ep_dir),
        "--track-num", "1",
    ]):
        with unittest.mock.patch("requests.post") as mock_post, \
             unittest.mock.patch("shared.scripts.lib.upload.select_uploader") as mock_up:
            mock_up.return_value.upload.return_value = fake_url
            mock_post.return_value.status_code = 200
            mock_post.return_value.raise_for_status = lambda: None
            mock_post.return_value.json.return_value = fake_resp
            mod.main()

    # upload was called with the audio file path
    mock_up.return_value.upload.assert_called_once()
    called_path = mock_up.return_value.upload.call_args[0][0]
    assert Path(called_path) == audio_file

    # task_id was written
    task_id_file = ep_dir / "1_transcribe" / "task_id_track1.txt"
    assert task_id_file.exists()
    assert task_id_file.read_text().strip() == fake_task_id
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/scripts/test_volcano_scripts.py::test_submit_with_audio_file -v
```

Expected: FAIL — `--audio-file` not recognised yet.

- [ ] **Step 3: Update `volcano_submit.py`**

Replace:
```python
ap.add_argument("--audio-url", required=True)
```

With:
```python
ap.add_argument("--audio-url", default=None, help="Pre-uploaded audio URL.")
ap.add_argument("--audio-file", default=None, help="Local audio file; pipeline uploads it automatically.")
```

After `cfg = load(env_path)`, add:
```python
    if args.audio_url and args.audio_file:
        ap.error("Provide --audio-url or --audio-file, not both.")
    if args.audio_url:
        audio_url = args.audio_url
    elif args.audio_file:
        from lib.upload import select_uploader
        audio_url = select_uploader(cfg).upload(Path(args.audio_file))
    else:
        ap.error("Either --audio-url or --audio-file is required.")
```

Replace every subsequent reference to `args.audio_url` with `audio_url`.

Full updated `main()`:
```python
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio-url", default=None, help="Pre-uploaded audio URL.")
    ap.add_argument("--audio-file", default=None, help="Local audio file; uploaded automatically.")
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
    data = resp.json()
    try:
        returned_task_id = data["resp"]["task_id"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError(f"Volcano submit response missing 'task_id': {data}") from exc

    ep_dir = Path(args.ep_dir)
    out_dir = ep_dir / "1_transcribe"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"task_id_track{args.track_num}.txt").write_text(returned_task_id)
    print(returned_task_id)
```

- [ ] **Step 4: Run all volcano tests**

```bash
python -m pytest tests/scripts/test_volcano_scripts.py -v
```

Expected: all tests pass (existing + new).

- [ ] **Step 5: Full suite**

```bash
python -m pytest tests/ -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add shared/scripts/volcano_submit.py tests/scripts/test_volcano_scripts.py
git commit -m "feat: volcano_submit --audio-file uploads and submits in one step"
```

---

## Task 2: `run_pipeline.py`

**Files:**
- Create: `shared/scripts/run_pipeline.py`
- Create: `tests/scripts/test_run_pipeline.py`

The orchestrator runs stages in order, skips stages whose output already exists, pauses at stage 3 with a clear message, and resumes at stage 4 via `--resume`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/scripts/test_run_pipeline.py
from __future__ import annotations
import importlib.util, json, sys, unittest.mock
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load():
    spec = importlib.util.spec_from_file_location("run_pipeline", SCRIPTS / "run_pipeline.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _meta(ep_dir: Path, n_tracks: int = 1) -> None:
    in_dir = ep_dir / "input"
    in_dir.mkdir(parents=True, exist_ok=True)
    tracks = [{"file": f"working_track{i}.wav", "duration_ms": 60000, "sample_rate": 44100}
              for i in range(1, n_tracks + 1)]
    (in_dir / "audio_meta.json").write_text(json.dumps({
        "episode_id": "test", "total_duration_ms": 60000, "tracks": tracks
    }))


# ── Test 1: resume fails without delete_segments_edited.json ─────────────────
def test_resume_requires_delete_segments(tmp_path):
    mod = _load()
    ep_dir = tmp_path / "ep"
    (ep_dir / "3_review").mkdir(parents=True)
    with unittest.mock.patch("sys.argv", ["run_pipeline.py", "--ep-dir", str(ep_dir), "--resume"]):
        with unittest.mock.patch("sys.exit") as mock_exit:
            mod.main()
    mock_exit.assert_called_once_with(1)


# ── Test 2: resume runs stage 4 when delete_segments exists ──────────────────
def test_resume_runs_stage4(tmp_path):
    mod = _load()
    ep_dir = tmp_path / "ep"
    review_dir = ep_dir / "3_review"
    review_dir.mkdir(parents=True)
    (review_dir / "delete_segments_edited.json").write_text('{"deletes": []}')

    with unittest.mock.patch("sys.argv", ["run_pipeline.py", "--ep-dir", str(ep_dir), "--resume"]):
        with unittest.mock.patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mod.main()

    calls = [c.args[0] for c in mock_run.call_args_list]
    scripts_called = [Path(c[1]).name for c in calls]
    assert "cut_audio.py" in scripts_called
    assert "trim_silences.py" in scripts_called


# ── Test 3: skips stages whose output already exists ─────────────────────────
def test_skips_done_stages(tmp_path):
    mod = _load()
    ep_dir = tmp_path / "ep"
    _meta(ep_dir, n_tracks=1)

    # pre-create all outputs through stage 2.3
    td = ep_dir / "1_transcribe"
    td.mkdir(parents=True)
    (td / "volcano_raw_track1.json").write_text("{}")
    (td / "words.json").write_text("{}")
    (td / "sentences.json").write_text("{}")
    ad = ep_dir / "2_analysis"
    ad.mkdir(parents=True)
    (ad / "rough_cuts.json").write_text("{}")
    (ad / "fine_cuts.json").write_text("{}")
    (ad / "self_review.json").write_text("{}")
    rd = ep_dir / "3_review"
    rd.mkdir(parents=True)
    (rd / "review_enhanced.html").write_text("<html/>")

    with unittest.mock.patch("sys.argv", ["run_pipeline.py", "--ep-dir", str(ep_dir)]):
        with unittest.mock.patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mod.main()

    # no subprocess.run calls — everything already done, pauses at review
    mock_run.assert_not_called()


# ── Test 4: new episode runs prepare_audio first ─────────────────────────────
def test_new_episode_runs_prepare_audio(tmp_path):
    mod = _load()
    ep_dir = tmp_path / "ep"
    track = tmp_path / "track1.wav"
    track.write_bytes(b"RIFF" + b"\x00" * 40)

    def fake_run(cmd, **kw):
        # After prepare_audio.py is "called", create audio_meta.json so pipeline can continue
        if "prepare_audio.py" in str(cmd):
            _meta(ep_dir, n_tracks=1)
        return unittest.mock.MagicMock(returncode=0)

    with unittest.mock.patch("sys.argv", ["run_pipeline.py",
                                           "--ep-dir", str(ep_dir),
                                           "--track1", str(track)]):
        with unittest.mock.patch("subprocess.run", side_effect=fake_run) as mock_run:
            mod.main()

    first_call = mock_run.call_args_list[0].args[0]
    assert "prepare_audio.py" in str(first_call[1])
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/scripts/test_run_pipeline.py -v
```

Expected: FAIL — `run_pipeline.py` does not exist.

- [ ] **Step 3: Implement `run_pipeline.py`**

```python
#!/usr/bin/env python3
"""Single entry point for the podcast cutting pipeline.

First run (stages 1–3, pauses at human review):
    python shared/scripts/run_pipeline.py \\
        --ep-dir output/2026-05-08-ep01 \\
        --track1 recordings/host.wav \\
        [--track2 recordings/guest.wav] \\
        [--align clap|timestamp|transcript] \\
        [--t1 10:00:00 --t2 10:00:03]

After review (export delete_segments_edited.json in browser, then):
    python shared/scripts/run_pipeline.py --ep-dir output/2026-05-08-ep01 --resume

Stages are skipped if their output already exists — safe to re-run.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYTHON = sys.executable


def _repo_root() -> Path:
    return Path(__file__).parent.parent.parent


def _scripts() -> Path:
    return Path(__file__).parent


def _run(cmd: list[str], label: str) -> None:
    print(f"\n[pipeline] {label}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"Stage failed (exit {result.returncode}): {label}")


def _done(path: Path) -> bool:
    return path.exists()


def main() -> None:
    ap = argparse.ArgumentParser(description="Podcast cutting pipeline.")
    ap.add_argument("--ep-dir", required=True, help="Episode output directory.")
    ap.add_argument("--track1", default=None, help="Path to track 1 recording.")
    ap.add_argument("--track2", default=None, help="Path to track 2 recording (optional).")
    ap.add_argument("--ep-id", default=None, help="Episode ID (defaults to ep-dir name).")
    ap.add_argument("--align", choices=["clap", "timestamp", "transcript"],
                    default=None, help="Track alignment mode (two-track only).")
    ap.add_argument("--t1", default=None, help="Track 1 wall-clock start time HH:MM:SS (for --align timestamp).")
    ap.add_argument("--t2", default=None, help="Track 2 wall-clock start time HH:MM:SS (for --align timestamp).")
    ap.add_argument("--resume", action="store_true", help="Skip to stage 4 after human review.")
    args = ap.parse_args()

    ep = Path(args.ep_dir)
    sc = _scripts()

    # ── Resume path ──────────────────────────────────────────────────────────
    if args.resume:
        delete_file = ep / "3_review" / "delete_segments_edited.json"
        if not delete_file.exists():
            print(f"[pipeline] ERROR: {delete_file} not found. Complete the browser review first.")
            sys.exit(1)
        if not _done(ep / "4_cut" / "cut.wav"):
            _run([PYTHON, str(sc / "cut_audio.py"), "--ep-dir", str(ep)], "4.0 cut audio")
        _run([PYTHON, str(sc / "trim_silences.py"), "--ep-dir", str(ep)], "4.1 trim silences")
        cut = ep / "4_cut" / "cut.wav"
        print(f"\n[pipeline] ✓ Done. Output: {cut}")
        return

    # ── Stage 1.0: prepare audio ─────────────────────────────────────────────
    if not _done(ep / "input" / "audio_meta.json"):
        if not args.track1:
            ap.error("--track1 is required for a new episode.")
        cmd = [PYTHON, str(sc / "prepare_audio.py"), "--ep-dir", str(ep),
               "--track1", args.track1]
        if args.track2:
            cmd += ["--track2", args.track2]
        if args.ep_id:
            cmd += ["--ep-id", args.ep_id]
        _run(cmd, "1.0 prepare audio")

    meta = json.loads((ep / "input" / "audio_meta.json").read_text())
    n_tracks = len(meta.get("tracks", []))
    two_track = n_tracks >= 2

    # ── Stage 1.05: align (clap / timestamp — before ASR) ───────────────────
    if two_track and "track_offsets_ms" not in meta and args.align in ("clap", "timestamp"):
        cmd = [PYTHON, str(sc / "align_tracks.py"), "--ep-dir", str(ep)]
        if args.align == "clap":
            cmd.append("--clap")
        else:
            if not args.t1 or not args.t2:
                ap.error("--t1 and --t2 are required for --align timestamp.")
            cmd += ["--t1", args.t1, "--t2", args.t2]
        _run(cmd, "1.05 align tracks (pre-ASR)")

    # ── Stage 1.2: ASR per track ─────────────────────────────────────────────
    for i in range(1, n_tracks + 1):
        if not _done(ep / "1_transcribe" / f"volcano_raw_track{i}.json"):
            wav = ep / "input" / f"working_track{i}.wav"
            _run([PYTHON, str(sc / "volcano_submit.py"),
                  "--audio-file", str(wav),
                  "--track-num", str(i),
                  "--ep-dir", str(ep)], f"1.2a ASR submit track{i}")
            _run([PYTHON, str(sc / "volcano_query.py"),
                  "--track-num", str(i),
                  "--ep-dir", str(ep)], f"1.2b ASR query track{i}")

    # ── Stage 1.05: align (transcript — after ASR) ───────────────────────────
    meta = json.loads((ep / "input" / "audio_meta.json").read_text())
    if two_track and "track_offsets_ms" not in meta and args.align not in ("clap", "timestamp"):
        _run([PYTHON, str(sc / "align_tracks.py"), "--ep-dir", str(ep)],
             "1.05 align tracks (transcript, post-ASR)")

    # ── Stage 1.3: merge transcription ───────────────────────────────────────
    if not _done(ep / "1_transcribe" / "words.json"):
        _run([PYTHON, str(sc / "transcribe_merge.py"), "--ep-dir", str(ep)], "1.3 transcribe merge")

    # ── Stage 1.4: sentences ─────────────────────────────────────────────────
    if not _done(ep / "1_transcribe" / "sentences.json"):
        _run([PYTHON, str(sc / "make_sentences.py"), "--ep-dir", str(ep)], "1.4 make sentences")

    # ── Stage 2.1: rough cuts ────────────────────────────────────────────────
    if not _done(ep / "2_analysis" / "rough_cuts.json"):
        _run([PYTHON, str(sc / "analyze_rough.py"), "--ep-dir", str(ep)], "2.1 rough cut analysis")

    # ── Stage 2.2: fine cuts ─────────────────────────────────────────────────
    if not _done(ep / "2_analysis" / "fine_cuts.json"):
        _run([PYTHON, str(sc / "analyze_fine.py"), "--ep-dir", str(ep)], "2.2 fine cut analysis")

    # ── Stage 2.3: self-review ───────────────────────────────────────────────
    if not _done(ep / "2_analysis" / "self_review.json"):
        _run([PYTHON, str(sc / "self_review.py"), "--ep-dir", str(ep)], "2.3 self-review")

    # ── Stage 3.0: review HTML ───────────────────────────────────────────────
    html = ep / "3_review" / "review_enhanced.html"
    if not _done(html):
        _run([PYTHON, str(sc / "generate_review_html.py"), "--ep-dir", str(ep)], "3.0 generate review HTML")

    # ── Pause: human review ──────────────────────────────────────────────────
    print(f"""
[pipeline] ────────────────────────────────────────────────────────────
  Transcription and analysis complete. Human review required.

  Review file : {html}
  Start server: python shared/scripts/review_server.py --ep-dir {ep} --port 5050

  Steps:
    1. Start the review server (command above)
    2. Open the review file in your browser
    3. Review suggested cuts — accept, reject, or adjust
    4. Click Export (saves delete_segments_edited.json automatically)
    5. Run this to finish:
         python shared/scripts/run_pipeline.py --ep-dir {ep} --resume
[pipeline] ────────────────────────────────────────────────────────────
""")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests**

```bash
python -m pytest tests/scripts/test_run_pipeline.py -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Full suite**

```bash
python -m pytest tests/ -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add shared/scripts/run_pipeline.py tests/scripts/test_run_pipeline.py
git commit -m "feat: add run_pipeline.py — single entry point for the full podcast pipeline"
```

---

## Task 3: Update SKILL.md + add Codex mirror

**Files:**
- Modify: `.claude/skills/podcast-cut-剪播客/SKILL.md`
- Create: `.codex/skills/podcast-cut-剪播客/SKILL.md`

No tests — these are skill definition files read by agents.

- [ ] **Step 1: Rewrite `.claude/skills/podcast-cut-剪播客/SKILL.md`**

Replace the entire file with:

```markdown
---
name: podcast-cut-剪播客
description: |
  将原始播客录音（单轨或双轨）自动转录、LLM分析并裁剪为 cut.wav，供后期使用。
  触发词：剪播客、cut podcast、裁剪录音、处理录音
---

# /podcast-cut-剪播客

将录音转录、AI分析、人工审查后输出 cut.wav。

## 前提条件

已运行 `/podcast-cut-安装`，且 `.env` 已配置：
- `VOLC_API_KEY`（或 `VOLC_APP_KEY` + `VOLC_ACCESS_KEY`）
- `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`

## 用法（两条命令）

**第一步：运行流水线（转录 + 分析，约需 5-20 分钟）**

```bash
python shared/scripts/run_pipeline.py \
  --ep-dir output/2026-05-08-ep01 \
  --track1 recordings/host.wav \
  --track2 recordings/guest.wav
```

流水线会自动完成：
- 1.0 音频准备（转换格式）
- 1.05 轨道对齐（双轨时自动推断，可用 `--align clap` 或 `--align timestamp --t1 HH:MM:SS --t2 HH:MM:SS` 指定）
- 1.2 Volcano ASR 转录（含上传）
- 1.3 合并 + 1.4 分句
- 2.1 粗剪 + 2.2 精剪 + 2.3 自审
- 3.0 生成审查 HTML

完成后打印审查文件路径和 review_server 启动命令，**等待人工审查**。

**人工审查**

```bash
python shared/scripts/review_server.py --ep-dir output/2026-05-08-ep01 --port 5050
# 浏览器打开 output/2026-05-08-ep01/3_review/review_enhanced.html
# 审查建议删除内容，点击 Export → 自动保存 delete_segments_edited.json
```

**第二步：完成剪辑**

```bash
python shared/scripts/run_pipeline.py --ep-dir output/2026-05-08-ep01 --resume
```

输出：`output/2026-05-08-ep01/4_cut/cut.wav`

## 重新运行

每个阶段检测输出是否已存在，已完成的阶段自动跳过。在任意阶段中断后重新运行两条命令即可续传。

## 常见错误

| 错误 | 原因 | 处理 |
|------|------|------|
| Volcano `45000001` | API key 无效 | 检查 `.env` 中的 Volcano 配置 |
| Volcano `45000132` | 音频超 512 MB | 先用 ffmpeg 转为 16kHz mono mp3 |
| uguu.se 上传失败 | 文件过大或网络问题 | 重试，或配置 TOS/S3 |
| `silence trap` | 输出几乎全静音 | 检查输入文件是否包含有效音频 |
| `delete_segments_edited.json not found` | 审查未完成 | 在浏览器中点击 Export 后再 --resume |

## 各阶段详情

- [阶段1 转录](../../docs/剪播客/阶段1-转录.md)
- [阶段2 分析](../../docs/剪播客/阶段2-分析.md)
- [阶段3 审查](../../docs/剪播客/阶段3-审查.md)
- [阶段4 剪辑](../../docs/剪播客/阶段4-剪辑.md)
```

- [ ] **Step 2: Create `.codex/skills/podcast-cut-剪播客/SKILL.md`**

Codex CLI uses a different skill format. Create the directory and file:

```markdown
# podcast-cut-剪播客

将录音转录、AI分析并剪为 cut.wav。

## 用法

```bash
# 第一步（转录 + 分析）
python shared/scripts/run_pipeline.py \
  --ep-dir output/EP_ID \
  --track1 recordings/host.wav \
  [--track2 recordings/guest.wav]

# 人工在浏览器中审查后：
python shared/scripts/run_pipeline.py --ep-dir output/EP_ID --resume
```

## 前提

- `.env` 已配置 `VOLC_API_KEY` 和 `LLM_API_KEY`
- `pip install -e ".[dev]"` 已执行
- ffmpeg 已安装（`brew install ffmpeg` 或 `apt install ffmpeg`）

## 输出

`output/EP_ID/4_cut/cut.wav` — 已按审查意见剪辑的干净音频。
```

- [ ] **Step 3: Update README quick-start**

In `README.md`, replace the 10-step command sequence in the Quick Start section with the two-command interface:

```markdown
## Quick Start

```bash
# 1. Install Python dependencies
pip install -e ".[dev]"

# 2. Copy and fill in the environment file
cp .env.example .env
# Edit .env — set VOLC_API_KEY and LLM_API_KEY at minimum

# 3. Run the pipeline (transcription + analysis, ~5–20 min)
python shared/scripts/run_pipeline.py \
  --ep-dir output/2026-05-08-ep01 \
  --track1 recordings/host.wav \
  --track2 recordings/guest.wav

# 4. Review in browser (the pipeline prints the URL and server command)
python shared/scripts/review_server.py --ep-dir output/2026-05-08-ep01 --port 5050
# Open output/2026-05-08-ep01/3_review/review_enhanced.html, review, click Export

# 5. Finish the cut
python shared/scripts/run_pipeline.py --ep-dir output/2026-05-08-ep01 --resume
# Result: output/2026-05-08-ep01/4_cut/cut.wav
```

For alignment options, troubleshooting, and per-stage details, see [docs/剪播客/快速上手.md](docs/剪播客/快速上手.md).
```

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/podcast-cut-剪播客/SKILL.md \
        .codex/skills/podcast-cut-剪播客/SKILL.md \
        README.md
git commit -m "docs: rewrite SKILL.md to two-command interface, add Codex mirror"
```
