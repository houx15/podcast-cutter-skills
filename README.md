# podcast-cutter-skills

**Language: English | [中文](README.zh.md)**

A Chinese-podcast editing toolkit that lets your AI coding agent (Claude Code / Codex CLI / Gemini CLI) take raw recordings and produce a clean, sample-accurate `cut.wav`. The pipeline covers ASR transcription, agent-driven cut analysis, browser-based human review, and precise ffmpeg splicing.

> 📖 Looking to drive this repo from an agent? See **[AGENTS.md](AGENTS.md)** — that's the contract your agent reads.

---

## Quick start for users

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

### 4. Register Volcano Engine API keys

We use [Volcano Engine Speech](https://www.volcengine.com/product/speech-tech) for Chinese ASR — it has the best Chinese accuracy we've found, supports word-level timestamps, and the free tier is generous.

1. Sign up at [console.volcengine.com](https://console.volcengine.com/) (real-name verification required for mainland users).
2. Open **语音技术 (Speech) → 应用管理 (Apps)** and create an app — record the **APP ID**.
3. Open **API 访问密钥 (API Keys)** and create a key — record the **API Key**.
4. In the **大模型录音文件识别 (Large-model File Recognition)** product page, click **开通 (Enable)** for the resource `volc.bigasr.auc` (a.k.a. `volc.seedasr.auc`).
5. (Optional, for files larger than ~50 MB) Create a **TOS bucket** for audio uploads, and an **access key / secret key** with read+write on that bucket.

Copy the template and fill in the keys:

```bash
cp .env.example .env
# Edit .env — at minimum set VOLC_API_KEY and VOLC_RESOURCE_ID=volc.bigasr.auc
```

The full variable reference lives in [docs/configuration.md](docs/configuration.md).

### 5. Tell your agent to use this repo

Open the repo in **Claude Code**, **Codex CLI**, or **Gemini CLI** — they all auto-load this project's instructions from `AGENTS.md`/`CLAUDE.md`/`GEMINI.md` and discover the bundled skills under `.claude/skills/`, `.codex/skills/`, `.gemini/skills/`.

Then drop your recording into `recordings/` and prompt the agent in plain language:

> 剪播客 — 录音在 `recordings/ep01.wav`，episode id 是 `2026-05-08-ep01`。

The agent will read `.claude/skills/podcast-cut-剪播客/SKILL.md`, run each stage end-to-end, pause for your browser review at stage 3, and produce `output/<ep-id>/4_cut/cut.wav` plus `output/<ep-id>/5_shownotes/shownotes.md`.

If you'd rather drive the scripts by hand (no agent), see **[AGENTS.md](AGENTS.md)** — it lists every script with its inputs and outputs.

---

## How the pipeline works

```
recording.wav  ─┐
                │  Stage 1 — Transcribe
                │   ffmpeg normalize → Volcano ASR → word + sentence JSON
                ▼
         sentences.json
                │  Stage 2 — Analyze (your agent does the work)
                │   reads editing rules + preferences, proposes deletions
                ▼
   rough_cuts.json + fine_cuts.json + self_review.json
                │  Stage 3 — Human review
                │   browser timeline, accept/reject each delete
                ▼
   delete_segments_edited.json
                │  Stage 4 — Cut
                │   sample-accurate ffmpeg splice with 25 ms crossfades
                ▼
            cut.wav
                │  Stage 5 — Show notes (optional)
                │   agent drafts shownotes.md from the cut transcript
                ▼
          shownotes.md
```

Stage outputs are individual files under `output/<ep-id>/`. Re-running a stage overwrites only that stage's output — the upstream files stay intact, so you can iterate cheaply.

---

## What's not great yet

Honest list of current gaps — contributions welcome:

- **Filler-word trimming (口癖) is rough.** The rule-based pass catches the obvious "嗯/呃/那个/就是" cases but still leaves residue, and the fine-cut agent pass occasionally over-cuts pauses that carried meaning. Expect to spend review time on these.
- **No background music / scoring.** The pipeline outputs a clean speech `cut.wav` and stops there. There's no built-in step for intro/outro stingers, ducking, or per-section BGM — you'll need to bring those into your DAW manually.
- **Mono-recording speaker diarization is unreliable.** Volcano's diarization on a single mixed track frequently returns `speaker=null`. Dual-track recording (one mic per speaker) sidesteps this entirely and is strongly recommended.
- **Show notes are template-driven, not adaptive.** Stage 5 produces a workable draft in our podcast's voice, but you'll usually want to rewrite the intro paragraph and Highlights section yourself.

---

## For contributors

### Repository layout

```
podcast-cutter-skills/
├── shared/
│   ├── scripts/              # One script per pipeline stage
│   │   ├── lib/              # Shared library modules
│   │   │   ├── config.py         # Env + LLM config loader
│   │   │   ├── ffmpeg_wrap.py    # Sole ffmpeg entry point (silence-trap guarded)
│   │   │   ├── volcano_client.py # Volcano Engine ASR HTTP client
│   │   │   ├── upload.py         # TOS → S3 → uguu.se upload chain
│   │   │   ├── json_io.py        # Atomic JSON read/write helpers
│   │   │   └── audio_constants.py# Sample-rate, bit-depth, crossfade constants
│   │   └── install/          # Dependency check + asset fetch scripts
│   ├── rules/
│   │   ├── editing/          # Editing rules (Chinese Markdown — agent system prompt)
│   │   └── users/default/    # Default user preferences (preferences.yaml, hotwords.txt)
│   └── test_fixtures/        # Audio fixtures used by the test suite
├── tests/                    # pytest suite
│   ├── lib/                  # Tests for lib/ modules
│   ├── scripts/              # Tests for each pipeline script
│   └── install/              # Tests for install scripts
├── docs/
│   ├── 剪播客/               # Per-stage documentation (stages 1–4) + quick-start guide
│   ├── configuration.md      # All .env variables with descriptions
│   ├── volcano_asr.md        # Volcano ASR API reference notes
│   └── volcano_tos_sdk.md    # Volcano TOS SDK / signing reference
├── .claude/                  # Claude Code skills, agents, rules
├── .codex/                   # Codex CLI skills + prompts
├── .gemini/                  # Gemini CLI skills + commands
├── output/                   # Episode working directories (gitignored)
├── recordings/               # Raw input recordings (gitignored)
├── .env.example
├── AGENTS.md                 # Agent-facing project instructions
├── pyproject.toml
└── CHANGELOG.md
```

### Development

```bash
pytest                                      # full test suite
pytest --cov=shared/scripts --cov-report=term-missing
pytest tests/lib/test_ffmpeg_wrap.py -v     # single module
```

All new behavior must be test-driven — write the failing test first, then implement. The `ffmpeg-invariants-reviewer` subagent enforces that every ffmpeg call goes through `lib/ffmpeg_wrap.run_ffmpeg`.

### Stage documentation

- [阶段 1 — 转录](docs/剪播客/阶段1-转录.md)
- [阶段 2 — 分析](docs/剪播客/阶段2-分析.md)
- [阶段 3 — 审查](docs/剪播客/阶段3-审查.md)
- [阶段 4 — 剪辑](docs/剪播客/阶段4-剪辑.md)
- [Configuration reference](docs/configuration.md)
- [快速上手（中文）](docs/剪播客/快速上手.md)

---

## Acknowledgements

This repo borrows ideas, patterns, and editing-rule inspiration from several open-source projects. Huge thanks to their authors:

- [kennyzheng-builds/ai-podcast-editor](https://github.com/kennyzheng-builds/ai-podcast-editor) — Descript-inspired transcription-driven editor that informed our text↔audio mapping and filler-detection thinking.
- [JasonYpro/autocut-skills](https://github.com/JasonYpro/autocut-skills) — AI-driven autocut for spoken-word video, with a similar Volcano ASR + browser-review flow that shaped our review UI.
- [luoyuweidu1/podcastcut-skills](https://github.com/luoyuweidu1/podcastcut-skills) — Claude Code Skills approach to podcast cutting that influenced our skill/stage layout.
- [avaleenlhs-gif/zh-podcast-filler-cut](https://github.com/avaleenlhs-gif/zh-podcast-filler-cut) — Whisper + ffmpeg filler-word cutter whose heuristic词表 informed our rule-based pass.

If you're building in this space, those repos are well worth a read.
