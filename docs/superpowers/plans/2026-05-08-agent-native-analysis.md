# Agent-Native Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the doubao/Ark LLM API dependency from the pipeline by replacing `analyze_rough.py`, `analyze_fine.py`, and `self_review.py` with a single context-builder script; the orchestrating agent (Claude Code, Codex, Gemini) reads the context and writes the analysis JSONs directly.

**Architecture:** Stage 2 is split into two sub-stages: 2.0 (`build_analysis_context.py`) which assembles transcript + rules into `2_analysis/analysis_context.md`, and the agent analysis pass where the orchestrating agent reads that file and writes `rough_cuts.json`, `fine_cuts.json`, `self_review.json`. The pipeline pauses after stage 2.0 and resumes via `--resume` which auto-detects state from file existence.

**Tech Stack:** Python 3.10+, pathlib, json, yaml (PyYAML — already indirectly available; use `json` + text loading since preferences.yaml is simple). No new dependencies introduced.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `shared/scripts/build_analysis_context.py` | Reads transcript + rules → writes `analysis_context.md` |
| Delete | `shared/scripts/analyze_rough.py` | Replaced by agent analysis |
| Delete | `shared/scripts/analyze_fine.py` | Replaced by agent analysis |
| Delete | `shared/scripts/self_review.py` | Replaced by agent analysis |
| Modify | `shared/scripts/lib/config.py` | Remove `LLMConfig` + `_build_llm`; remove `llm` from `Config` |
| Modify | `shared/scripts/run_pipeline.py` | Replace stages 2.1–2.3 with stage 2.0 + pause; update `--resume` to auto-detect two pause points |
| Modify | `pyproject.toml` | Remove `openai>=1.0.0` from dependencies |
| Create | `tests/scripts/test_build_analysis_context.py` | Tests for context builder |
| Delete | `tests/scripts/test_analyze_rough.py` | Script deleted |
| Delete | `tests/scripts/test_analyze_fine.py` | Script deleted |
| Delete | `tests/scripts/test_self_review.py` | Script deleted |
| Modify | `tests/lib/test_config.py` | Remove LLM test cases + `LLM_KEYS` helper from all tests |
| Modify | `tests/scripts/test_run_pipeline.py` | Update for new two-pause-point flow |
| Modify | `.claude/skills/podcast-cut-剪播客/SKILL.md` | Add detailed agent analysis instructions (stage 2) |
| Modify | `.codex/skills/podcast-cut-剪播客/SKILL.md` | Mirror update |
| Modify | `README.md` | Remove LLM env vars from required table; update pipeline description |
| Modify | `AGENTS.md` | Remove LLM env vars; update stage outputs |
| Modify | `docs/剪播客/快速上手.md` | Update to three-command flow |

---

## Data Contracts (unchanged — downstream scripts still read same JSON)

`rough_cuts.json` (written by agent, read by `generate_review_html.py`):
```json
{
  "deletes": [
    {
      "start_ms": 0,
      "end_ms": 45000,
      "level": "rough",
      "reason": "录前闲聊",
      "source": "agent_rough",
      "confidence": 0.9
    }
  ]
}
```

`fine_cuts.json` (written by agent):
```json
{
  "deletes": [
    {
      "start_ms": 12340,
      "end_ms": 12890,
      "level": "fine",
      "reason": "口头禅嗯",
      "source": "agent_fine",
      "confidence": 0.85
    }
  ]
}
```

`self_review.json` (written by agent, `deletes` + `flags` + `summary`):
```json
{
  "deletes": [],
  "flags": [
    {"start_ms": 0, "end_ms": 5000, "flag": "false_positive", "reason": "实为开场介绍，不应删"}
  ],
  "summary": "共审查15条建议，标记2条误删，补充3条遗漏"
}
```

`generate_review_html.py` already reads all three; `self_review.json` is already optional-chained so no change needed there.

---

## New Pipeline Flow

```
run_pipeline.py --ep-dir X --track1 Y
  Stage 1.0  prepare_audio.py
  Stage 1.05 align_tracks.py  (pre-ASR if clap/timestamp)
  Stage 1.2  volcano_submit.py + volcano_query.py  (per track)
  Stage 1.05 align_tracks.py  (post-ASR transcript inference)
  Stage 1.3  transcribe_merge.py
  Stage 1.4  make_sentences.py
  Stage 2.0  build_analysis_context.py  ← NEW
  → PAUSE: print "Agent analysis required — read analysis_context.md, write 3 JSONs, then --resume"

run_pipeline.py --ep-dir X --resume       (after agent writes self_review.json)
  Stage 3.0  generate_review_html.py
  → PAUSE: print "Human review required — start review server, export, then --resume"

run_pipeline.py --ep-dir X --resume       (after human exports delete_segments_edited.json)
  Stage 4.0  cut_audio.py
  Stage 4.1  trim_silences.py
  → DONE: output/X/4_cut/cut.wav
```

`--resume` auto-detects state:
1. `delete_segments_edited.json` exists → run stage 4 → done
2. `self_review.json` exists (but no `delete_segments_edited.json`) → run stage 3.0 → print human review message
3. Neither → print error, `sys.exit(1)`

---

## Task 1: `build_analysis_context.py`

**Files:**
- Create: `shared/scripts/build_analysis_context.py`
- Create: `tests/scripts/test_build_analysis_context.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/scripts/test_build_analysis_context.py
import importlib.util, json, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load():
    spec = importlib.util.spec_from_file_location(
        "build_analysis_context", SCRIPTS / "build_analysis_context.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _setup(tmp_path):
    ep = tmp_path / "ep"
    td = ep / "1_transcribe"
    td.mkdir(parents=True)
    (ep / "2_analysis").mkdir(parents=True)

    sentences = {"sentences": [
        {"id": 0, "speaker": "S1", "start_ms": 0, "end_ms": 3000, "text": "录前闲聊"},
        {"id": 1, "speaker": "S2", "start_ms": 3500, "end_ms": 8000, "text": "正式内容"},
    ]}
    (td / "sentences.json").write_text(json.dumps(sentences))

    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    (rules_dir / "1-核心原则.md").write_text("# 核心原则\n删掉录前闲聊。")
    prefs_dir = tmp_path / "prefs"
    prefs_dir.mkdir()
    (prefs_dir / "preferences.yaml").write_text("aggressiveness: moderate\n")
    return ep, rules_dir, prefs_dir


def test_writes_analysis_context(tmp_path):
    """build_analysis_context writes analysis_context.md."""
    ep, rules_dir, prefs_dir = _setup(tmp_path)
    mod = _load()
    import sys, unittest.mock
    with unittest.mock.patch("sys.argv", [
        "build_analysis_context.py",
        "--ep-dir", str(ep),
        "--rules-dir", str(rules_dir),
        "--prefs-file", str(prefs_dir / "preferences.yaml"),
    ]):
        mod.main()

    ctx = ep / "2_analysis" / "analysis_context.md"
    assert ctx.exists()
    text = ctx.read_text()
    assert "核心原则" in text
    assert "aggressiveness" in text
    assert "录前闲聊" in text   # sentence text appears
    assert "00:00" in text       # timestamps formatted


def test_contains_output_format_spec(tmp_path):
    """analysis_context.md includes the JSON output format the agent must follow."""
    ep, rules_dir, prefs_dir = _setup(tmp_path)
    mod = _load()
    import sys, unittest.mock
    with unittest.mock.patch("sys.argv", [
        "build_analysis_context.py",
        "--ep-dir", str(ep),
        "--rules-dir", str(rules_dir),
        "--prefs-file", str(prefs_dir / "preferences.yaml"),
    ]):
        mod.main()

    text = (ep / "2_analysis" / "analysis_context.md").read_text()
    assert "rough_cuts.json" in text
    assert "fine_cuts.json" in text
    assert "self_review.json" in text
    assert "agent_rough" in text   # source field value in format spec
    assert "agent_fine" in text


def test_missing_sentences_raises(tmp_path):
    """Missing sentences.json raises FileNotFoundError."""
    ep = tmp_path / "ep"
    (ep / "1_transcribe").mkdir(parents=True)
    (ep / "2_analysis").mkdir(parents=True)
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    prefs_dir = tmp_path / "prefs"
    prefs_dir.mkdir()
    (prefs_dir / "preferences.yaml").write_text("")
    mod = _load()
    import sys, unittest.mock, pytest
    with unittest.mock.patch("sys.argv", [
        "build_analysis_context.py",
        "--ep-dir", str(ep),
        "--rules-dir", str(rules_dir),
        "--prefs-file", str(prefs_dir / "preferences.yaml"),
    ]):
        with pytest.raises((FileNotFoundError, SystemExit)):
            mod.main()


def test_default_rules_and_prefs_paths(tmp_path):
    """Without --rules-dir/--prefs-file, uses repo defaults."""
    ep, _, _ = _setup(tmp_path)  # rules_dir and prefs not used here
    # create sentences only; rely on real rules from repo
    import sys, unittest.mock
    mod = _load()
    with unittest.mock.patch("sys.argv", [
        "build_analysis_context.py", "--ep-dir", str(ep),
    ]):
        mod.main()  # should not raise; real rules exist

    assert (ep / "2_analysis" / "analysis_context.md").exists()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/houyuxin/08Coding/podcast-cutter-skills
python -m pytest tests/scripts/test_build_analysis_context.py -v
```

Expected: `ModuleNotFoundError` or `FileNotFoundError` — file doesn't exist yet.

- [ ] **Step 3: Implement `build_analysis_context.py`**

```python
#!/usr/bin/env python3
"""Stage 2.0: Assemble analysis context for the orchestrating agent.

Reads sentences.json, editing rules, and user preferences; writes
2_analysis/analysis_context.md which the agent reads to perform analysis.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).parent.parent.parent


def _ms_to_ts(ms: int) -> str:
    s = ms // 1000
    return f"{s // 60:02d}:{s % 60:02d}"


def _load_rules(rules_dir: Path) -> str:
    parts = []
    for md in sorted(rules_dir.glob("*.md")):
        parts.append(md.read_text())
    return "\n\n---\n\n".join(parts) if parts else "(no rules found)"


def _format_sentences(sentences: list[dict]) -> str:
    lines = []
    for s in sentences:
        ts = _ms_to_ts(s["start_ms"])
        speaker = s.get("speaker", "?")
        text = s.get("text", "")
        lines.append(f"[{ts}] {speaker}: {text}")
    return "\n".join(lines)


OUTPUT_FORMAT = """
## 输出格式要求

你（agent）需要在 `2_analysis/` 目录下写入三个 JSON 文件：

### rough_cuts.json（粗剪 — 大段内容级删除）
```json
{
  "deletes": [
    {
      "start_ms": <整数毫秒>,
      "end_ms": <整数毫秒>,
      "level": "rough",
      "reason": "<删除原因（中文）>",
      "source": "agent_rough",
      "confidence": <0.0-1.0>
    }
  ]
}
```

### fine_cuts.json（精剪 — 词/句级细节删除）
```json
{
  "deletes": [
    {
      "start_ms": <整数毫秒>,
      "end_ms": <整数毫秒>,
      "level": "fine",
      "reason": "<删除原因>",
      "source": "agent_fine",
      "confidence": <0.0-1.0>
    }
  ]
}
```

### self_review.json（自审 — 审查粗剪和精剪结果）
```json
{
  "deletes": [
    {
      "start_ms": <整数毫秒>,
      "end_ms": <整数毫秒>,
      "level": "fine",
      "reason": "<遗漏的删除>",
      "source": "agent_self_review",
      "confidence": <0.0-1.0>
    }
  ],
  "flags": [
    {
      "start_ms": <整数毫秒>,
      "end_ms": <整数毫秒>,
      "flag": "false_positive",
      "reason": "<为什么这条建议是误删>"
    }
  ],
  "summary": "<总体评估，1-3句>"
}
```

所有时间戳必须是整数毫秒，与下方 sentences 列表中的 start_ms/end_ms 对应。
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep-dir", required=True)
    ap.add_argument("--rules-dir", default=None)
    ap.add_argument("--prefs-file", default=None)
    args = ap.parse_args()

    repo = _repo_root()
    rules_dir = Path(args.rules_dir) if args.rules_dir else repo / "shared/rules/editing"
    prefs_file = (
        Path(args.prefs_file) if args.prefs_file
        else repo / "shared/rules/users/default/preferences.yaml"
    )

    ep_dir = Path(args.ep_dir)
    td = ep_dir / "1_transcribe"
    ad = ep_dir / "2_analysis"
    ad.mkdir(parents=True, exist_ok=True)

    sentences_path = td / "sentences.json"
    if not sentences_path.exists():
        raise FileNotFoundError(f"sentences.json not found: {sentences_path}")

    sentences = json.loads(sentences_path.read_text())["sentences"]
    rules_text = _load_rules(rules_dir)
    prefs_text = prefs_file.read_text() if prefs_file.exists() else "(preferences not found)"

    context = f"""# 播客剪辑分析上下文

## 剪辑规则

{rules_text}

---

## 用户偏好

```yaml
{prefs_text}
```

---
{OUTPUT_FORMAT}
---

## 完整文本（共 {len(sentences)} 句）

{_format_sentences(sentences)}
"""

    out = ad / "analysis_context.md"
    out.write_text(context, encoding="utf-8")
    print(f"analysis_context.md written ({len(sentences)} sentences, {out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/scripts/test_build_analysis_context.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add shared/scripts/build_analysis_context.py tests/scripts/test_build_analysis_context.py
git commit -m "feat: add build_analysis_context.py (stage 2.0 context assembler)"
```

---

## Task 2: Remove LLM scripts + clean config + pyproject.toml

**Files:**
- Delete: `shared/scripts/analyze_rough.py`
- Delete: `shared/scripts/analyze_fine.py`
- Delete: `shared/scripts/self_review.py`
- Delete: `tests/scripts/test_analyze_rough.py`
- Delete: `tests/scripts/test_analyze_fine.py`
- Delete: `tests/scripts/test_self_review.py`
- Modify: `shared/scripts/lib/config.py`
- Modify: `tests/lib/test_config.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Delete the LLM analysis scripts and their tests**

```bash
rm shared/scripts/analyze_rough.py
rm shared/scripts/analyze_fine.py
rm shared/scripts/self_review.py
rm tests/scripts/test_analyze_rough.py
rm tests/scripts/test_analyze_fine.py
rm tests/scripts/test_self_review.py
```

- [ ] **Step 2: Remove `LLMConfig` from `lib/config.py`**

In `shared/scripts/lib/config.py`, make these changes:

Remove the `LLMConfig` dataclass (the whole `@dataclass(frozen=True) class LLMConfig:` block).

Remove `llm: LLMConfig` from the `Config` dataclass.

Remove the `_build_llm` function.

Remove the `llm=llm` line and the `llm = _build_llm(raw)` call from `load()`.

The `load()` function after edits:

```python
def load(env_path: Path) -> Config:
    env_path = Path(env_path)
    if not env_path.is_file():
        raise ConfigError(f".env not found at {env_path}")
    raw = {k: v for k, v in dotenv_values(env_path).items()}

    volcano = _build_volcano(raw)
    tos = _build_tos(raw)
    s3 = _build_s3(raw)
    upload_backend: Literal["tos", "s3", "uguu"] = (
        "tos" if tos else "s3" if s3 else "uguu"
    )

    return Config(
        volcano=volcano,
        tos=tos,
        s3=s3,
        gemini_api_key=_nonempty(raw, "GEMINI_API_KEY"),
        upload_backend=upload_backend,
    )
```

The `Config` dataclass after edits:

```python
@dataclass(frozen=True)
class Config:
    volcano: VolcanoConfig
    tos: Optional[TOSConfig]
    s3: Optional[S3Config]
    gemini_api_key: Optional[str]
    upload_backend: Literal["tos", "s3", "uguu"]
```

- [ ] **Step 3: Update `tests/lib/test_config.py`**

Remove the `LLM_KEYS` constant and all `+ LLM_KEYS` concatenations from every test.

Remove the two test functions `test_llm_config_loaded` and `test_llm_config_missing_key_raises` entirely.

Each test that currently ends with `+ LLM_KEYS` should just remove that suffix — the `.env` content no longer needs LLM keys for `config.load()` to succeed.

Example: `test_new_console_config_loaded` currently writes:
```python
env.write_text(
    "VOLC_API_KEY=newkey\nVOLC_RESOURCE_ID=volc.seedasr.auc\n"
    + LLM_KEYS
)
```
After edit:
```python
env.write_text("VOLC_API_KEY=newkey\nVOLC_RESOURCE_ID=volc.seedasr.auc\n")
```

Apply this pattern to every test in the file.

- [ ] **Step 4: Remove `openai` from `pyproject.toml`**

In `pyproject.toml`, remove the `"openai>=1.0.0",` line from `dependencies`.

- [ ] **Step 5: Verify tests pass**

```bash
python -m pytest tests/lib/test_config.py -v
python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all remaining tests pass (test count will drop by ~11 — 9 analysis tests + 2 LLM config tests).

- [ ] **Step 6: Commit**

```bash
git add -u
git commit -m "refactor: remove doubao LLM API — agent does analysis directly"
```

---

## Task 3: Update `run_pipeline.py` for two-pause-point flow

**Files:**
- Modify: `shared/scripts/run_pipeline.py`
- Modify: `tests/scripts/test_run_pipeline.py`

- [ ] **Step 1: Write failing tests for the new pipeline behavior**

Replace the entire contents of `tests/scripts/test_run_pipeline.py` with:

```python
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


def _make_meta(ep_dir: Path, n_tracks: int = 1) -> None:
    in_dir = ep_dir / "input"
    in_dir.mkdir(parents=True, exist_ok=True)
    tracks = [{"file": f"working_track{i}.wav", "duration_ms": 60000, "sample_rate": 44100}
              for i in range(1, n_tracks + 1)]
    (in_dir / "audio_meta.json").write_text(json.dumps({
        "episode_id": "test", "total_duration_ms": 60000, "tracks": tracks
    }))


def _make_transcribe(ep_dir: Path, n_tracks: int = 1) -> None:
    td = ep_dir / "1_transcribe"
    td.mkdir(parents=True, exist_ok=True)
    for i in range(1, n_tracks + 1):
        (td / f"volcano_raw_track{i}.json").write_text("{}")
    (td / "words.json").write_text('{"words":[]}')
    (td / "sentences.json").write_text('{"sentences":[]}')


def _make_analysis(ep_dir: Path) -> None:
    ad = ep_dir / "2_analysis"
    ad.mkdir(parents=True, exist_ok=True)
    (ad / "analysis_context.md").write_text("# context")
    (ad / "rough_cuts.json").write_text('{"deletes":[]}')
    (ad / "fine_cuts.json").write_text('{"deletes":[]}')
    (ad / "self_review.json").write_text('{"deletes":[],"flags":[],"summary":"ok"}')


# ── resume tests ─────────────────────────────────────────────────────────────

def test_resume_no_analysis_exits_error(tmp_path):
    """--resume with no self_review.json and no delete_segments exits with code 1."""
    mod = _load()
    ep_dir = tmp_path / "ep"
    (ep_dir / "3_review").mkdir(parents=True)
    with unittest.mock.patch("sys.argv", ["run_pipeline.py", "--ep-dir", str(ep_dir), "--resume"]):
        with unittest.mock.patch("sys.exit") as mock_exit, \
             unittest.mock.patch("subprocess.run") as mock_run:
            mod.main()
    mock_exit.assert_called_once_with(1)
    mock_run.assert_not_called()


def test_resume_with_self_review_runs_html_generation(tmp_path):
    """--resume with self_review.json (no delete_segments) runs generate_review_html.py."""
    mod = _load()
    ep_dir = tmp_path / "ep"
    _make_analysis(ep_dir)

    with unittest.mock.patch("sys.argv", ["run_pipeline.py", "--ep-dir", str(ep_dir), "--resume"]):
        with unittest.mock.patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mod.main()

    scripts_called = [Path(c.args[0][1]).name for c in mock_run.call_args_list]
    assert "generate_review_html.py" in scripts_called
    assert "cut_audio.py" not in scripts_called


def test_resume_with_delete_segments_runs_stage4(tmp_path):
    """--resume with delete_segments_edited.json runs cut_audio.py + trim_silences.py."""
    mod = _load()
    ep_dir = tmp_path / "ep"
    _make_analysis(ep_dir)
    rd = ep_dir / "3_review"
    rd.mkdir(parents=True)
    (rd / "delete_segments_edited.json").write_text('{"deletes":[]}')

    with unittest.mock.patch("sys.argv", ["run_pipeline.py", "--ep-dir", str(ep_dir), "--resume"]):
        with unittest.mock.patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mod.main()

    scripts_called = [Path(c.args[0][1]).name for c in mock_run.call_args_list]
    assert "cut_audio.py" in scripts_called
    assert "trim_silences.py" in scripts_called


def test_resume_skips_html_if_already_exists(tmp_path):
    """--resume skips generate_review_html.py if review_enhanced.html already exists."""
    mod = _load()
    ep_dir = tmp_path / "ep"
    _make_analysis(ep_dir)
    rd = ep_dir / "3_review"
    rd.mkdir(parents=True)
    (rd / "review_enhanced.html").write_text("<html/>")

    with unittest.mock.patch("sys.argv", ["run_pipeline.py", "--ep-dir", str(ep_dir), "--resume"]):
        with unittest.mock.patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mod.main()

    scripts_called = [Path(c.args[0][1]).name for c in mock_run.call_args_list]
    assert "generate_review_html.py" not in scripts_called


# ── normal run tests ──────────────────────────────────────────────────────────

def test_skips_done_stages(tmp_path):
    """All stage outputs exist: no subprocess.run calls, prints analysis-required message."""
    mod = _load()
    ep_dir = tmp_path / "ep"
    _make_meta(ep_dir, n_tracks=1)
    _make_transcribe(ep_dir, n_tracks=1)
    _make_analysis(ep_dir)

    with unittest.mock.patch("sys.argv", ["run_pipeline.py", "--ep-dir", str(ep_dir)]):
        with unittest.mock.patch("subprocess.run") as mock_run:
            mod.main()

    mock_run.assert_not_called()


def test_new_episode_runs_prepare_audio_first(tmp_path):
    """New episode: prepare_audio.py is the first subprocess called."""
    mod = _load()
    ep_dir = tmp_path / "ep"
    track = tmp_path / "track1.wav"
    track.write_bytes(b"RIFF" + b"\x00" * 40)

    def fake_run(cmd, **kw):
        script_name = Path(cmd[1]).name if len(cmd) > 1 else ""
        if script_name == "prepare_audio.py":
            _make_meta(ep_dir, n_tracks=1)
        return unittest.mock.MagicMock(returncode=0)

    with unittest.mock.patch("sys.argv", ["run_pipeline.py",
                                           "--ep-dir", str(ep_dir),
                                           "--track1", str(track)]):
        with unittest.mock.patch("subprocess.run", side_effect=fake_run) as mock_run:
            mod.main()

    first_script = Path(mock_run.call_args_list[0].args[0][1]).name
    assert first_script == "prepare_audio.py"


def test_stage2_context_builder_called_after_transcription(tmp_path):
    """After transcription stages, build_analysis_context.py is called."""
    mod = _load()
    ep_dir = tmp_path / "ep"
    _make_meta(ep_dir, n_tracks=1)
    _make_transcribe(ep_dir, n_tracks=1)
    # No analysis_context.md yet

    with unittest.mock.patch("sys.argv", ["run_pipeline.py", "--ep-dir", str(ep_dir)]):
        with unittest.mock.patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mod.main()

    scripts_called = [Path(c.args[0][1]).name for c in mock_run.call_args_list]
    assert "build_analysis_context.py" in scripts_called
    # LLM analysis scripts must NOT be called
    assert "analyze_rough.py" not in scripts_called
    assert "analyze_fine.py" not in scripts_called
    assert "self_review.py" not in scripts_called
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/scripts/test_run_pipeline.py -v
```

Expected: several tests FAIL because pipeline still calls analyze_rough.py etc.

- [ ] **Step 3: Update `run_pipeline.py`**

Replace the `--resume` block and stages 2.1–2.3 in `shared/scripts/run_pipeline.py` with:

```python
    # ── Resume path ──────────────────────────────────────────────────────────
    if args.resume:
        delete_file = ep / "3_review" / "delete_segments_edited.json"
        self_review = ep / "2_analysis" / "self_review.json"

        if delete_file.exists():
            # Post-human-review: stage 4
            if not _done(ep / "4_cut" / "cut.wav"):
                _run([PYTHON, str(sc / "cut_audio.py"), "--ep-dir", str(ep)], "4.0 cut audio")
            _run([PYTHON, str(sc / "trim_silences.py"), "--ep-dir", str(ep)], "4.1 trim silences")
            print(f"\n[pipeline] Done. Output: {ep / '4_cut' / 'cut.wav'}")
            return

        if self_review.exists():
            # Post-agent-analysis: stage 3.0
            html = ep / "3_review" / "review_enhanced.html"
            if not _done(html):
                _run([PYTHON, str(sc / "generate_review_html.py"), "--ep-dir", str(ep)],
                     "3.0 generate review HTML")
            print(f"""
[pipeline] ────────────────────────────────────────────────────────────
  Analysis complete. Human review required.

  Review file : {ep / '3_review' / 'review_enhanced.html'}
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
            return

        # Neither: analysis not complete
        ctx = ep / "2_analysis" / "analysis_context.md"
        print(f"[pipeline] ERROR: Agent analysis not complete.")
        print(f"  Read {ctx} and write rough_cuts.json, fine_cuts.json, self_review.json")
        print(f"  Then run: python shared/scripts/run_pipeline.py --ep-dir {ep} --resume")
        sys.exit(1)
        return
```

Replace the three stage 2.x blocks (stages 2.1, 2.2, 2.3) with a single stage 2.0 block:

```python
    # ── Stage 2.0: build analysis context ────────────────────────────────────
    if not _done(ep / "2_analysis" / "analysis_context.md"):
        _run([PYTHON, str(sc / "build_analysis_context.py"), "--ep-dir", str(ep)],
             "2.0 build analysis context")

    # ── Pause: agent analysis ─────────────────────────────────────────────────
    print(f"""
[pipeline] ────────────────────────────────────────────────────────────
  Transcription complete. Agent analysis required.

  Context file: {ep / '2_analysis' / 'analysis_context.md'}

  As the orchestrating agent, read the context file and write:
    - {ep / '2_analysis' / 'rough_cuts.json'}
    - {ep / '2_analysis' / 'fine_cuts.json'}
    - {ep / '2_analysis' / 'self_review.json'}

  Then resume:
    python shared/scripts/run_pipeline.py --ep-dir {ep} --resume
[pipeline] ────────────────────────────────────────────────────────────
""")
```

Also remove the old stage 3.0 block and old pause message (they moved into `--resume`). The main path now ends right after the agent-analysis pause print.

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/scripts/test_run_pipeline.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add shared/scripts/run_pipeline.py tests/scripts/test_run_pipeline.py
git commit -m "feat: pipeline pauses after transcription for agent analysis"
```

---

## Task 4: Update SKILL.md with agent analysis instructions

**Files:**
- Modify: `.claude/skills/podcast-cut-剪播客/SKILL.md`
- Modify: `.codex/skills/podcast-cut-剪播客/SKILL.md`

- [ ] **Step 1: Rewrite `.claude/skills/podcast-cut-剪播客/SKILL.md`**

Replace the entire file with:

```markdown
---
name: podcast-cut-剪播客
description: |
  将原始播客录音（单轨或双轨）自动转录、AI分析并裁剪为 cut.wav，供后期使用。
  触发词：剪播客、cut podcast、裁剪录音、处理录音
---

# /podcast-cut-剪播客

将录音转录、分析、人工审查后输出 cut.wav。整个流程分三步：
1. 转录（自动）
2. 分析（**你来做**）
3. 剪辑（自动）

## 前提条件

已运行 `/podcast-cut-安装`，且 `.env` 已配置：
- `VOLC_API_KEY`（或 `VOLC_APP_KEY` + `VOLC_ACCESS_KEY`）

## 三步流程

### 第一步：转录

```bash
python shared/scripts/run_pipeline.py \
  --ep-dir output/2026-05-08-ep01 \
  --track1 recordings/host.wav \
  --track2 recordings/guest.wav
```

流水线自动完成：
- 1.0 音频准备
- 1.05 轨道对齐（双轨时自动从 ASR 结果推断；可用 `--align clap` 或 `--align timestamp --t1 HH:MM:SS --t2 HH:MM:SS`）
- 1.2 Volcano ASR 转录
- 1.3 合并 + 1.4 分句
- 2.0 生成分析上下文（`analysis_context.md`）

结束时打印：**"Agent analysis required"**，并列出 `analysis_context.md` 路径。

---

### 第二步：你做分析（三轮）

流水线结束后，读取打印出的 `analysis_context.md`，按以下三轮完成分析。

#### 2.1 粗剪（内容级）

阅读 `analysis_context.md` 中的**剪辑规则**和**完整文本**，找出大段应删除的内容：
- 录前/录后闲聊（主题开始前的内容）
- 与主题完全无关的题外话（外卖、手机铃声、旁白）
- 明显技术故障（麦克风调试、重录片段）
- 时长超过3秒且无实质内容的停顿段

将结果写入 `output/EP_DIR/2_analysis/rough_cuts.json`：

```json
{
  "deletes": [
    {
      "start_ms": 0,
      "end_ms": 45000,
      "level": "rough",
      "reason": "录前闲聊：测麦克风、寒暄",
      "source": "agent_rough",
      "confidence": 0.95
    }
  ]
}
```

规则优先级：保守原则优先，宁可少删不要误删（`confidence` < 0.7 的不放入）。

#### 2.2 精剪（词/句级）

在粗剪标记的区间之外，逐句检查仍需删除的细节：
- 高频口头禅（"嗯"、"啊"、"对对对"、"然后然后然后"）
- 同一观点30秒内用几乎相同措辞重复，删去重复
- "怎么说呢"、"就是那种"等开头无实质内容的句子

将结果写入 `output/EP_DIR/2_analysis/fine_cuts.json`：

```json
{
  "deletes": [
    {
      "start_ms": 12340,
      "end_ms": 12890,
      "level": "fine",
      "reason": "口头禅：句首嗯",
      "source": "agent_fine",
      "confidence": 0.85
    }
  ]
}
```

**不删除**：情感停顿、自然思考停顿（<1.5s）、短时对话节奏词（"对"/"嗯嗯" <1s）、故意强调的重复。

#### 2.3 自审

回顾粗剪和精剪建议，检查：
- 有无误删（false positive）——不该删的被删了？
- 有无遗漏（false negative）——应该删的没删？

将结果写入 `output/EP_DIR/2_analysis/self_review.json`：

```json
{
  "deletes": [
    {
      "start_ms": 180000,
      "end_ms": 182000,
      "level": "fine",
      "reason": "遗漏：纯填充句无实质内容",
      "source": "agent_self_review",
      "confidence": 0.8
    }
  ],
  "flags": [
    {
      "start_ms": 30000,
      "end_ms": 75000,
      "flag": "false_positive",
      "reason": "误判为题外话，实为对主题的铺垫"
    }
  ],
  "summary": "共审查23条建议，标记1条误删（30-75s），补充1条遗漏（180-182s）"
}
```

三个文件写完后，运行第三步。

---

### 第三步：生成审查界面 + 剪辑

```bash
python shared/scripts/run_pipeline.py --ep-dir output/2026-05-08-ep01 --resume
```

流水线自动：
- 生成 `review_enhanced.html`（含所有删除建议）
- 打印：启动审查服务器的命令，等待人工审查

人工审查：

```bash
python shared/scripts/review_server.py --ep-dir output/2026-05-08-ep01 --port 5050
# 浏览器打开打印出的 review_enhanced.html 路径
# 审查建议删除内容，点击 Export → 自动保存 delete_segments_edited.json
```

审查完成后再次运行：

```bash
python shared/scripts/run_pipeline.py --ep-dir output/2026-05-08-ep01 --resume
```

输出：`output/2026-05-08-ep01/4_cut/cut.wav`

## 重新运行与续传

每个阶段检测输出是否已存在，已完成的阶段自动跳过。在任意阶段中断后重新运行即可续传。

若需重跑分析，删除 `2_analysis/` 目录后重新运行流水线：

```bash
rm -rf output/EP_DIR/2_analysis
python shared/scripts/run_pipeline.py --ep-dir output/EP_DIR
```

## 常见错误

| 错误 | 原因 | 处理 |
|------|------|------|
| Volcano `45000001` | API key 无效 | 检查 `.env` 中的 Volcano 配置 |
| Volcano `45000132` | 音频超 512 MB | 先用 ffmpeg 转为 16kHz mono mp3 |
| uguu.se 上传失败 | 文件过大或网络问题 | 重试，或配置 TOS/S3 |
| `silence trap` | 输出几乎全静音 | 检查输入文件是否包含有效音频 |
| `Agent analysis not complete` | 三个分析 JSON 尚未写入 | 按第二步写完三个文件后再 `--resume` |
| `delete_segments_edited.json not found` | 审查未完成 | 在浏览器中点击 Export 后再 `--resume` |

## 各阶段详情

- [阶段1 转录](../../docs/剪播客/阶段1-转录.md)
- [阶段2 分析](../../docs/剪播客/阶段2-分析.md)
- [阶段3 审查](../../docs/剪播客/阶段3-审查.md)
- [阶段4 剪辑](../../docs/剪播客/阶段4-剪辑.md)
```

- [ ] **Step 2: Update `.codex/skills/podcast-cut-剪播客/SKILL.md`**

Replace with:

```markdown
---
name: podcast-cut-剪播客
description: 播客剪辑技能 — 三步：转录→分析→剪辑
---

# /podcast-cut-剪播客

## 前提

`.env` 已配置 `VOLC_API_KEY`（或 `VOLC_APP_KEY` + `VOLC_ACCESS_KEY`）。

## 三步流程

**第一步：转录（自动，~5-30分钟）**

```bash
python shared/scripts/run_pipeline.py \
  --ep-dir output/EP_ID \
  --track1 recordings/host.wav \
  [--track2 recordings/guest.wav] \
  [--align clap|timestamp] [--t1 HH:MM:SS --t2 HH:MM:SS]
```

结束时打印 `analysis_context.md` 路径，等待分析。

**第二步：你做分析（三轮）**

读取 `EP_DIR/2_analysis/analysis_context.md`，写入三个 JSON：

1. `rough_cuts.json` — 粗剪（内容级，录前闲聊、题外话、技术故障）
2. `fine_cuts.json` — 精剪（词级，口头禅、冗余解释）
3. `self_review.json` — 自审（检查误删和遗漏）

格式见 `analysis_context.md` 中的"输出格式要求"节。所有字段：`start_ms`、`end_ms`、`level`、`reason`、`source`、`confidence`。

**第三步：审查 + 剪辑（两次 --resume）**

```bash
# 第一次：生成 HTML 审查界面
python shared/scripts/run_pipeline.py --ep-dir output/EP_ID --resume

# 人工审查（浏览器）
python shared/scripts/review_server.py --ep-dir output/EP_ID --port 5050
# 点击 Export → 保存 delete_segments_edited.json

# 第二次：生成 cut.wav
python shared/scripts/run_pipeline.py --ep-dir output/EP_ID --resume
```

输出：`output/EP_ID/4_cut/cut.wav`

## 续传

所有阶段幂等。中断后重新运行同样命令即可续传。

## 常见错误

| 错误 | 处理 |
|------|------|
| Volcano `45000001` | 检查 VOLC_API_KEY |
| Volcano `45000132` | 音频超 512MB，先转码 |
| `Agent analysis not complete` | 写完三个 JSON 后再 --resume |
| `delete_segments_edited.json not found` | 在浏览器点击 Export |
```

- [ ] **Step 3: Verify SKILL.md loads correctly (no syntax errors)**

```bash
python -c "import yaml; yaml.safe_load(open('.claude/skills/podcast-cut-剪播客/SKILL.md').read().split('---')[1])"
```

Expected: no error.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/podcast-cut-剪播客/SKILL.md .codex/skills/podcast-cut-剪播客/SKILL.md
git commit -m "docs: SKILL.md — agent does analysis directly, no LLM API"
```

---

## Task 5: Update docs, README, AGENTS.md

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/剪播客/快速上手.md`

- [ ] **Step 1: Update `README.md` required variables table**

Replace the "Required variables at minimum" table:

```markdown
| Variable | Purpose |
|----------|---------|
| `VOLC_API_KEY` | Volcano Engine ASR authentication |
| `VOLC_RESOURCE_ID` | Set to `volc.seedasr.auc` |
```

Remove the `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` rows.

Update the `.env.example` mention in Step 4 to:

```bash
cp .env.example .env
# Edit .env and fill in VOLC_API_KEY (and VOLC_RESOURCE_ID if needed)
```

Update the Quick Start section to show three commands:

```bash
# Step 1: Transcription (automatic, ~5–20 min)
python shared/scripts/run_pipeline.py \
  --ep-dir output/2026-05-08-ep01 \
  --track1 recordings/host.wav \
  --track2 recordings/guest.wav

# Step 2: You (the agent) read analysis_context.md and write three analysis JSONs
# See SKILL.md for detailed instructions

# Step 3a: Resume after analysis → generates review HTML
python shared/scripts/run_pipeline.py --ep-dir output/2026-05-08-ep01 --resume
# Review in browser, click Export

# Step 3b: Resume after human review → cut.wav
python shared/scripts/run_pipeline.py --ep-dir output/2026-05-08-ep01 --resume
# Result: output/2026-05-08-ep01/4_cut/cut.wav
```

- [ ] **Step 2: Update `AGENTS.md` stage outputs table**

Replace the stage 2 rows to show `analysis_context.md` and remove the three LLM script rows:

```markdown
| Path | Written by |
|------|------------|
| `input/audio_meta.json` | prepare_audio.py |
| `input/track_offsets_ms` (in audio_meta.json) | align_tracks.py |
| `1_transcribe/words.json` | transcribe_merge.py |
| `1_transcribe/sentences.json` | make_sentences.py |
| `2_analysis/analysis_context.md` | build_analysis_context.py |
| `2_analysis/rough_cuts.json` | **Agent** (reads analysis_context.md) |
| `2_analysis/fine_cuts.json` | **Agent** (reads analysis_context.md) |
| `2_analysis/self_review.json` | **Agent** (reads analysis_context.md) |
| `3_review/review_enhanced.html` | generate_review_html.py |
| `3_review/delete_segments_edited.json` | review_server.py (POST /export) |
| `4_cut/cut.wav` | cut_audio.py + trim_silences.py |
```

Remove `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` from the key files list.

- [ ] **Step 3: Update `docs/剪播客/快速上手.md`**

Update the "标准流程" section to show three steps:

1. **第一步：运行流水线（转录）** — same as before but note it stops at "agent analysis required"
2. **第二步：AI 分析（你来做）** — read `analysis_context.md`, write three JSONs (with format examples from SKILL.md)
3. **第三步：审查 + 剪辑** — two `--resume` calls

Update the "续传与幂等性" section to mention `2_analysis/` is where agent files live.

Update the common errors table to add `Agent analysis not complete` entry.

Remove any mention of `LLM_API_KEY` from prerequisites section.

- [ ] **Step 4: Run full test suite one final time**

```bash
python -m pytest tests/ -v 2>&1 | tail -10
```

Expected: all tests pass.

- [ ] **Step 5: Commit and tag**

```bash
git add README.md AGENTS.md docs/剪播客/快速上手.md
git commit -m "docs: update for agent-native analysis — no LLM API required"
git tag v0.3.0-agent-native
git push && git push --tags
```

---

## Self-Review

**Spec coverage:**
1. ✅ Remove doubao/Ark API → Task 2 (delete scripts + config)
2. ✅ Agent does analysis → Task 4 (SKILL.md with three-round instructions)
3. ✅ Build context package for agent → Task 1 (`build_analysis_context.py`)
4. ✅ Pipeline pauses correctly → Task 3 (`run_pipeline.py` two-pause-point)
5. ✅ Data contract unchanged (JSON format preserved) → Data Contracts section
6. ✅ Tests updated → Tasks 1, 2, 3
7. ✅ Docs updated → Task 5

**Placeholder scan:** None found. All code blocks are complete.

**Type consistency:**
- `analysis_context.md` is the sentinel file for "stage 2.0 complete" throughout all tasks ✅
- `self_review.json` is the sentinel for "agent analysis complete" throughout all tasks ✅
- `rough_cuts.json`/`fine_cuts.json` format (`level: "rough"/"fine"`, `source: "agent_rough"/"agent_fine"`) consistent across Task 1 output format spec, Task 4 SKILL.md examples, and Task 5 AGENTS.md ✅
