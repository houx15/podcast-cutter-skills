# podcast-cutter-skills

A Python toolkit for cutting Chinese podcast episodes with AI assistance. Raw dual-track recordings go in; a clean, sample-accurate `cut.wav` comes out. The pipeline covers audio preparation, Volcano Engine v3 AUC ASR transcription, three rounds of LLM analysis (rough cut, fine cut, self-review), browser-based human review, and precise ffmpeg splicing with 25 ms crossfades.

## Prerequisites

| Dependency | Notes |
|------------|-------|
| Python 3.10+ | |
| ffmpeg | Must be on `PATH`. Install via Homebrew (`brew install ffmpeg`) or your OS package manager. |
| Volcano Engine ASR key | `VOLC_API_KEY` (new console) or `VOLC_APP_KEY` + `VOLC_ACCESS_KEY` (old console). See [docs/configuration.md](docs/configuration.md). |
| ByteDance Ark (LLM) key | `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`. |
| Audio storage (optional) | TOS or S3-compatible bucket, or fall through to uguu.se for small files. |

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

# 4. Review in browser (the pipeline prints the server command and HTML path)
python shared/scripts/review_server.py --ep-dir output/2026-05-08-ep01 --port 5050
# Open the printed review_enhanced.html path, review cuts, click Export

# 5. Finish the cut
python shared/scripts/run_pipeline.py --ep-dir output/2026-05-08-ep01 --resume
# Result: output/2026-05-08-ep01/4_cut/cut.wav
```

For alignment options, troubleshooting, and per-stage details, see [docs/剪播客/快速上手.md](docs/剪播客/快速上手.md).

## Stage Pipeline

| Stage | Script | Input | Output |
|-------|--------|-------|--------|
| 1.0 | `prepare_audio.py` | Recording files | `input/working_track*.wav`, `audio_meta.json` |
| 1.1 | `lib/upload.py` (embedded) | working WAV | Audio URL |
| 1.2a | `volcano_submit.py` | Audio URL | `task_id_track*.txt` |
| 1.2b | `volcano_query.py` | Task ID | `volcano_raw_track*.json` |
| 1.3 | `transcribe_merge.py` | volcano_raw × n | `words.json` |
| 1.4 | `make_sentences.py` | words.json | `sentences.json` |
| 2.1 | `analyze_rough.py` | sentences + rules | `rough_cuts.json` |
| 2.2 | `analyze_fine.py` | sentences + words + rough | `fine_cuts.json` |
| 2.3 | `self_review.py` | rough + fine + sentences | `self_review.json` |
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
├── tests/                    # pytest suite (96 tests)
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
