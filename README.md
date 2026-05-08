# podcast-cutter-skills

A Python toolkit for cutting Chinese podcast episodes with AI assistance. Raw dual-track recordings go in; a clean, sample-accurate `cut.wav` comes out. The pipeline covers audio preparation, Volcano Engine v3 AUC ASR transcription, agent-driven analysis (rough cut, fine cut, self-review), browser-based human review, and precise ffmpeg splicing with 25 ms crossfades.

## Installation

### 1. Clone the repo

```bash
git clone https://github.com/houx15/podcast-cutter-skills.git
cd podcast-cutter-skills
```

### 2. Install system dependencies

```bash
# macOS
brew install ffmpeg python@3.12

# Ubuntu / Debian
sudo apt install ffmpeg python3.10
```

Verify: `ffmpeg -version` and `python3 --version` (need 3.10+).

### 3. Install Python packages

```bash
pip install -e ".[dev]"
```

### 4. Get API keys

You need one service (plus optional storage):

**Volcano Engine ASR** (transcription)
- Sign up at [console.volcengine.com](https://console.volcengine.com/)
- Go to **Speech → API Keys** and create a key → `VOLC_API_KEY`
- Enable the `volc.seedasr.auc` resource (Chinese big-model ASR)

**Audio upload** (optional — needed for files > ~50 MB)
- Volcano TOS bucket (`TOS_*`) or any S3-compatible storage (`S3_*`)
- Without this, the pipeline falls back to [uguu.se](https://uguu.se) (public, 24 h TTL) with a warning

See [docs/configuration.md](docs/configuration.md) for the full variable reference.

### 5. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in VOLC_API_KEY (and VOLC_RESOURCE_ID if needed)
```

### 6. Verify the installation

```bash
python -m pytest          # 89 tests — all should pass
bash shared/scripts/install/check_deps.sh   # checks ffmpeg + python versions
```

---

## Environment variables for agents

The scripts load `.env` via `python-dotenv`, which checks **shell environment variables first**, then falls back to the `.env` file. This means:

- **Local agents** (Claude Code, Codex CLI, Gemini CLI): create `.env` once in the repo root — every agent running in that directory picks it up automatically.
- **Remote / cloud agents**: set `VOLC_API_KEY` as environment variables in the agent's runtime config (e.g., GitHub Actions secrets, Cowork env vars). No `.env` file needed.

Required variables at minimum:

| Variable | Purpose |
|----------|---------|
| `VOLC_API_KEY` | Volcano Engine ASR authentication |
| `VOLC_RESOURCE_ID` | Set to `volc.seedasr.auc` |

---

## Quick Start

The agent (Claude Code, Codex CLI) drives the workflow by following SKILL.md. Stages run as individual scripts:

```bash
# Stage 1: Transcribe (~5–20 min)
python shared/scripts/prepare_audio.py --ep-dir output/2026-05-08-ep01 --track1 recordings/host.wav --track2 recordings/guest.wav
python shared/scripts/volcano_submit.py --audio-file output/2026-05-08-ep01/input/working_track1.wav --track-num 1 --ep-dir output/2026-05-08-ep01
python shared/scripts/volcano_query.py --track-num 1 --ep-dir output/2026-05-08-ep01
# ...repeat submit/query for track 2 if dual-track...
python shared/scripts/transcribe_merge.py --ep-dir output/2026-05-08-ep01
python shared/scripts/make_sentences.py --ep-dir output/2026-05-08-ep01

# Stage 2: Agent reads sentences.json + rules, writes rough/fine/self_review JSON
# (See SKILL.md for instructions and JSON formats)

# Stage 3: Review
python shared/scripts/generate_review_html.py --ep-dir output/2026-05-08-ep01
python shared/scripts/review_server.py --ep-dir output/2026-05-08-ep01 --port 5050
# Open the printed HTML, review, click Export

# Stage 4: Cut
python shared/scripts/cut_audio.py --ep-dir output/2026-05-08-ep01
python shared/scripts/trim_silences.py --ep-dir output/2026-05-08-ep01
# Output: output/2026-05-08-ep01/4_cut/cut.wav
```

For details (alignment options, error codes, the analysis JSON formats), see `.claude/skills/podcast-cut-剪播客/SKILL.md` or `docs/剪播客/快速上手.md`.

## Stage Pipeline

| Stage | Script | Input | Output |
|-------|--------|-------|--------|
| 1.0 | `prepare_audio.py` | Recording files | `input/working_track*.wav`, `audio_meta.json` |
| 1.05 | `align_tracks.py` (optional) | working WAV or ASR output | `track_offsets_ms` in `audio_meta.json` |
| 1.2a | `volcano_submit.py` | working WAV (uploads internally) | `task_id_track*.txt` |
| 1.2b | `volcano_query.py` | Task ID | `volcano_raw_track*.json` |
| 1.3 | `transcribe_merge.py` | volcano_raw × n | `words.json` |
| 1.4 | `make_sentences.py` | words.json | `sentences.json` |
| 2.1–2.3 | *(agent reads sentences.json + rules)* | sentences.json + rules | `rough_cuts.json`, `fine_cuts.json`, `self_review.json` |
| 3.0 | `generate_review_html.py` + `review_server.py` | analysis | `review_enhanced.html` |
| 3.1 | (browser, manual) | — | `delete_segments_edited.json` |
| 4.0 | `cut_audio.py` | working WAV + delete_segments_edited | `cut.wav` |
| 4.1 | `trim_silences.py` | cut.wav | cut.wav (head/tail trimmed) |

All scripts are idempotent — re-running overwrites the previous output for that stage only.

## Project Layout

```
podcast-cutter-skills/
├── shared/
│   ├── scripts/              # One script per pipeline stage
│   │   ├── lib/              # Shared library modules
│   │   │   ├── config.py         # Env + LLM config loader
│   │   │   ├── ffmpeg_wrap.py    # Sole ffmpeg entry point (includes silence-trap guard)
│   │   │   ├── volcano_client.py # Volcano Engine ASR HTTP client
│   │   │   ├── upload.py         # TOS → S3 → uguu.se upload chain
│   │   │   ├── json_io.py        # Atomic JSON read/write helpers
│   │   │   └── audio_constants.py# Sample-rate, bit-depth, crossfade constants
│   │   └── install/          # Dependency check + asset fetch scripts
│   ├── rules/
│   │   ├── editing/          # LLM editing rules (Chinese Markdown, concatenated as system prompt)
│   │   └── users/default/    # Default user preferences (preferences.yaml, hotwords.txt)
│   └── test_fixtures/        # Audio fixtures used by the test suite
├── tests/                    # pytest suite (89 tests)
│   ├── lib/                  # Tests for lib/ modules
│   ├── scripts/              # Tests for each pipeline script
│   └── install/              # Tests for install scripts
├── docs/
│   ├── 剪播客/               # Per-stage documentation (stages 1–4) + quick-start guide
│   ├── configuration.md      # All .env variables with descriptions
│   └── volcano_asr.md        # Volcano ASR API reference notes
├── .claude/
│   ├── skills/               # Claude Code slash commands
│   └── agents/               # Reviewer subagents (spec-drift, ffmpeg-invariants, etc.)
├── output/                   # Episode working directories (gitignored)
├── recordings/               # Raw input recordings (gitignored)
├── .env.example              # Environment variable template
├── pyproject.toml
└── CHANGELOG.md
```

## Stage Documentation

- [阶段1 — 转录](docs/剪播客/阶段1-转录.md)
- [阶段2 — 分析](docs/剪播客/阶段2-分析.md)
- [阶段3 — 审查](docs/剪播客/阶段3-审查.md)
- [阶段4 — 剪辑](docs/剪播客/阶段4-剪辑.md)
- [Configuration reference](docs/configuration.md)
- [快速上手（中文）](docs/剪播客/快速上手.md)

## Development

```bash
# Run the full test suite
pytest

# With coverage
pytest --cov=shared/scripts --cov-report=term-missing

# Run a specific module's tests
pytest tests/lib/test_ffmpeg_wrap.py -v
```

All new behavior must be test-driven: write a failing test first, then implement. The `ffmpeg-invariants-reviewer` subagent enforces that all ffmpeg calls go through `lib/ffmpeg_wrap.run_ffmpeg`.
