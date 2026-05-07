# Podcast Cutter Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared library, test infrastructure, and reviewer-agent scaffolding that every later script depends on. After this plan, the project has a runnable Volcano client, an upload abstraction, an ffmpeg wrapper that catches the −91 dB silence trap, audio constants, JSON I/O helpers, full pytest scaffolding with fixtures, four reviewer-subagent stubs, and a working `/podcast-cut-安装` skill.

**Architecture:** Pure-Python library at `shared/scripts/lib/` with one module per responsibility. Each module is unit-tested in isolation via pytest. External services (Volcano API, S3, ffmpeg) are mocked in tests; integration smoke tests run only when explicit env flags are set. Reviewer agents live as plain `.md` files in `.claude/agents/` with frontmatter declaring scope.

**Tech Stack:** Python 3.10+, pytest, ffmpeg (CLI), requests (Volcano + uguu), boto3 (S3-compat), python-dotenv (`.env` loader). Node only enters in Plan 3 (review HTML server) — no Node dependency in Foundation.

---

## File Structure

After this plan executes, the repo will contain:

```
podcast-cutter-skills/
├── .claude/
│   ├── agents/                              # NEW
│   │   ├── spec-drift-reviewer.md
│   │   ├── ffmpeg-invariants-reviewer.md
│   │   ├── prompt-eval-reviewer.md
│   │   └── listening-spot-check-reviewer.md
│   └── skills/                              # NEW
│       └── podcast-cut-安装/
│           └── SKILL.md
├── shared/                                  # NEW
│   ├── scripts/
│   │   ├── __init__.py
│   │   ├── lib/
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   ├── json_io.py
│   │   │   ├── audio_constants.py
│   │   │   ├── volcano_client.py
│   │   │   ├── upload.py
│   │   │   └── ffmpeg_wrap.py
│   │   └── install/
│   │       ├── check_deps.sh
│   │       ├── fetch_assets.sh
│   │       └── verify_volcano.py
│   ├── test_fixtures/
│   │   ├── README.md
│   │   ├── silence_only/
│   │   │   └── silence_5s.wav             # generated, committed
│   │   ├── tiny_1track/
│   │   │   └── README.md                  # placeholder until user supplies
│   │   ├── tiny_2track/
│   │   │   └── README.md
│   │   └── over_512mb_simulated/
│   │       └── README.md
│   └── assets/
│       └── music/
│           └── README.md                  # bundled music arrives in Plan 4
├── tests/                                   # NEW
│   ├── __init__.py
│   ├── conftest.py
│   ├── lib/
│   │   ├── __init__.py
│   │   ├── test_config.py
│   │   ├── test_json_io.py
│   │   ├── test_audio_constants.py
│   │   ├── test_volcano_client.py
│   │   ├── test_upload.py
│   │   └── test_ffmpeg_wrap.py
│   └── install/
│       └── test_check_deps.py
├── .env.example                             # NEW
├── pyproject.toml                           # NEW
├── pytest.ini                               # NEW (or in pyproject.toml)
└── docs/
    └── superpowers/
        ├── specs/2026-05-07-podcast-cutter-mvp-design.md  # already exists
        └── plans/2026-05-07-podcast-cutter-foundation.md  # this file
```

**File responsibility matrix:**

| File | Owns | Imports |
|---|---|---|
| `lib/config.py` | Loads `.env` once via dotenv; exposes typed config object (`cfg.volcano_api_key`, `cfg.upload_backend`, etc.); validates required keys | `os`, `dotenv`, `dataclasses` |
| `lib/json_io.py` | Atomic JSON read/write with schema-shaped helpers (`load_words_json`, `dump_manifest`, etc.). Atomic write = write to `<path>.tmp` then `rename` | `json`, `pathlib` |
| `lib/audio_constants.py` | All tunable defaults: `SPLICE_XFADE_MS=25`, `LUFS_TARGET=-16`, `TRUE_PEAK_DB=-1.5`, `LRA=11`, `MIN_QUOTE_COUNT=4`, etc. Pure dataclass, no behavior | (none) |
| `lib/volcano_client.py` | Header building (auto old-vs-new console), error code matrix, polling loop. Pure logic; HTTP is injected | `requests` (only at boundary) |
| `lib/upload.py` | Fallback chain TOS → S3 → uguu. Each backend is a class implementing `upload(path) -> url`. Selector is `cfg.upload_backend` or auto-detect | `boto3` (lazy), `requests` |
| `lib/ffmpeg_wrap.py` | `run_ffmpeg(args, log_path)` that captures stderr to file, surfaces last 20 lines on error, runs `volumedetect` on output, asserts `max_volume > -10 dB` | `subprocess`, `re` |

---

## Self-Contained Conventions

- **All paths in code use `pathlib.Path`**, never strings.
- **Time fields are integer milliseconds** end-to-end, per spec §4.
- **Errors use specific exception types** (`VolcanoError`, `UploadError`, `FFmpegError`) with `.code` and `.context` attrs — no bare `Exception`.
- **Tests use real temp dirs** (`tmp_path` fixture), not in-memory mocks where filesystem behavior matters.
- **Every commit is preceded by a passing test run.**

---

## Tasks

### Task 1: Repository scaffolding and pytest config

**Files:**
- Create: `pyproject.toml`
- Create: `pytest.ini`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `shared/scripts/__init__.py`
- Create: `shared/scripts/lib/__init__.py`
- Create: `shared/test_fixtures/README.md`
- Create: `shared/test_fixtures/tiny_1track/README.md`
- Create: `shared/test_fixtures/tiny_2track/README.md`
- Create: `shared/test_fixtures/over_512mb_simulated/README.md`
- Create: `shared/assets/music/README.md`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "podcast-cutter-skills"
version = "0.1.0"
description = "AI podcast cutter skills (Chinese, Volcano ASR)"
requires-python = ">=3.10"
dependencies = [
    "python-dotenv>=1.0.0",
    "requests>=2.31.0",
    "boto3>=1.34.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4",
    "pytest-cov>=4.1",
]

[tool.setuptools.packages.find]
where = ["shared/scripts"]
```

- [ ] **Step 2: Write `pytest.ini`**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -ra --strict-markers
markers =
    integration: tests that hit real external services (skipped without --integration flag)
    requires_audio_fixture: tests that need user-supplied audio fixtures
filterwarnings =
    error
    ignore::DeprecationWarning:boto3.*
    ignore::DeprecationWarning:botocore.*
```

- [ ] **Step 3: Write `tests/conftest.py`**

```python
"""Shared pytest fixtures for the podcast cutter test suite."""
from __future__ import annotations

from pathlib import Path

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="run tests marked @pytest.mark.integration (hits real services)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--integration"):
        return
    skip = pytest.mark.skip(reason="needs --integration to run")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def repo_root() -> Path:
    """Absolute path to the repo root, regardless of cwd."""
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def fixtures_dir(repo_root: Path) -> Path:
    return repo_root / "shared" / "test_fixtures"
```

- [ ] **Step 4: Write the empty package init files**

`tests/__init__.py`:
```python
```

`shared/scripts/__init__.py`:
```python
```

`shared/scripts/lib/__init__.py`:
```python
"""Podcast cutter shared library."""
```

- [ ] **Step 5: Write fixtures README files**

`shared/test_fixtures/README.md`:
```markdown
# Test fixtures

| Dir | Purpose | Source |
|---|---|---|
| `tiny_2track/` | 60s 2-track sample for end-to-end integration tests | user-supplied; commit only after consent |
| `tiny_1track/` | same content merged; tests speaker diarization path | user-supplied |
| `silence_only/` | exercises Volcano `20000003` silent-audio error | generated by Task 1 (committed) |
| `over_512mb_simulated/` | exercises pre-upload size guard | synthesized at test time, not committed |

The `silence_only/silence_5s.wav` file is generated by the script at the bottom of this README and is the only fixture committed to git.

To regenerate `silence_5s.wav`:

\`\`\`bash
ffmpeg -y -f lavfi -i anullsrc=r=16000:cl=mono -t 5 -c:a pcm_s16le shared/test_fixtures/silence_only/silence_5s.wav
\`\`\`
```

`shared/test_fixtures/tiny_1track/README.md`:
```markdown
Place a 60s single-track Chinese podcast sample here as `merged.mp3`, and the golden `words.json`, `delete_segments_edited.json`, and `final.mp3` checksums alongside. Add files only after recording consent has been confirmed.
```

`shared/test_fixtures/tiny_2track/README.md`:
```markdown
Place 60s 2-track samples here as `track1.wav` and `track2.wav`. Add golden `words.json`, `delete_segments_edited.json`, and `final.mp3` checksum once Plans 2-4 have shipped.
```

`shared/test_fixtures/over_512mb_simulated/README.md`:
```markdown
This directory stays empty. Tests synthesize the >512MB file at runtime to avoid bloating the repo.
```

`shared/assets/music/README.md`:
```markdown
Bundled royalty-free intro/outro music will be placed here by `shared/scripts/install/fetch_assets.sh` (Plan 1, Task 12). Do NOT commit copyrighted music.
```

- [ ] **Step 6: Generate the silence fixture**

Run:
```bash
ffmpeg -y -f lavfi -i anullsrc=r=16000:cl=mono -t 5 -c:a pcm_s16le shared/test_fixtures/silence_only/silence_5s.wav
```
Expected: file `shared/test_fixtures/silence_only/silence_5s.wav` exists and is ~160 KB. Verify:
```bash
ls -la shared/test_fixtures/silence_only/silence_5s.wav
```

- [ ] **Step 7: Verify pytest discovers nothing yet (passes vacuously)**

Run: `python -m pytest`
Expected: `no tests ran` exit 5, OR `0 passed`. Either is fine; the point is pytest is configured.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml pytest.ini tests/__init__.py tests/conftest.py \
  shared/scripts/__init__.py shared/scripts/lib/__init__.py \
  shared/test_fixtures/README.md \
  shared/test_fixtures/tiny_1track/README.md \
  shared/test_fixtures/tiny_2track/README.md \
  shared/test_fixtures/over_512mb_simulated/README.md \
  shared/test_fixtures/silence_only/silence_5s.wav \
  shared/assets/music/README.md
git commit -m "$(cat <<'EOF'
chore: scaffold pyproject, pytest, fixtures dirs

Foundation for TDD on shared/scripts/lib/. Includes the silence_5s.wav
fixture (16kHz mono PCM, 5s) used by Volcano error-path tests.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `lib/audio_constants.py` (no-behavior leaf, do this first)

Trivial module with no dependencies. Doing it first means every later test can import constants instead of hard-coding magic numbers.

**Files:**
- Create: `shared/scripts/lib/audio_constants.py`
- Create: `tests/lib/__init__.py`
- Test: `tests/lib/test_audio_constants.py`

- [ ] **Step 1: Write the failing test**

`tests/lib/__init__.py`:
```python
```

`tests/lib/test_audio_constants.py`:
```python
"""Tests for shared.scripts.lib.audio_constants."""
from __future__ import annotations

from shared.scripts.lib import audio_constants as ac


def test_lufs_target_is_apple_podcasts_compatible() -> None:
    assert ac.LUFS_TARGET == -16
    assert ac.TRUE_PEAK_DB == -1.5
    assert ac.LRA == 11


def test_splice_xfade_is_25_ms() -> None:
    assert ac.SPLICE_XFADE_MS == 25


def test_golden_quote_count_is_4_to_5() -> None:
    assert ac.MIN_QUOTE_COUNT == 4
    assert ac.MAX_QUOTE_COUNT == 5
    assert ac.MIN_QUOTE_COUNT < ac.MAX_QUOTE_COUNT


def test_volume_check_threshold_catches_silence_trap() -> None:
    """podcastcut 反馈记录 2026-02-02: -91 dB silence after a bad cut."""
    assert ac.MIN_OUTPUT_PEAK_DB == -10  # any quieter is suspicious


def test_constants_are_immutable_frozen_module() -> None:
    """Constants module should not have setters or behavior."""
    with_callable = [
        name for name in dir(ac)
        if not name.startswith("_") and callable(getattr(ac, name))
    ]
    assert with_callable == [], f"audio_constants must be data-only: {with_callable}"
```

- [ ] **Step 2: Run the failing test**

Run: `python -m pytest tests/lib/test_audio_constants.py -v`
Expected: FAIL with `ModuleNotFoundError` or `AttributeError`.

- [ ] **Step 3: Write the minimal implementation**

`shared/scripts/lib/audio_constants.py`:
```python
"""Tunable audio defaults for the podcast cutter pipeline.

This module is intentionally data-only: no functions, no classes with methods.
Every constant should have a citation in either the spec
(docs/superpowers/specs/2026-05-07-podcast-cutter-mvp-design.md) or
docs/后期/反馈记录.md once that file is ported.
"""
from __future__ import annotations

# Loudness target (Apple Podcasts / spec §5.3 step 5.1).
LUFS_TARGET: int = -16
TRUE_PEAK_DB: float = -1.5
LRA: int = 11

# Sample-accurate splice (spec §4.4: cut_audio.py crossfade per splice).
SPLICE_XFADE_MS: int = 25

# Inter-quote crossfade in the opening montage (spec §5.3 step 6.3 #3).
MONTAGE_XFADE_MS: int = 400

# Main-body to outro crossfade (spec §5.3 step 6.3 #6).
OUTRO_XFADE_MS: int = 3000

# Per-quote in/out micro-fade to prevent click/pop (spec §5.3 step 6.3 #2).
QUOTE_FADE_IN_MS: int = 30
QUOTE_FADE_OUT_MS: int = 50

# Continuous music bed levels (spec §5.3 step 6.3 #4 / podcastcut 反馈记录 2026-02-21).
MUSIC_BED_VOICE_LEVEL: float = 0.08
MUSIC_BED_TRANSITION_LEVEL: float = 1.0
MUSIC_BED_RAMP_MS: int = 1500

# Golden quote count invariants (spec §4.6 / §5.3 step 6.3 #1).
MIN_QUOTE_COUNT: int = 4
MAX_QUOTE_COUNT: int = 5

# Cut-point silence detection (spec §5.4 / podcastcut 质检 Layer A).
CUT_POINT_SILENCE_MS: int = 300

# Head/tail trim threshold (spec §5.2 stage 4.1 trim_silences).
TRIM_HEAD_TAIL_MS: int = 200

# Output sanity check (podcastcut 反馈记录 2026-02-02 -91 dB trap).
MIN_OUTPUT_PEAK_DB: float = -10

# Volcano hard limits (docs/volcano_asr.md error 45000132).
VOLCANO_MAX_AUDIO_BYTES: int = 512 * 1024 * 1024  # 512 MB

# Output encoding (spec §2 final.mp3 192 VBR).
MP3_OUTPUT_BITRATE: str = "192k"
MP3_OUTPUT_VBR: str = "2"  # ffmpeg libmp3lame -q:a 2 ≈ V0
```

- [ ] **Step 4: Run the test to verify pass**

Run: `python -m pytest tests/lib/test_audio_constants.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add shared/scripts/lib/audio_constants.py tests/lib/__init__.py tests/lib/test_audio_constants.py
git commit -m "$(cat <<'EOF'
feat(lib): audio_constants with TDD-locked defaults

Every constant cited from spec or podcastcut 反馈记录. Data-only module —
test asserts no callables present so it can never grow behavior.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `lib/json_io.py` — atomic JSON read/write helpers

**Files:**
- Create: `shared/scripts/lib/json_io.py`
- Test: `tests/lib/test_json_io.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for shared.scripts.lib.json_io."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from shared.scripts.lib import json_io


def test_dump_and_load_roundtrip(tmp_path: Path) -> None:
    payload = {"speakers": [{"id": "S1", "name": None}], "duration_ms": 7200000}
    target = tmp_path / "out.json"
    json_io.dump_json(payload, target)
    assert json_io.load_json(target) == payload


def test_dump_is_atomic_against_partial_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crash mid-write must not leave a partial file at the target path.

    json_io.dump_json must write to <path>.tmp then os.replace.
    """
    target = tmp_path / "out.json"
    target.write_text(json.dumps({"old": True}))  # pre-existing good file

    real_replace = json_io.os.replace

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated crash before rename completes")

    monkeypatch.setattr(json_io.os, "replace", boom)
    with pytest.raises(RuntimeError):
        json_io.dump_json({"new": True}, target)

    # Original file is untouched.
    assert json.loads(target.read_text()) == {"old": True}
    # No stray .tmp file blocks future writes.
    monkeypatch.setattr(json_io.os, "replace", real_replace)
    json_io.dump_json({"new": True}, target)
    assert json_io.load_json(target) == {"new": True}


def test_dump_ensures_chinese_text_not_escaped(tmp_path: Path) -> None:
    target = tmp_path / "zh.json"
    json_io.dump_json({"text": "做播客最难的不是开始"}, target)
    raw = target.read_text(encoding="utf-8")
    assert "做播客" in raw
    assert "\\u" not in raw  # no escape of CJK


def test_dump_creates_parent_dirs(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "nested" / "out.json"
    json_io.dump_json({"k": 1}, target)
    assert target.exists()


def test_load_missing_file_raises_filenotfound(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        json_io.load_json(tmp_path / "nope.json")
```

- [ ] **Step 2: Run the failing test**

Run: `python -m pytest tests/lib/test_json_io.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shared.scripts.lib.json_io'`.

- [ ] **Step 3: Write the minimal implementation**

`shared/scripts/lib/json_io.py`:
```python
"""Atomic JSON read/write helpers.

Atomicity matters because a half-written words.json (megabytes of
ASR output) corrupts the entire downstream pipeline. We always write
to <path>.tmp and rename at the end.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def dump_json(payload: Any, path: Path) -> None:
    """Serialize payload to path atomically. Creates parent dirs as needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def load_json(path: Path) -> Any:
    """Read and parse JSON from path. Raises FileNotFoundError if absent."""
    return json.loads(Path(path).read_text(encoding="utf-8"))
```

- [ ] **Step 4: Run the test to verify pass**

Run: `python -m pytest tests/lib/test_json_io.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add shared/scripts/lib/json_io.py tests/lib/test_json_io.py
git commit -m "$(cat <<'EOF'
feat(lib): atomic JSON I/O with CJK preserved

dump_json writes to <path>.tmp then os.replace, so a crash never leaves
a partial file. ensure_ascii=False because every transcript artifact
contains Chinese — escaped \\uXXXX is unreadable in editors.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: `lib/config.py` — single `.env` loader

**Files:**
- Create: `shared/scripts/lib/config.py`
- Create: `.env.example`
- Test: `tests/lib/test_config.py`

- [ ] **Step 1: Write `.env.example`**

```bash
# ----- Volcano Engine ASR -----
# New console (preferred): a single API key.
# Get from: https://console.volcengine.com/speech/new/setting/apikeys
# Leave VOLC_APP_KEY / VOLC_ACCESS_KEY empty if VOLC_API_KEY is set.
VOLC_API_KEY=

# Old console: paired App ID + Access Token.
# Use these only if you cannot obtain a new-console key.
VOLC_APP_KEY=
VOLC_ACCESS_KEY=

# Required for both consoles. See docs/volcano_asr.md.
VOLC_RESOURCE_ID=volc.seedasr.auc

# ----- Audio upload backend -----
# Priority: TOS (Volcano Object Storage) → S3-compatible → uguu.se fallback.
# Leave all empty to fall through to uguu.se with a privacy warning.

# Volcano TOS (recommended, same vendor as ASR):
TOS_ACCESS_KEY=
TOS_SECRET_KEY=
TOS_BUCKET=
TOS_ENDPOINT=

# S3-compatible (Cloudflare R2, AWS S3, Aliyun OSS in S3 mode):
S3_ENDPOINT=
S3_BUCKET=
S3_ACCESS_KEY=
S3_SECRET_KEY=
S3_REGION=auto

# ----- Optional: AI listening review (Plan 5) -----
# Used by qc_ai_listen.py and listening-spot-check-reviewer.
GEMINI_API_KEY=
```

- [ ] **Step 2: Write the failing test**

`tests/lib/test_config.py`:
```python
"""Tests for shared.scripts.lib.config."""
from __future__ import annotations

from pathlib import Path

import pytest

from shared.scripts.lib import config


def test_load_picks_new_console_api_key(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "VOLC_API_KEY=newkey\n"
        "VOLC_RESOURCE_ID=volc.seedasr.auc\n"
    )
    cfg = config.load(env_path=env)
    assert cfg.volcano.api_key == "newkey"
    assert cfg.volcano.console == "new"
    assert cfg.volcano.app_key is None
    assert cfg.volcano.access_key is None


def test_load_picks_old_console_when_only_pair_present(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "VOLC_APP_KEY=appid\n"
        "VOLC_ACCESS_KEY=token\n"
        "VOLC_RESOURCE_ID=volc.seedasr.auc\n"
    )
    cfg = config.load(env_path=env)
    assert cfg.volcano.console == "old"
    assert cfg.volcano.app_key == "appid"
    assert cfg.volcano.access_key == "token"
    assert cfg.volcano.api_key is None


def test_load_prefers_new_when_both_present(tmp_path: Path) -> None:
    """If user has both old and new creds, new wins (per spec §7 #11)."""
    env = tmp_path / ".env"
    env.write_text(
        "VOLC_API_KEY=newkey\n"
        "VOLC_APP_KEY=appid\n"
        "VOLC_ACCESS_KEY=token\n"
        "VOLC_RESOURCE_ID=volc.seedasr.auc\n"
    )
    cfg = config.load(env_path=env)
    assert cfg.volcano.console == "new"
    assert cfg.volcano.api_key == "newkey"


def test_load_raises_when_no_volcano_creds(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("VOLC_RESOURCE_ID=volc.seedasr.auc\n")
    with pytest.raises(config.ConfigError) as exc:
        config.load(env_path=env)
    assert "VOLC_API_KEY" in str(exc.value)


def test_load_raises_when_old_console_pair_incomplete(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "VOLC_APP_KEY=appid\n"
        "VOLC_RESOURCE_ID=volc.seedasr.auc\n"
        # missing VOLC_ACCESS_KEY
    )
    with pytest.raises(config.ConfigError) as exc:
        config.load(env_path=env)
    assert "VOLC_ACCESS_KEY" in str(exc.value)


def test_upload_backend_is_tos_when_tos_keys_present(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "VOLC_API_KEY=newkey\nVOLC_RESOURCE_ID=volc.seedasr.auc\n"
        "TOS_ACCESS_KEY=ak\nTOS_SECRET_KEY=sk\n"
        "TOS_BUCKET=b\nTOS_ENDPOINT=https://tos.example\n"
    )
    cfg = config.load(env_path=env)
    assert cfg.upload_backend == "tos"


def test_upload_backend_is_s3_when_only_s3_keys_present(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "VOLC_API_KEY=newkey\nVOLC_RESOURCE_ID=volc.seedasr.auc\n"
        "S3_ENDPOINT=https://r2.example\nS3_BUCKET=b\n"
        "S3_ACCESS_KEY=ak\nS3_SECRET_KEY=sk\n"
    )
    cfg = config.load(env_path=env)
    assert cfg.upload_backend == "s3"


def test_upload_backend_is_uguu_when_no_storage_keys(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("VOLC_API_KEY=newkey\nVOLC_RESOURCE_ID=volc.seedasr.auc\n")
    cfg = config.load(env_path=env)
    assert cfg.upload_backend == "uguu"


def test_load_missing_env_file_raises(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError) as exc:
        config.load(env_path=tmp_path / "nope.env")
    assert "not found" in str(exc.value).lower()
```

- [ ] **Step 3: Run the failing test**

Run: `python -m pytest tests/lib/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 4: Write the minimal implementation**

`shared/scripts/lib/config.py`:
```python
"""Single .env loader for the podcast cutter library.

Replaces the scattered env handling found in podcastcut-skills (some
scripts read .env, some os.environ, some --flag). Every script imports
config.load() and uses cfg.volcano.api_key / cfg.upload_backend / etc.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from dotenv import dotenv_values


class ConfigError(Exception):
    """Raised when required env vars are missing or malformed."""


@dataclass(frozen=True)
class VolcanoConfig:
    console: Literal["new", "old"]
    api_key: Optional[str]
    app_key: Optional[str]
    access_key: Optional[str]
    resource_id: str


@dataclass(frozen=True)
class TOSConfig:
    access_key: str
    secret_key: str
    bucket: str
    endpoint: str


@dataclass(frozen=True)
class S3Config:
    endpoint: str
    bucket: str
    access_key: str
    secret_key: str
    region: str


@dataclass(frozen=True)
class Config:
    volcano: VolcanoConfig
    tos: Optional[TOSConfig]
    s3: Optional[S3Config]
    gemini_api_key: Optional[str]
    upload_backend: Literal["tos", "s3", "uguu"]


def _nonempty(d: dict[str, str | None], key: str) -> Optional[str]:
    v = d.get(key)
    return v if v else None


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


def _build_volcano(raw: dict[str, str | None]) -> VolcanoConfig:
    api_key = _nonempty(raw, "VOLC_API_KEY")
    app_key = _nonempty(raw, "VOLC_APP_KEY")
    access_key = _nonempty(raw, "VOLC_ACCESS_KEY")
    resource_id = _nonempty(raw, "VOLC_RESOURCE_ID") or "volc.seedasr.auc"

    if api_key:
        return VolcanoConfig(
            console="new",
            api_key=api_key,
            app_key=None,
            access_key=None,
            resource_id=resource_id,
        )
    if app_key and access_key:
        return VolcanoConfig(
            console="old",
            api_key=None,
            app_key=app_key,
            access_key=access_key,
            resource_id=resource_id,
        )
    if app_key and not access_key:
        raise ConfigError("VOLC_APP_KEY set but VOLC_ACCESS_KEY missing")
    if access_key and not app_key:
        raise ConfigError("VOLC_ACCESS_KEY set but VOLC_APP_KEY missing")
    raise ConfigError(
        "no Volcano credentials. Set VOLC_API_KEY (new console, preferred) "
        "or VOLC_APP_KEY + VOLC_ACCESS_KEY (old console)."
    )


def _build_tos(raw: dict[str, str | None]) -> Optional[TOSConfig]:
    keys = ["TOS_ACCESS_KEY", "TOS_SECRET_KEY", "TOS_BUCKET", "TOS_ENDPOINT"]
    vals = [_nonempty(raw, k) for k in keys]
    if all(vals):
        return TOSConfig(
            access_key=vals[0],  # type: ignore[arg-type]
            secret_key=vals[1],  # type: ignore[arg-type]
            bucket=vals[2],  # type: ignore[arg-type]
            endpoint=vals[3],  # type: ignore[arg-type]
        )
    return None


def _build_s3(raw: dict[str, str | None]) -> Optional[S3Config]:
    required = ["S3_ENDPOINT", "S3_BUCKET", "S3_ACCESS_KEY", "S3_SECRET_KEY"]
    if all(_nonempty(raw, k) for k in required):
        return S3Config(
            endpoint=raw["S3_ENDPOINT"],  # type: ignore[arg-type]
            bucket=raw["S3_BUCKET"],  # type: ignore[arg-type]
            access_key=raw["S3_ACCESS_KEY"],  # type: ignore[arg-type]
            secret_key=raw["S3_SECRET_KEY"],  # type: ignore[arg-type]
            region=_nonempty(raw, "S3_REGION") or "auto",
        )
    return None
```

- [ ] **Step 5: Run the test to verify pass**

Run: `python -m pytest tests/lib/test_config.py -v`
Expected: 9 passed.

- [ ] **Step 6: Commit**

```bash
git add shared/scripts/lib/config.py tests/lib/test_config.py .env.example
git commit -m "$(cat <<'EOF'
feat(lib): single .env loader, prefers new Volcano console

Resolves spec §7 #10 (scattered env handling) and #11 (old vs new
console). Old-console partial-credential cases fail loudly instead of
silently falling through.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: `lib/volcano_client.py` — header building, polling, error matrix

**Files:**
- Create: `shared/scripts/lib/volcano_client.py`
- Test: `tests/lib/test_volcano_client.py`

This module is intentionally HTTP-injectable: tests pass a stub callable instead of `requests.post`. No network in unit tests.

- [ ] **Step 1: Write the failing test**

```python
"""Tests for shared.scripts.lib.volcano_client."""
from __future__ import annotations

from typing import Any

import pytest

from shared.scripts.lib import config, volcano_client


def _new_console_cfg() -> config.VolcanoConfig:
    return config.VolcanoConfig(
        console="new",
        api_key="newkey",
        app_key=None,
        access_key=None,
        resource_id="volc.seedasr.auc",
    )


def _old_console_cfg() -> config.VolcanoConfig:
    return config.VolcanoConfig(
        console="old",
        api_key=None,
        app_key="appid",
        access_key="token",
        resource_id="volc.seedasr.auc",
    )


def test_submit_headers_new_console_uses_single_api_key() -> None:
    headers = volcano_client.build_submit_headers(
        _new_console_cfg(), task_id="t-1"
    )
    assert headers["X-Api-Key"] == "newkey"
    assert headers["X-Api-Resource-Id"] == "volc.seedasr.auc"
    assert headers["X-Api-Request-Id"] == "t-1"
    assert headers["X-Api-Sequence"] == "-1"
    assert "X-Api-App-Key" not in headers
    assert "X-Api-Access-Key" not in headers


def test_submit_headers_old_console_uses_pair() -> None:
    headers = volcano_client.build_submit_headers(
        _old_console_cfg(), task_id="t-2"
    )
    assert headers["X-Api-App-Key"] == "appid"
    assert headers["X-Api-Access-Key"] == "token"
    assert "X-Api-Key" not in headers


def test_query_headers_omit_x_api_sequence() -> None:
    """Per docs/volcano_asr.md: query has no Sequence header."""
    headers = volcano_client.build_query_headers(_new_console_cfg(), task_id="t-3")
    assert "X-Api-Sequence" not in headers
    assert headers["X-Api-Request-Id"] == "t-3"


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("20000000", volcano_client.QueryStatus.SUCCESS),
        ("20000001", volcano_client.QueryStatus.PROCESSING),
        ("20000002", volcano_client.QueryStatus.QUEUED),
    ],
)
def test_classify_status_in_progress(code: str, expected: volcano_client.QueryStatus) -> None:
    assert volcano_client.classify_status(code) is expected


@pytest.mark.parametrize(
    "code",
    ["20000003", "45000001", "45000002", "45000132", "45000151"],
)
def test_classify_status_hard_fail(code: str) -> None:
    """These codes must map to HARD_FAIL with the message from the spec."""
    assert volcano_client.classify_status(code) is volcano_client.QueryStatus.HARD_FAIL


@pytest.mark.parametrize("code", ["45000131", "55000031", "5500999"])
def test_classify_status_retryable(code: str) -> None:
    assert volcano_client.classify_status(code) is volcano_client.QueryStatus.RETRYABLE


def test_message_for_silent_audio() -> None:
    msg = volcano_client.message_for_code("20000003")
    assert "无人声" in msg


def test_message_for_oversize_audio_mentions_512mb() -> None:
    msg = volcano_client.message_for_code("45000132")
    assert "512" in msg


def test_submit_payload_minimal() -> None:
    p = volcano_client.build_submit_payload(
        audio_url="https://example/audio.mp3",
        audio_format="mp3",
        uid="user-1",
        enable_speaker_info=True,
        hotwords=["热词1", "热词2"],
    )
    assert p["audio"]["url"] == "https://example/audio.mp3"
    assert p["audio"]["format"] == "mp3"
    assert p["request"]["enable_speaker_info"] is True
    assert p["user"]["uid"] == "user-1"
    # Hotwords go through corpus.context as documented JSON string.
    import json as _json
    ctx = _json.loads(p["request"]["corpus"]["context"])
    assert ctx == {"hotwords": [{"word": "热词1"}, {"word": "热词2"}]}


def test_submit_payload_omits_corpus_when_no_hotwords() -> None:
    p = volcano_client.build_submit_payload(
        audio_url="https://example/audio.mp3",
        audio_format="mp3",
        uid="user-1",
        enable_speaker_info=True,
        hotwords=[],
    )
    assert "corpus" not in p["request"]


def test_poll_until_done_returns_result_on_success() -> None:
    calls: list[int] = []

    def fake_query() -> tuple[str, dict[str, Any]]:
        calls.append(1)
        if len(calls) < 3:
            return ("20000001", {})
        return ("20000000", {"result": {"text": "ok"}})

    result = volcano_client.poll_until_done(
        fake_query, interval_seconds=0, max_attempts=10
    )
    assert result == {"result": {"text": "ok"}}
    assert len(calls) == 3


def test_poll_until_done_raises_on_hard_fail() -> None:
    def fake_query() -> tuple[str, dict[str, Any]]:
        return ("20000003", {})

    with pytest.raises(volcano_client.VolcanoError) as exc:
        volcano_client.poll_until_done(
            fake_query, interval_seconds=0, max_attempts=10
        )
    assert exc.value.code == "20000003"
    assert "无人声" in str(exc.value)


def test_poll_until_done_retries_then_gives_up() -> None:
    def fake_query() -> tuple[str, dict[str, Any]]:
        return ("55000031", {})

    with pytest.raises(volcano_client.VolcanoError) as exc:
        volcano_client.poll_until_done(
            fake_query, interval_seconds=0, max_attempts=3
        )
    assert exc.value.code == "55000031"
```

- [ ] **Step 2: Run the failing test**

Run: `python -m pytest tests/lib/test_volcano_client.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write the implementation**

`shared/scripts/lib/volcano_client.py`:
```python
"""Volcano AUC v3 big-model ASR client (header building + polling + errors).

HTTP is injected so the module is unit-testable without network.
docs/volcano_asr.md is the source of truth for endpoints, headers, codes.
"""
from __future__ import annotations

import enum
import json
import time
from dataclasses import dataclass
from typing import Any, Callable

from shared.scripts.lib.config import VolcanoConfig

SUBMIT_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
QUERY_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"


class QueryStatus(enum.Enum):
    SUCCESS = "success"
    PROCESSING = "processing"
    QUEUED = "queued"
    HARD_FAIL = "hard_fail"
    RETRYABLE = "retryable"


@dataclass
class VolcanoError(Exception):
    code: str
    message: str
    context: dict[str, Any]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"[{self.code}] {self.message}"


# Per docs/volcano_asr.md error code table.
_HARD_FAIL_CODES: dict[str, str] = {
    "20000003": "音频无人声，检查录音是否为空轨",
    "45000001": "请求参数无效（缺字段或值错误）",
    "45000002": "音频为空，先用 ffprobe 检查文件",
    "45000132": "音频超 512 MB Volcano 上限，建议先 ffmpeg 转 16 kHz mono mp3",
    "45000151": "音频格式不正确，先用 ffprobe 检查",
}

_RETRYABLE_CODES: set[str] = {
    "45000131",  # 30-min rate limit exceeded
    "55000031",  # service busy
}


def classify_status(code: str) -> QueryStatus:
    if code == "20000000":
        return QueryStatus.SUCCESS
    if code == "20000001":
        return QueryStatus.PROCESSING
    if code == "20000002":
        return QueryStatus.QUEUED
    if code in _HARD_FAIL_CODES:
        return QueryStatus.HARD_FAIL
    if code in _RETRYABLE_CODES:
        return QueryStatus.RETRYABLE
    if code.startswith("550"):
        return QueryStatus.RETRYABLE
    return QueryStatus.HARD_FAIL


def message_for_code(code: str) -> str:
    if code in _HARD_FAIL_CODES:
        return _HARD_FAIL_CODES[code]
    if code == "45000131":
        return "30 分钟内提交时长超过 500h 上限，需降低提交速度"
    if code == "55000031":
        return "服务繁忙，重试"
    if code.startswith("550"):
        return "服务内部错误，重试"
    return f"未知错误 {code}"


def _common_headers(cfg: VolcanoConfig, task_id: str) -> dict[str, str]:
    h = {
        "X-Api-Resource-Id": cfg.resource_id,
        "X-Api-Request-Id": task_id,
    }
    if cfg.console == "new":
        assert cfg.api_key is not None
        h["X-Api-Key"] = cfg.api_key
    else:
        assert cfg.app_key is not None and cfg.access_key is not None
        h["X-Api-App-Key"] = cfg.app_key
        h["X-Api-Access-Key"] = cfg.access_key
    return h


def build_submit_headers(cfg: VolcanoConfig, task_id: str) -> dict[str, str]:
    h = _common_headers(cfg, task_id)
    h["X-Api-Sequence"] = "-1"
    return h


def build_query_headers(cfg: VolcanoConfig, task_id: str) -> dict[str, str]:
    return _common_headers(cfg, task_id)


def build_submit_payload(
    *,
    audio_url: str,
    audio_format: str,
    uid: str,
    enable_speaker_info: bool,
    hotwords: list[str],
    enable_punc: bool = True,
    enable_itn: bool = True,
    enable_ddc: bool = False,
    show_utterances: bool = True,
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "model_name": "bigmodel",
        "enable_itn": enable_itn,
        "enable_punc": enable_punc,
        "enable_ddc": enable_ddc,
        "enable_speaker_info": enable_speaker_info,
        "show_utterances": show_utterances,
    }
    if hotwords:
        request["corpus"] = {
            "context": json.dumps({"hotwords": [{"word": w} for w in hotwords]})
        }
    return {
        "user": {"uid": uid},
        "audio": {"url": audio_url, "format": audio_format},
        "request": request,
    }


def poll_until_done(
    query_fn: Callable[[], tuple[str, dict[str, Any]]],
    *,
    interval_seconds: float,
    max_attempts: int,
) -> dict[str, Any]:
    """Drive a Volcano query loop until success / hard_fail / max_attempts.

    query_fn returns (status_code, response_body). Caller wires it to real HTTP.
    """
    last_code = ""
    last_body: dict[str, Any] = {}
    for _ in range(max_attempts):
        last_code, last_body = query_fn()
        status = classify_status(last_code)
        if status is QueryStatus.SUCCESS:
            return last_body
        if status is QueryStatus.HARD_FAIL:
            raise VolcanoError(
                code=last_code,
                message=message_for_code(last_code),
                context=last_body,
            )
        # PROCESSING, QUEUED, RETRYABLE → keep polling
        if interval_seconds > 0:
            time.sleep(interval_seconds)
    raise VolcanoError(
        code=last_code or "timeout",
        message=f"max_attempts={max_attempts} exceeded; last status={last_code}",
        context=last_body,
    )
```

- [ ] **Step 4: Run the test to verify pass**

Run: `python -m pytest tests/lib/test_volcano_client.py -v`
Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
git add shared/scripts/lib/volcano_client.py tests/lib/test_volcano_client.py
git commit -m "$(cat <<'EOF'
feat(lib): Volcano v3 client — headers, payload, polling, error matrix

HTTP is injected; tests run with no network. Error codes from
docs/volcano_asr.md mapped to QueryStatus + Chinese-language messages
sourced from the spec (§8.2). Hotwords flow through corpus.context as a
JSON-stringified payload per docs.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: `lib/upload.py` — TOS / S3 / uguu fallback chain

**Files:**
- Create: `shared/scripts/lib/upload.py`
- Test: `tests/lib/test_upload.py`

S3 is exercised via a stub that mimics `boto3.client("s3")`. uguu is exercised via a fake `requests.post`. TOS uses Volcano's S3-compatible API the same way (`boto3` with custom endpoint).

- [ ] **Step 1: Write the failing test**

```python
"""Tests for shared.scripts.lib.upload."""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest

from shared.scripts.lib import config, upload


def _empty_cfg(backend: str = "uguu") -> config.Config:
    volcano = config.VolcanoConfig(
        console="new",
        api_key="newkey",
        app_key=None,
        access_key=None,
        resource_id="volc.seedasr.auc",
    )
    tos = (
        config.TOSConfig(
            access_key="ak",
            secret_key="sk",
            bucket="b",
            endpoint="https://tos.example",
        )
        if backend == "tos"
        else None
    )
    s3 = (
        config.S3Config(
            endpoint="https://r2.example",
            bucket="b",
            access_key="ak",
            secret_key="sk",
            region="auto",
        )
        if backend == "s3"
        else None
    )
    return config.Config(
        volcano=volcano,
        tos=tos,
        s3=s3,
        gemini_api_key=None,
        upload_backend=backend,  # type: ignore[arg-type]
    )


def test_uguu_uploader_posts_file_and_returns_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = tmp_path / "in.wav"
    audio.write_bytes(b"fake-audio")

    captured: dict[str, Any] = {}

    class FakeResponse:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return {
                "success": True,
                "files": [{"url": "https://uguu.example/abc.wav"}],
            }

        def raise_for_status(self) -> None:
            return None

    def fake_post(url: str, files: dict[str, Any], timeout: int) -> FakeResponse:
        captured["url"] = url
        captured["files"] = files
        return FakeResponse()

    monkeypatch.setattr(upload.requests, "post", fake_post)
    uploader = upload.UguuUploader()
    url = uploader.upload(audio)
    assert url == "https://uguu.example/abc.wav"
    assert "uguu" in captured["url"]


def test_uguu_uploader_raises_on_upstream_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = tmp_path / "in.wav"
    audio.write_bytes(b"fake")

    class BadResponse:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return {"success": False, "description": "rate limited"}

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(upload.requests, "post", lambda *a, **k: BadResponse())
    with pytest.raises(upload.UploadError) as exc:
        upload.UguuUploader().upload(audio)
    assert "rate limited" in str(exc.value)


def test_s3_uploader_calls_put_object_with_presigned_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = tmp_path / "in.wav"
    audio.write_bytes(b"abc")

    captured: dict[str, Any] = {}

    class FakeS3Client:
        def upload_file(
            self, Filename: str, Bucket: str, Key: str, ExtraArgs: dict[str, Any]
        ) -> None:
            captured["filename"] = Filename
            captured["bucket"] = Bucket
            captured["key"] = Key
            captured["extra"] = ExtraArgs

        def generate_presigned_url(
            self, op: str, Params: dict[str, Any], ExpiresIn: int
        ) -> str:
            captured["presign"] = (op, Params, ExpiresIn)
            return f"https://r2.example/{Params['Bucket']}/{Params['Key']}?sig=fake"

    def fake_boto_client(*args: Any, **kwargs: Any) -> FakeS3Client:
        captured["client_args"] = (args, kwargs)
        return FakeS3Client()

    monkeypatch.setattr(upload, "_boto3_client", fake_boto_client)

    cfg = _empty_cfg("s3").s3
    assert cfg is not None
    uploader = upload.S3Uploader(cfg)
    url = uploader.upload(audio)
    assert url.startswith("https://r2.example/b/")
    assert captured["bucket"] == "b"
    assert captured["filename"] == str(audio)
    assert captured["presign"][2] == upload.PRESIGN_EXPIRES_SECONDS


def test_select_uploader_returns_tos_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _empty_cfg("tos")
    monkeypatch.setattr(upload, "_boto3_client", lambda *a, **k: object())
    uploader = upload.select_uploader(cfg)
    assert isinstance(uploader, upload.TOSUploader)


def test_select_uploader_returns_s3(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _empty_cfg("s3")
    monkeypatch.setattr(upload, "_boto3_client", lambda *a, **k: object())
    uploader = upload.select_uploader(cfg)
    assert isinstance(uploader, upload.S3Uploader)


def test_select_uploader_falls_back_to_uguu_with_warning(
    capsys: pytest.CaptureFixture[str],
) -> None:
    cfg = _empty_cfg("uguu")
    uploader = upload.select_uploader(cfg)
    assert isinstance(uploader, upload.UguuUploader)
    captured = capsys.readouterr()
    assert "uguu.se" in captured.err
    assert "私密" in captured.err or "privacy" in captured.err.lower()
```

- [ ] **Step 2: Run the failing test**

Run: `python -m pytest tests/lib/test_upload.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write the implementation**

`shared/scripts/lib/upload.py`:
```python
"""Audio upload backends: TOS → S3 → uguu.se fallback chain.

The first two require credentials; uguu.se is a public temp host
and is only used as a last resort, with a privacy warning to stderr.
TOS is exposed via Volcano's S3-compatible interface; we use boto3
for both TOS and generic S3, so the implementations share most code.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any, Protocol

import requests

from shared.scripts.lib.config import Config, S3Config, TOSConfig

UGUU_ENDPOINT = "https://uguu.se/upload"
PRESIGN_EXPIRES_SECONDS = 3600


class UploadError(Exception):
    pass


class Uploader(Protocol):
    def upload(self, path: Path) -> str: ...


def _boto3_client(service: str, **kwargs: Any) -> Any:
    """Wrapped so tests can monkeypatch without importing boto3 in test scope."""
    import boto3  # noqa: WPS433  (lazy import keeps test import-fast)

    return boto3.client(service, **kwargs)


class _S3LikeUploader:
    """Shared logic for TOS and generic S3 uploaders."""

    def __init__(
        self,
        *,
        endpoint: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str = "auto",
    ) -> None:
        self._client = _boto3_client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        self._bucket = bucket

    def upload(self, path: Path) -> str:
        path = Path(path)
        key = f"podcast-cutter/{uuid.uuid4().hex}/{path.name}"
        try:
            self._client.upload_file(
                Filename=str(path),
                Bucket=self._bucket,
                Key=key,
                ExtraArgs={"ContentType": "audio/mpeg"},
            )
        except Exception as exc:  # noqa: BLE001
            raise UploadError(f"S3-compatible upload failed: {exc}") from exc
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=PRESIGN_EXPIRES_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001
            raise UploadError(f"presign failed: {exc}") from exc


class TOSUploader(_S3LikeUploader):
    def __init__(self, cfg: TOSConfig) -> None:
        super().__init__(
            endpoint=cfg.endpoint,
            bucket=cfg.bucket,
            access_key=cfg.access_key,
            secret_key=cfg.secret_key,
        )


class S3Uploader(_S3LikeUploader):
    def __init__(self, cfg: S3Config) -> None:
        super().__init__(
            endpoint=cfg.endpoint,
            bucket=cfg.bucket,
            access_key=cfg.access_key,
            secret_key=cfg.secret_key,
            region=cfg.region,
        )


class UguuUploader:
    def upload(self, path: Path) -> str:
        path = Path(path)
        with path.open("rb") as fh:
            resp = requests.post(
                UGUU_ENDPOINT,
                files={"files[]": (path.name, fh)},
                timeout=120,
            )
        try:
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise UploadError(f"uguu HTTP error: {exc}") from exc
        if not payload.get("success"):
            raise UploadError(
                f"uguu rejected upload: {payload.get('description', payload)}"
            )
        files = payload.get("files") or []
        if not files or "url" not in files[0]:
            raise UploadError(f"uguu returned no url: {payload}")
        return files[0]["url"]


def select_uploader(cfg: Config) -> Uploader:
    if cfg.upload_backend == "tos":
        assert cfg.tos is not None
        return TOSUploader(cfg.tos)
    if cfg.upload_backend == "s3":
        assert cfg.s3 is not None
        return S3Uploader(cfg.s3)
    print(
        "[upload] WARNING: 未配置 TOS 或 S3，回退到 uguu.se 公共托管。"
        "音频会被上传到公网临时主机，私密内容请先在 .env 配置 TOS_* 或 S3_*。",
        file=sys.stderr,
    )
    return UguuUploader()
```

- [ ] **Step 4: Run the test to verify pass**

Run: `python -m pytest tests/lib/test_upload.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add shared/scripts/lib/upload.py tests/lib/test_upload.py
git commit -m "$(cat <<'EOF'
feat(lib): TOS → S3 → uguu upload fallback chain

uguu.se is the autocut-skills approach but lacks privacy semantics;
spec §7 #8 requires explicit warning. TOS uses Volcano's S3-compat
interface, so it shares the boto3 client logic with generic S3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: `lib/ffmpeg_wrap.py` — run, log, post-cut volumedetect

**Files:**
- Create: `shared/scripts/lib/ffmpeg_wrap.py`
- Test: `tests/lib/test_ffmpeg_wrap.py`

This is the only lib module that calls a real subprocess in its tests, because the −91 dB silence trap is exactly what we're guarding against and parsing real ffmpeg `volumedetect` output is the only honest test.

- [ ] **Step 1: Write the failing test**

```python
"""Tests for shared.scripts.lib.ffmpeg_wrap."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from shared.scripts.lib import audio_constants, ffmpeg_wrap

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg not installed"
)


def _silence_input(tmp_path: Path) -> Path:
    """Use the committed silence fixture rather than re-synthesizing."""
    fixture = (
        Path(__file__).resolve().parent.parent.parent
        / "shared/test_fixtures/silence_only/silence_5s.wav"
    )
    if not fixture.exists():
        pytest.skip("silence fixture not committed yet (Task 1 not run)")
    target = tmp_path / "silence.wav"
    shutil.copy(fixture, target)
    return target


def _tone_input(tmp_path: Path) -> Path:
    """A 1 kHz sine at -6 dB; safely above the silence trap."""
    out = tmp_path / "tone.wav"
    ffmpeg_wrap.run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:duration=2",
            "-af",
            "volume=0.5",
            "-c:a",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(out),
        ],
        log_path=tmp_path / "tone.log",
        skip_volumedetect=True,
    )
    return out


def test_volumedetect_parses_max_volume(tmp_path: Path) -> None:
    audio = _tone_input(tmp_path)
    peak = ffmpeg_wrap.volumedetect_max_db(audio)
    assert peak > audio_constants.MIN_OUTPUT_PEAK_DB


def test_run_ffmpeg_raises_when_output_is_silence(tmp_path: Path) -> None:
    """The whole point: a successful ffmpeg run that produces silence is a failure."""
    silence_in = _silence_input(tmp_path)
    silence_out = tmp_path / "out.wav"
    with pytest.raises(ffmpeg_wrap.FFmpegError) as exc:
        ffmpeg_wrap.run_ffmpeg(
            ["-i", str(silence_in), "-c:a", "copy", str(silence_out)],
            log_path=tmp_path / "ffmpeg.log",
        )
    assert "silence" in str(exc.value).lower() or "-91" in str(exc.value)


def test_run_ffmpeg_succeeds_for_audible_output(tmp_path: Path) -> None:
    out = tmp_path / "tone.wav"
    ffmpeg_wrap.run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:duration=1",
            "-af",
            "volume=0.5",
            "-c:a",
            "pcm_s16le",
            str(out),
        ],
        log_path=tmp_path / "tone.log",
    )
    assert out.exists()


def test_run_ffmpeg_writes_log_and_surfaces_last_lines_on_failure(
    tmp_path: Path,
) -> None:
    log = tmp_path / "ffmpeg.log"
    with pytest.raises(ffmpeg_wrap.FFmpegError) as exc:
        ffmpeg_wrap.run_ffmpeg(
            ["-i", "/no/such/file.wav", str(tmp_path / "out.wav")],
            log_path=log,
        )
    assert log.exists()
    text = exc.value.tail
    assert text  # last 20 lines surfaced
    assert "/no/such/file" in log.read_text()
```

- [ ] **Step 2: Run the failing test**

Run: `python -m pytest tests/lib/test_ffmpeg_wrap.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write the implementation**

`shared/scripts/lib/ffmpeg_wrap.py`:
```python
"""Thin ffmpeg wrapper that catches the −91 dB silence trap.

podcastcut 反馈记录 2026-02-02: a successful ffmpeg invocation that
emits a silent file is the most insidious failure mode. Every cut
pipeline writes goes through here; volumedetect verifies the output
has a peak above audio_constants.MIN_OUTPUT_PEAK_DB.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from shared.scripts.lib import audio_constants


@dataclass
class FFmpegError(Exception):
    args: list[str]
    returncode: int
    tail: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"ffmpeg failed (rc={self.returncode}):\n{self.tail}"


_VOLUMEDETECT_RE = re.compile(r"max_volume:\s*(-?\d+(?:\.\d+)?)\s*dB")


def run_ffmpeg(
    args: Sequence[str],
    *,
    log_path: Path,
    skip_volumedetect: bool = False,
) -> None:
    """Run ffmpeg; capture full stderr to log_path; verify output peak.

    The output path is assumed to be the LAST positional arg (ffmpeg convention).
    Set skip_volumedetect=True for synthesizers (sine, anullsrc) where the
    "input" is a generator and the verification step is upstream of usage.
    """
    full_args = ["ffmpeg", "-y", "-hide_banner", *args]
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    proc = subprocess.run(
        full_args,
        capture_output=True,
        text=True,
    )
    log_path.write_text(
        f"$ {' '.join(full_args)}\n\n"
        f"--- STDOUT ---\n{proc.stdout}\n"
        f"--- STDERR ---\n{proc.stderr}\n",
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise FFmpegError(
            args=list(full_args),
            returncode=proc.returncode,
            tail=_tail(proc.stderr, 20),
        )

    if skip_volumedetect:
        return
    output_path = Path(args[-1])
    peak = volumedetect_max_db(output_path)
    if peak <= audio_constants.MIN_OUTPUT_PEAK_DB:
        raise FFmpegError(
            args=list(full_args),
            returncode=0,
            tail=(
                f"silence trap: output {output_path} max_volume={peak} dB "
                f"≤ {audio_constants.MIN_OUTPUT_PEAK_DB} dB"
            ),
        )


def volumedetect_max_db(path: Path) -> float:
    """Run ffmpeg volumedetect on path and return max_volume in dB."""
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(path),
            "-af",
            "volumedetect",
            "-vn",
            "-sn",
            "-dn",
            "-f",
            "null",
            "/dev/null",
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise FFmpegError(
            args=["ffmpeg", "volumedetect", str(path)],
            returncode=proc.returncode,
            tail=_tail(proc.stderr, 20),
        )
    match = _VOLUMEDETECT_RE.search(proc.stderr)
    if not match:
        raise FFmpegError(
            args=["ffmpeg", "volumedetect", str(path)],
            returncode=proc.returncode,
            tail="volumedetect produced no max_volume line",
        )
    return float(match.group(1))


def _tail(text: str, n_lines: int) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-n_lines:])
```

- [ ] **Step 4: Run the test to verify pass**

Run: `python -m pytest tests/lib/test_ffmpeg_wrap.py -v`
Expected: 4 passed (3 if `ffmpeg` not installed — `pytestmark` skips the file).

- [ ] **Step 5: Commit**

```bash
git add shared/scripts/lib/ffmpeg_wrap.py tests/lib/test_ffmpeg_wrap.py
git commit -m "$(cat <<'EOF'
feat(lib): ffmpeg_wrap with -91 dB silence-trap guard

Every successful ffmpeg run is followed by volumedetect; if the output
peak ≤ MIN_OUTPUT_PEAK_DB (-10), we raise FFmpegError. Tests use the
committed silence fixture to exercise the failure path honestly.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Reviewer subagent stubs (no behavior yet, just signatures)

**Files:**
- Create: `.claude/agents/spec-drift-reviewer.md`
- Create: `.claude/agents/ffmpeg-invariants-reviewer.md`
- Create: `.claude/agents/prompt-eval-reviewer.md`
- Create: `.claude/agents/listening-spot-check-reviewer.md`
- Create: `tests/agents/__init__.py`
- Test: `tests/agents/test_agent_stubs.py`

These agents won't actually be functional until their dependencies (eval gold set, timeline manifest, final.mp3) exist. Stubs nail the frontmatter and reading list now, so later plans only fill in the bodies.

- [ ] **Step 1: Write the failing test**

`tests/agents/__init__.py`:
```python
```

`tests/agents/test_agent_stubs.py`:
```python
"""Verify reviewer subagent files exist with correct frontmatter."""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AGENTS_DIR = REPO_ROOT / ".claude" / "agents"


REQUIRED_AGENTS = [
    "spec-drift-reviewer",
    "ffmpeg-invariants-reviewer",
    "prompt-eval-reviewer",
    "listening-spot-check-reviewer",
]


@pytest.mark.parametrize("name", REQUIRED_AGENTS)
def test_agent_file_exists(name: str) -> None:
    path = AGENTS_DIR / f"{name}.md"
    assert path.exists(), f"missing reviewer agent: {path}"


@pytest.mark.parametrize("name", REQUIRED_AGENTS)
def test_agent_has_yaml_frontmatter(name: str) -> None:
    path = AGENTS_DIR / f"{name}.md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{name} missing frontmatter"
    end = text.find("\n---\n", 4)
    assert end > 0, f"{name} frontmatter not closed"
    fm = text[4:end]
    assert "name:" in fm
    assert "description:" in fm


def test_ffmpeg_reviewer_references_反馈记录() -> None:
    text = (AGENTS_DIR / "ffmpeg-invariants-reviewer.md").read_text(encoding="utf-8")
    assert "反馈记录" in text


def test_prompt_eval_reviewer_references_eval_gold() -> None:
    text = (AGENTS_DIR / "prompt-eval-reviewer.md").read_text(encoding="utf-8")
    assert "shared/eval/gold" in text


def test_listening_reviewer_references_timeline_manifest() -> None:
    text = (AGENTS_DIR / "listening-spot-check-reviewer.md").read_text(
        encoding="utf-8"
    )
    assert "timeline_manifest.json" in text
```

- [ ] **Step 2: Run the failing test**

Run: `python -m pytest tests/agents/test_agent_stubs.py -v`
Expected: FAIL — files missing.

- [ ] **Step 3: Write the four agent stub files**

`.claude/agents/spec-drift-reviewer.md`:
```markdown
---
name: spec-drift-reviewer
description: Reviews a git diff against docs/superpowers/specs/2026-05-07-podcast-cutter-mvp-design.md. Reports spec items unimplemented in the diff, items implemented but not in the spec, and items diverging from the spec. Triggered on every PR / per-stage merge. Use proactively after any non-trivial change.
---

# spec-drift-reviewer

You are a fresh-context reviewer with no memory of design or implementation conversations. Your only inputs are:

1. The spec at `docs/superpowers/specs/2026-05-07-podcast-cutter-mvp-design.md`
2. A git diff (the user provides this in the prompt or you obtain via `git diff main...HEAD`)
3. The current state of the repo

## Your job

For each section of the spec, answer:
- Is this requirement implemented in the diff or already on disk?
- Are there changes in the diff that the spec does NOT describe?
- Are there documented divergences (e.g. a CHANGELOG entry explaining "we deviated from spec §X.Y because…")? Undocumented divergence is a hard fail.

## Output format

```
## Spec drift report

### Implemented in this diff
- §X.Y "<spec heading>": <one line how>

### Implemented but undocumented in the spec
- <file:line> <description>

### In the spec but missing from the diff and from disk
- §X.Y <description>

### Divergences (documented OR undocumented)
- §X.Y diff says <X>, spec says <Y>; documented in <CHANGELOG/PR description/none>

### Verdict
PASS | FAIL — <one-line summary>
```

## Hard-fail conditions

- Any "In the spec but missing from disk" item that is in scope for this MVP per spec §1.1.
- Any "undocumented divergence."

## Out of scope

You do NOT review code quality, security, or performance. Generic reviewers (`compound-engineering:review:*`) handle those. You only check the diff against the spec.
```

`.claude/agents/ffmpeg-invariants-reviewer.md`:
```markdown
---
name: ffmpeg-invariants-reviewer
description: Audits any diff that touches ffmpeg or audio-processing code against the rule book in docs/后期/反馈记录.md. Hard-fails on amix usage, -ss after -i with -af, missing fade in/out on extracted clips, absolute music paths, and missing volumedetect post-checks. Use proactively after any change to *.py / *.js with ffmpeg/audio invocations.
---

# ffmpeg-invariants-reviewer

You are a fresh-context reviewer with no memory of design or implementation conversations. Your inputs:

1. The rule book at `docs/后期/反馈记录.md` (ported from podcastcut, gold-grade hard-won lessons).
2. A git diff (provided or obtained via `git diff main...HEAD`).

## Your job

Scan every changed line that touches ffmpeg invocation or audio processing. For each, check against the invariants:

| Rule | Source in 反馈记录 |
|---|---|
| Never use `amix`; use `amerge=inputs=N,pan=stereo|c0=c0+c2|c1=c1+c3` | 2026-02-14 |
| `-ss` placed BEFORE `-i` when `-af` filter is also present | 2026-02-02 / 2026-02-22 (line 658-672 of `后期/SKILL.md` reference) |
| Use `atrim` not `-ss` for mp3 input (mp3 seek is unreliable) | 2026-02-02 |
| Every clip extract has both `afade in` AND `afade out` (30 ms / 50 ms minimum) | 2026-02-22 |
| Two adjacent audio segments are joined with `acrossfade` (or explicit equivalent), never bare `concat` for non-music joins | 2026-02-22 |
| Continuous music bed uses `volume=eval=frame:volume='if(...)'`, not separate music clips | 2026-02-14 |
| Music files are copied into the project working dir, never referenced by absolute user-machine path | 2026-02-18 |
| Every successful ffmpeg run is followed by `volumedetect` (or routed through `lib/ffmpeg_wrap.run_ffmpeg` which does this) | 2026-02-02 |
| Final-section `afade out` (3 s) is applied at the end of main_body before crossfade to outro | 2026-02-21 |

## Output format

```
## FFmpeg invariants report

### Violations found
- <file:line> [rule X] <quote of offending code> — <why it violates>

### Suggestions (non-blocking)
- <file:line> consider <…>

### Verdict
PASS | FAIL — <count> violations
```

## Hard-fail conditions

Any violation in the table above. No exceptions; every entry was learned from a real bug in podcastcut.

## Out of scope

Code style, performance, non-audio behaviors. Only audio invariants.
```

`.claude/agents/prompt-eval-reviewer.md`:
```markdown
---
name: prompt-eval-reviewer
description: Runs eval gold set in shared/eval/gold against any diff to analyze_*.py / pick_golden_quotes.py / shared/rules/editing/*. Compares precision/recall/F1 vs baseline; hard-fails on regression beyond threshold. Use proactively after changes to LLM prompts or editing rules.
---

# prompt-eval-reviewer

You are a fresh-context reviewer with no memory of prior conversations. Inputs:

1. Eval gold set under `shared/eval/gold/` (ported from `reference/podcastcut-skills/剪播客/eval/`).
2. The diff (analyze_*.py / pick_golden_quotes.py / shared/rules/editing/*.md).
3. Baseline metrics committed in `shared/eval/baseline.json` (or, if absent, established by running the eval on the pre-diff version).

## Your job

1. Run the new prompt against the eval gold set. The runner script will be `shared/eval/run_eval.py` (added in Plan 2 / 3).
2. Produce metrics: precision, recall, F1 for each class of cuts (rough, fine, golden_quote candidates).
3. Compare against baseline.

## Hard-fail thresholds

- Precision drops > 3 percentage points from baseline.
- Recall drops > 5 percentage points from baseline.
- F1 drops > 3 percentage points from baseline.

These thresholds are for MVP; tune later in `shared/eval/baseline.json` after we have stable numbers.

## Output format

```
## Prompt eval report

| Metric | Baseline | New | Δ |
|---|---|---|---|
| precision_rough | … | … | … |
| recall_rough | … | … | … |
| F1_rough | … | … | … |
| precision_fine | … | … | … |
| recall_fine | … | … | … |
| F1_fine | … | … | … |

### Sample regressions (if any)
- gold/<sample>.json: baseline marked "X" as cut, new prompt does not

### Verdict
PASS | FAIL — <reason>
```

## Out of scope

Anything not run-against-eval. If the change is a bugfix that does not affect prompt behavior, recommend the user note this in the PR and skip you.

## Bootstrap notes

Until `shared/eval/run_eval.py` exists (Plan 3), report: "eval runner not yet implemented; deferring; verify manually." This stub is in place so the gate is wired before its body.
```

`.claude/agents/listening-spot-check-reviewer.md`:
```markdown
---
name: listening-spot-check-reviewer
description: Final-output sanity check using Gemini to LISTEN to final.mp3. Reads timeline_manifest.json so it never flags golden_quote duplication as a bug. Spot-checks each xfade region for artifacts and each main_body cut point flagged by qc_signal. Use at end of /podcast-cut-后期 and /podcast-cut-质检.
---

# listening-spot-check-reviewer

You are a fresh-context reviewer with no memory of prior conversations. Inputs:

1. `output/<episode>/6_packaging/final.mp3`
2. `output/<episode>/6_packaging/timeline_manifest.json` (structural truth — see spec §4.6)
3. `output/<episode>/7_qc/qc_summary.md` and the underlying `qc_*.json` files
4. Gemini API key (`GEMINI_API_KEY`) — required

## Your job

1. Parse `timeline_manifest.json`. Build a list of "spot-check points":
   - Every `*_xfade` region's start AND end timestamps.
   - Every cut point inside `main_body` flagged HIGH by `qc_signal.json`.
   - Every `golden_quote` boundary (start, end).
2. For each spot, extract a 6-second window centered on the timestamp from `final.mp3` (use `ffmpeg -ss WINDOW_START -t 6 ...`). Send to Gemini for transcription + listening-quality assessment.
3. **Critical**: when assessing, you MUST treat `golden_quote` regions as INTENTIONAL reuse from later in the recording. Do NOT flag the duplication of content between montage and main body as a bug. Only flag intelligibility, click/pop, abrupt music level changes, ducking that doesn't restore.

## Output format

```
## Listening spot-check report

### Region map
<short summary of regions from manifest>

### Findings
| Time | Region | Severity | What I heard |
|---|---|---|---|
| 14.2s | intra_montage_xfade | LOW | crossfade smooth |
| 41.8s | montage_to_main_xfade | HIGH | hard cut, no music tail |
| 1342.5s | main_body cut | MEDIUM | brief click |

### Verdict
PASS | NEEDS_HUMAN_LISTEN | FAIL — <one-line summary>
```

## Hard-fail conditions

- Any HIGH-severity finding at a transition or main_body cut.
- A `golden_quote` window where the speaker is unintelligible.
- Music level changes that do not return to baseline (broken ducking).

## Out of scope

Editorial taste ("this quote isn't a great opener"). Only acoustic / listening artifacts.

## Bootstrap notes

Until Plan 4 lands `final.mp3` and `timeline_manifest.json`, report: "no final.mp3 / manifest present; nothing to listen to." This stub is in place so the gate is wired.
```

- [ ] **Step 4: Run the test to verify pass**

Run: `python -m pytest tests/agents/test_agent_stubs.py -v`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add .claude/agents/spec-drift-reviewer.md \
  .claude/agents/ffmpeg-invariants-reviewer.md \
  .claude/agents/prompt-eval-reviewer.md \
  .claude/agents/listening-spot-check-reviewer.md \
  tests/agents/__init__.py \
  tests/agents/test_agent_stubs.py
git commit -m "$(cat <<'EOF'
feat(agents): four reviewer subagent stubs

Spec §6 quality gates wired up before they're functional. Each agent
declares its scope, inputs, hard-fail conditions, and includes a
bootstrap-mode note for when its dependencies don't exist yet (eval
runner, final.mp3, manifest). The ffmpeg-invariants-reviewer rule book
references docs/后期/反馈记录.md, which arrives in Plan 4.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: `/podcast-cut-安装` skill — install scripts and SKILL.md

**Files:**
- Create: `.claude/skills/podcast-cut-安装/SKILL.md`
- Create: `shared/scripts/install/check_deps.sh`
- Create: `shared/scripts/install/fetch_assets.sh`
- Create: `shared/scripts/install/verify_volcano.py`
- Create: `tests/install/__init__.py`
- Test: `tests/install/test_check_deps.py`
- Test: `tests/install/test_verify_volcano.py`

`fetch_assets.sh` is a placeholder this plan: it creates the music dir (already done in Task 1) and exits zero. Plan 4 will make it actually fetch RNNoise model + bundled music. Stubbing it now keeps the install skill self-contained.

- [ ] **Step 1: Write the failing tests**

`tests/install/__init__.py`:
```python
```

`tests/install/test_check_deps.py`:
```python
"""Tests for shared/scripts/install/check_deps.sh."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parent.parent.parent
    / "shared/scripts/install/check_deps.sh"
)


def test_check_deps_passes_when_all_present() -> None:
    if not all(shutil.which(b) for b in ["node", "ffmpeg", "python3"]):
        pytest.skip("real deps not installed; cannot verify pass path")
    proc = subprocess.run(
        ["bash", str(SCRIPT)], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr


def test_check_deps_fails_when_dep_missing(tmp_path: Path) -> None:
    """Run with PATH set to an empty dir so no binaries are found."""
    proc = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env={"PATH": str(tmp_path), "HOME": os.environ.get("HOME", "/tmp")},
    )
    assert proc.returncode != 0
    assert "not found" in proc.stdout.lower() or "missing" in proc.stdout.lower()
```

`tests/install/test_verify_volcano.py`:
```python
"""Tests for shared/scripts/install/verify_volcano.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from shared.scripts.install import verify_volcano


def test_verify_volcano_reports_missing_creds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = tmp_path / ".env"
    env.write_text("VOLC_RESOURCE_ID=volc.seedasr.auc\n")
    rc = verify_volcano.main(env_path=env, do_network=False)
    assert rc != 0
    out = capsys.readouterr().out + capsys.readouterr().err
    assert "VOLC_API_KEY" in out or "Volcano" in out


def test_verify_volcano_dry_run_passes_with_creds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "VOLC_API_KEY=newkey\nVOLC_RESOURCE_ID=volc.seedasr.auc\n"
    )
    rc = verify_volcano.main(env_path=env, do_network=False)
    assert rc == 0
    out = capsys.readouterr().out
    assert "ok" in out.lower() or "passed" in out.lower()
```

- [ ] **Step 2: Run the failing tests**

Run: `python -m pytest tests/install -v`
Expected: FAIL — script and module missing.

- [ ] **Step 3: Write `shared/scripts/install/check_deps.sh`**

```bash
#!/usr/bin/env bash
# Verify all runtime dependencies for the podcast cutter skills.
# Exits 0 if everything is present; nonzero otherwise.

set -uo pipefail

ok=0
fail=0
warn() { printf '  [missing] %s — install with: %s\n' "$1" "$2"; fail=$((fail + 1)); }
good() { printf '  [ok]      %s\n' "$1"; ok=$((ok + 1)); }

printf 'Checking dependencies...\n'

if command -v node >/dev/null 2>&1; then
  ver=$(node -v)
  good "node $ver"
else
  warn "node" "brew install node  (or: nvm install --lts)"
fi

if command -v ffmpeg >/dev/null 2>&1; then
  ver=$(ffmpeg -version 2>/dev/null | head -1)
  good "$ver"
else
  warn "ffmpeg" "brew install ffmpeg  (or: apt install ffmpeg)"
fi

if command -v python3 >/dev/null 2>&1; then
  ver=$(python3 --version)
  good "$ver"
else
  warn "python3" "brew install python3  (or: apt install python3)"
fi

if command -v ffprobe >/dev/null 2>&1; then
  good "ffprobe (bundled with ffmpeg)"
else
  warn "ffprobe" "brew install ffmpeg  (ffprobe ships with ffmpeg)"
fi

printf '\n%d ok, %d missing.\n' "$ok" "$fail"
exit "$fail"
```

Make it executable:
```bash
chmod +x shared/scripts/install/check_deps.sh
```

- [ ] **Step 4: Write `shared/scripts/install/fetch_assets.sh`**

```bash
#!/usr/bin/env bash
# Download bundled assets (RNNoise model, royalty-free intro/outro).
#
# Plan 1 status: STUB. The real fetch logic arrives in Plan 4 (audio_clean
# + package_final). This script's only job today is to confirm the asset
# directory layout exists and exit cleanly.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
MUSIC_DIR="$ROOT/shared/assets/music"

mkdir -p "$MUSIC_DIR"
printf 'Asset directory ready: %s\n' "$MUSIC_DIR"
printf 'NOTE: bundled music + RNNoise model arrive in Plan 4 (audio cleanup + packaging).\n'
```

Make it executable:
```bash
chmod +x shared/scripts/install/fetch_assets.sh
```

- [ ] **Step 5: Write `shared/scripts/install/verify_volcano.py`**

```python
"""Confirm Volcano credentials are loadable and (optionally) reach the API.

Usage:
    python -m shared.scripts.install.verify_volcano [--env PATH] [--no-network]

Exits 0 on success, nonzero on failure. With --no-network we only check that
config.load() succeeds; with the network flag (default) we also send a tiny
ping submit (no audio actually transcribed).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from shared.scripts.lib import config


def main(*, env_path: Path, do_network: bool) -> int:
    try:
        cfg = config.load(env_path=env_path)
    except config.ConfigError as exc:
        print(f"[verify_volcano] config error: {exc}", file=sys.stderr)
        return 1

    print(
        f"[verify_volcano] config ok — console={cfg.volcano.console} "
        f"resource_id={cfg.volcano.resource_id} upload_backend={cfg.upload_backend}"
    )
    if not do_network:
        return 0

    # Plan 1 leaves the actual network ping to Plan 2 (where volcano_submit.py
    # exists). For now, --no-network is the default in tests; manual install
    # users can re-run with --network after Plan 2 ships.
    print("[verify_volcano] skipping network ping (Plan 2 adds the real submit)")
    return 0


def cli() -> int:  # pragma: no cover - thin argparse glue
    p = argparse.ArgumentParser(prog="verify_volcano")
    p.add_argument("--env", type=Path, default=Path(".env"))
    p.add_argument("--no-network", action="store_true")
    args = p.parse_args()
    return main(env_path=args.env, do_network=not args.no_network)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(cli())
```

Add `shared/scripts/install/__init__.py`:
```python
```

- [ ] **Step 6: Run the tests to verify pass**

Run: `python -m pytest tests/install -v`
Expected: 4 passed (or some skipped if real deps not installed locally — that's acceptable).

- [ ] **Step 7: Write the install SKILL.md**

`.claude/skills/podcast-cut-安装/SKILL.md`:
```markdown
---
name: podcast-cut-安装
description: |
  播客剪辑环境一次性准备：依赖检查、.env 模板、Volcano 凭据自验、bundled 资产准备。
  触发词：安装播客剪辑、初始化播客环境、podcast cut install
---

# 播客剪辑 · 安装

> 首次使用前的环境准备。运行一次即可。

## 快速使用

```
用户: 安装播客剪辑环境
用户: podcast cut install
```

## 步骤

### 1. 依赖检查

```bash
bash shared/scripts/install/check_deps.sh
```

需要：
- `node` ≥ 18
- `ffmpeg` ≥ 6（含 `ffprobe`，含 `arnndn` 滤镜）
- `python3` ≥ 3.10

如缺，脚本会打印对应的 `brew install` / `apt install` 命令。

### 2. Python 依赖

```bash
pip install -e ".[dev]"
```

### 3. 配置 `.env`

```bash
cp .env.example .env
$EDITOR .env
```

最少需要的字段（新版控制台）：
- `VOLC_API_KEY`：Volcano 引擎控制台获取
- `VOLC_RESOURCE_ID=volc.seedasr.auc`（默认）

可选：`TOS_*` 或 `S3_*`（音频上传后端，未配置则回退到 uguu.se 公网临时托管，会有提示）

### 4. 资产准备（stub，Plan 4 实现）

```bash
bash shared/scripts/install/fetch_assets.sh
```

当前只确认目录结构。Plan 4 后会下载 RNNoise 模型 + 默认 royalty-free 片头/片尾音乐。

### 5. Volcano 凭据自验

```bash
python -m shared.scripts.install.verify_volcano --no-network
```

`--no-network` 是 Plan 1 的默认选项；Plan 2 提供 `volcano_submit.py` 后会做完整的 ping 测试。

### 6. 测试套件

```bash
python -m pytest
```

全部通过即环境就绪。

## 输出

无文件输出，只是环境验证。

## 与其他 skill 的关系

```
/podcast-cut-安装   ← 本 skill（一次性）
/podcast-cut-剪播客 ← 主流程（Plan 2、3）
/podcast-cut-后期   ← 后期处理（Plan 4）
/podcast-cut-质检   ← 质检（Plan 5）
```

## 常见问题

**Q: `ffmpeg arnndn` 滤镜找不到？**
ffmpeg 必须 ≥ 4.4 且编译时启用 `--enable-libavfilter`。Homebrew 的版本默认满足。

**Q: 不想用 uguu.se 上传？**
在 `.env` 里配置 `TOS_*` 或 `S3_*` 任一组。优先级：TOS → S3 → uguu。
```

- [ ] **Step 8: Commit**

```bash
git add shared/scripts/install/check_deps.sh \
  shared/scripts/install/fetch_assets.sh \
  shared/scripts/install/verify_volcano.py \
  shared/scripts/install/__init__.py \
  .claude/skills/podcast-cut-安装/SKILL.md \
  tests/install/__init__.py \
  tests/install/test_check_deps.py \
  tests/install/test_verify_volcano.py
chmod +x shared/scripts/install/check_deps.sh shared/scripts/install/fetch_assets.sh
git update-index --chmod=+x shared/scripts/install/check_deps.sh
git update-index --chmod=+x shared/scripts/install/fetch_assets.sh
git commit -m "$(cat <<'EOF'
feat(install): podcast-cut-安装 skill + check_deps + verify_volcano

Stub fetch_assets and verify_volcano --no-network paths so the install
skill is runnable end-to-end today. Real network ping moves to Plan 2;
real asset fetch moves to Plan 4.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: Foundation milestone — full test sweep + CHANGELOG entry

**Files:**
- Create: `CHANGELOG.md`

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest -v`
Expected: All tests pass. Counts roughly: 5 (audio_constants) + 5 (json_io) + 9 (config) + 14 (volcano_client) + 6 (upload) + 4 (ffmpeg_wrap) + 11 (agent stubs) + 4 (install). Total ~58 passing. (Some `ffmpeg_wrap` and `check_deps` tests skip on machines missing real binaries — that's acceptable.)

- [ ] **Step 2: Write the foundation milestone CHANGELOG entry**

`CHANGELOG.md`:
```markdown
# Changelog

## 2026-05-07 — Foundation (Plan 1)

### Added
- `shared/scripts/lib/`: `config`, `json_io`, `audio_constants`, `volcano_client`, `upload`, `ffmpeg_wrap`. All TDD-tested.
- `.claude/agents/`: four reviewer-subagent stubs (`spec-drift`, `ffmpeg-invariants`, `prompt-eval`, `listening-spot-check`).
- `.claude/skills/podcast-cut-安装/SKILL.md` + `shared/scripts/install/{check_deps.sh, fetch_assets.sh, verify_volcano.py}`.
- `pyproject.toml`, `pytest.ini`, `tests/`, `shared/test_fixtures/`, `.env.example`.
- `shared/test_fixtures/silence_only/silence_5s.wav` (committed; used by ffmpeg_wrap silence-trap tests).

### Stubbed (real implementation arrives in later plans)
- `fetch_assets.sh` — Plan 4: bundled music + RNNoise model fetch.
- `verify_volcano.py --network` — Plan 2: real Volcano ping after `volcano_submit.py` exists.
- Reviewer-agent bodies: bootstrap-mode notes inside each agent describe what they fall back to until their dependencies (eval gold set, final.mp3, manifest) exist.

### Notes
- `audio_constants.py` is data-only by test enforcement; never grow it into a behavior module.
- `lib/ffmpeg_wrap.run_ffmpeg` is the only sanctioned ffmpeg entry point. Direct `subprocess.run(['ffmpeg', ...])` will fail the `ffmpeg-invariants-reviewer` once it has a body.
```

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "$(cat <<'EOF'
docs: CHANGELOG for Foundation milestone (Plan 1)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: Tag the milestone (optional)**

```bash
git tag -a v0.1.0-foundation -m "Foundation milestone: lib + install skill + reviewer stubs"
```

---

## Acceptance criteria for this plan

- [ ] `python -m pytest` exits 0 (with at most fixture-dependent skips, no failures).
- [ ] `bash shared/scripts/install/check_deps.sh` exits 0 on a properly set-up dev box.
- [ ] `python -m shared.scripts.install.verify_volcano --no-network` reports `config ok` when `.env` has Volcano creds.
- [ ] Four reviewer-agent files exist with passing structural tests.
- [ ] `/podcast-cut-安装` skill is invocable from Claude Code (slash menu).
- [ ] `git log --oneline` shows roughly 9 task commits + 1 CHANGELOG commit, all on top of the design-doc commit.

## What this plan does NOT do (deferred)

- Real audio I/O scripts (`prepare_audio.py`, `cut_audio.py`, etc.) — Plan 2 / 3.
- Real LLM analysis (`analyze_rough.py`, `analyze_fine.py`) — Plan 2.
- Review HTML server (`review_server.py`) — Plan 3.
- Audio cleanup (`audio_clean.py`) — Plan 4.
- Packaging (`package_final.py`) — Plan 4.
- QC (`qc_*.py`) — Plan 5.
- Reviewer-agent bodies past stubs — wired alongside their dependencies in Plans 2-5.

Each later plan begins by re-running `python -m pytest` to confirm Foundation still holds, then adds its layer.
