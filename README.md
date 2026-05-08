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

## Using This Skill in a Remote Agent (Cowork etc.)

A remote agent (e.g. Cowork, GitHub Actions, a hosted Claude Code session) runs the same SKILL.md you'd run locally — but three things change because the agent doesn't share your filesystem or browser:

### 1. Configure secrets, not `.env`

The agent has no `.env` file. Set these as secrets / runtime env vars in the remote runtime:

| Secret | Required? | Purpose |
|--------|-----------|---------|
| `VOLC_API_KEY` | yes | Volcano ASR (new console) |
| `VOLC_RESOURCE_ID` | yes | `volc.seedasr.auc` |
| `TOS_ACCESS_KEY` | yes | Object storage for audio uploads |
| `TOS_SECRET_KEY` | yes | |
| `TOS_BUCKET` | yes | |
| `TOS_ENDPOINT` | yes | e.g. `tos-cn-beijing.volces.com` |

`python-dotenv` reads shell env first, so the same scripts work without modification. (Old-console Volcano accounts can use `VOLC_APP_KEY` + `VOLC_ACCESS_KEY` instead of `VOLC_API_KEY`.)

### 2. Get recordings to the agent

The agent has no local `recordings/` dir. Two patterns:

**A. Pre-upload recordings to TOS yourself** (recommended for large dual-track files):

```bash
# On your laptop — upload to a bucket the agent's TOS keys can read:
aws s3 cp track1-host.wav s3://your-bucket/episodes/ep04/track1.wav --endpoint-url https://tos-s3-cn-beijing.volces.com
```

Then trigger the agent with the URL. In `prepare_audio.py`, point `--track1` at a local path the agent downloads first, e.g.:

```bash
curl -fsSLo recordings/track1.wav "https://...presigned-url..."
python shared/scripts/prepare_audio.py --ep-dir output/ep04 --track1 recordings/track1.wav
```

**B. Commit small reference clips to a private repo branch**, and have the agent check out that branch. Practical for short test clips, not for full recordings.

### 3. Skip the browser review step

`review_server.py` serves on `localhost:5050` — no use on a remote agent. Two options:

**A. Auto-accept the agent's analysis** (full automation): after the agent writes `rough_cuts.json` / `fine_cuts.json` / `self_review.json`, it composes `delete_segments_edited.json` directly from those (union of `rough_cuts.deletes` + `fine_cuts.deletes`, dropping anything the `self_review.flags` marked as `false_positive`), then runs stage 4. No human in the loop.

**B. Two-shot with you doing review locally**: agent runs through stage 3.0, uploads `review_enhanced.html` + `delete_segments.json` somewhere you can fetch (TOS, gist, PR). You review locally, push back `delete_segments_edited.json`, then trigger the agent again to finish stage 4.

For Cowork specifically, **Pattern A** is the natural fit — the orchestrating agent is the analyst, and you trust its judgment based on the editing rules in `shared/rules/editing/`. If you want oversight, run a small clip locally first, tune the rules, then let Cowork loose on full episodes.

### 4. Where the output lives

`output/<ep-id>/4_cut/cut.wav` and `5_shownotes/shownotes.md` end up on the agent's filesystem. To get them back:

- **TOS upload**: have the agent upload `cut.wav` to your TOS bucket as a final step (`aws s3 cp` or extend `lib/upload.py`).
- **Commit & PR**: agent commits `5_shownotes/shownotes.md` (text only) to a branch and opens a PR. `cut.wav` is too large for git — keep it in object storage.
- **Slack / direct delivery**: depends on the agent runtime — Cowork can post the TOS URL back in the channel.

### Minimal trigger message (Cowork example)

> "剪播客 — 录音在 TOS: `s3://your-bucket/episodes/ep04/track1.wav` + `track2.wav`，episode id `ep04`。请按 Pattern A 自动完成全流程，输出 `cut.wav` + `shownotes.md` 上传回 `s3://your-bucket/episodes/ep04/output/`。"

The agent reads `.claude/skills/podcast-cut-剪播客/SKILL.md`, runs each stage, does the analysis itself, and posts the output URLs back when done.

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
| 5.0 | `cut_transcript.py` | sentences.json + deletes | `5_shownotes/cut_transcript.json` |
| 5.1 | *(agent reads cut_transcript + shownotes_example)* | cut_transcript.json + user template | `5_shownotes/shownotes.md` |

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
