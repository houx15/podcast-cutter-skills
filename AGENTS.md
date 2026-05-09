# Project Instructions

> Podcast cutter skills toolkit — agent-facing reference

This is a **Chinese podcast editing toolkit**. It turns raw recordings into a clean `cut.wav` via ASR transcription, agent analysis, and human review. End users see [README.md](README.md); this file is the contract for the agent that runs the pipeline.

## How the agent runs a podcast episode

The agent drives the workflow by following `.claude/skills/podcast-cut-剪播客/SKILL.md` (Codex mirror in `.codex/skills/`, Gemini mirror in `.gemini/skills/`). Each stage is one or more scripts:

- **Stage 1 (transcribe)**: `prepare_audio` → `align_tracks` (if dual-track) → `volcano_submit` / `volcano_query` (per track) → `transcribe_merge` → `make_sentences`
- **Stage 2 (analyze)**: agent reads `sentences.json` + `shared/rules/editing/*.md` + `preferences.yaml`, writes `rough_cuts.json` + `fine_cuts.json` + `self_review.json`
- **Stage 3 (review)**: `generate_review_html` → `review_server` (human reviews in browser, exports `delete_segments_edited.json`)
- **Stage 4 (cut)**: `cut_audio` → `trim_silences`
- **Stage 5 (show notes, optional)**: `cut_transcript` → agent drafts `shownotes.md` from the cut transcript + user template

Each stage's output is its own file. To redo a stage, delete its output and rerun the script.

### Reference invocation

```bash
# Stage 1: Transcribe (~5–20 min depending on length and Volcano queue)
python shared/scripts/prepare_audio.py --ep-dir output/2026-05-08-ep01 \
    --track1 recordings/host.wav --track2 recordings/guest.wav
python shared/scripts/volcano_submit.py --audio-file output/2026-05-08-ep01/input/working_track1.wav \
    --track-num 1 --ep-dir output/2026-05-08-ep01
python shared/scripts/volcano_query.py --track-num 1 --ep-dir output/2026-05-08-ep01
# ...repeat submit/query for track 2 if dual-track...
python shared/scripts/transcribe_merge.py --ep-dir output/2026-05-08-ep01
python shared/scripts/make_sentences.py --ep-dir output/2026-05-08-ep01

# Stage 2: Agent reads sentences.json + rules, writes rough/fine/self_review JSON.
# (See SKILL.md for the JSON schemas and editing-rule precedence.)

# Stage 3: Review
python shared/scripts/generate_review_html.py --ep-dir output/2026-05-08-ep01
python shared/scripts/review_server.py --ep-dir output/2026-05-08-ep01 --port 5050
# Open the printed HTML, review, click Export.

# Stage 4: Cut
python shared/scripts/cut_audio.py --ep-dir output/2026-05-08-ep01
python shared/scripts/trim_silences.py --ep-dir output/2026-05-08-ep01
# Output: output/2026-05-08-ep01/4_cut/cut.wav
```

### Stage pipeline at a glance

| Stage | Script | Input | Output |
|-------|--------|-------|--------|
| 1.0 | `prepare_audio.py` | Recording files | `input/working_track*.wav`, `audio_meta.json` |
| 1.05 | `align_tracks.py` (optional) | working WAV or ASR output | `track_offsets_ms` in `audio_meta.json` |
| 1.2a | `volcano_submit.py` | working WAV (uploads internally) | `task_id_track*.txt` |
| 1.2b | `volcano_query.py` | Task ID | `volcano_raw_track*.json` |
| 1.3 | `transcribe_merge.py` | volcano_raw × n | `words.json` |
| 1.4 | `make_sentences.py` | `words.json` | `sentences.json` |
| 2.1–2.3 | *(agent reads sentences.json + rules)* | sentences.json + rules | `rough_cuts.json`, `fine_cuts.json`, `self_review.json` |
| 3.0 | `generate_review_html.py` + `review_server.py` | analysis | `review_enhanced.html` |
| 3.1 | (browser, manual) | — | `delete_segments_edited.json` |
| 4.0 | `cut_audio.py` | working WAV + delete_segments_edited | `cut.wav` |
| 4.1 | `trim_silences.py` | `cut.wav` | `cut.wav` (head/tail trimmed) |
| 5.0 | `cut_transcript.py` | sentences.json + deletes | `5_shownotes/cut_transcript.json` |
| 5.1 | *(agent reads cut_transcript + shownotes template)* | cut_transcript.json + user template | `5_shownotes/shownotes.md` |

All scripts are idempotent — re-running overwrites the previous output for that stage only.

## Key files

- `shared/scripts/lib/` — config, ffmpeg_wrap, volcano_client, upload, json_io, audio_constants
- `shared/rules/editing/` — editing rules (Chinese Markdown, read by agent during analysis)
- `shared/rules/users/default/` — user preferences YAML + hotwords.txt
- `.env` — API keys (Volcano ASR only); never commit this file

## Stage outputs (per-episode directory `output/<ep-id>/`)

| Path | Written by |
|------|------------|
| `input/audio_meta.json` | `prepare_audio.py` |
| `input/track_offsets_ms` (in `audio_meta.json`) | `align_tracks.py` |
| `1_transcribe/words.json` | `transcribe_merge.py` |
| `1_transcribe/sentences.json` | `make_sentences.py` |
| `2_analysis/rough_cuts.json` | **Agent** (reads sentences.json + rules) |
| `2_analysis/fine_cuts.json` | **Agent** (reads sentences.json + rules) |
| `2_analysis/self_review.json` | **Agent** (reads sentences.json + rules) |
| `3_review/review_enhanced.html` | `generate_review_html.py` |
| `3_review/delete_segments_edited.json` | `review_server.py` (POST /export) |
| `4_cut/cut.wav` | `cut_audio.py` + `trim_silences.py` |
| `5_shownotes/shownotes.md` | **Agent** (reads `cut_transcript.json` + user template) |

## Environment variables

Scripts load `.env` via `python-dotenv`, which reads **shell environment first**, then falls back to the `.env` file. So:

- **Local agents** (Claude Code, Codex CLI, Gemini CLI): create `.env` once in the repo root — every agent running in that directory picks it up automatically.
- **Remote / cloud agents**: set the same names as runtime env vars in your agent host (GitHub Actions secrets, Cowork env, etc.). No `.env` file needed.

Required at minimum:

| Variable | Purpose |
|----------|---------|
| `VOLC_API_KEY` | Volcano Engine ASR authentication |
| `VOLC_RESOURCE_ID` | Set to `volc.bigasr.auc` (a.k.a. `volc.seedasr.auc`) |

Optional but strongly recommended for files > ~50 MB:

| Variable | Purpose |
|----------|---------|
| `TOS_ACCESS_KEY` / `TOS_SECRET_KEY` | Volcano TOS access credentials |
| `TOS_BUCKET` | TOS bucket name |
| `TOS_ENDPOINT` | e.g. `tos-cn-beijing.volces.com` |

Without TOS/S3, the upload chain falls back to [uguu.se](https://uguu.se) (public, 24 h TTL) with a warning.

Old-console Volcano accounts can use `VOLC_APP_KEY` + `VOLC_ACCESS_KEY` instead of `VOLC_API_KEY`. Full reference: [docs/configuration.md](docs/configuration.md).

## Running in a remote agent (Cowork etc.)

A remote agent (e.g. Cowork, GitHub Actions, a hosted Claude Code session) runs the same SKILL.md you'd run locally, but three things change because the agent doesn't share your filesystem or browser:

### 1. Configure secrets, not `.env`

Set `VOLC_API_KEY`, `VOLC_RESOURCE_ID`, and the `TOS_*` block as runtime secrets. `python-dotenv` reads shell env first, so the same scripts work without modification.

### 2. Get recordings to the agent

The agent has no local `recordings/` dir. Two patterns:

**A. Pre-upload recordings to TOS yourself** (recommended for large dual-track files):

```bash
# On your laptop — upload to a bucket the agent's TOS keys can read:
aws s3 cp track1-host.wav s3://your-bucket/episodes/ep04/track1.wav \
    --endpoint-url https://tos-s3-cn-beijing.volces.com
```

Then trigger the agent with the URL. In the agent's run, fetch first, then point `prepare_audio.py` at the local copy:

```bash
curl -fsSLo recordings/track1.wav "https://...presigned-url..."
python shared/scripts/prepare_audio.py --ep-dir output/ep04 --track1 recordings/track1.wav
```

**B. Commit small reference clips to a private repo branch** the agent checks out. Practical for short test clips, not for full recordings.

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

## Never commit

- `.env` — contains API keys
- `recordings/` — raw audio, personal data
- `output/` — generated episode artifacts
- `configs/secrets` — legacy secrets file

## Shared memory

**Always write new instructions, rules, and memory to `AGENTS.md` only.**

Never modify `CLAUDE.md` or `GEMINI.md` directly — they only import `AGENTS.md`. This ensures Claude Code, Codex CLI, and Gemini CLI share the same context consistently.

## Project structure

- `.claude/agents/` — custom subagents for specialized tasks
- `.claude/skills/` — Claude Code skills (slash commands)
- `.claude/rules/` — modular rules auto-loaded into context
- `.codex/skills/` — Codex CLI skills
- `.codex/prompts/` — Codex CLI custom slash commands
- `.gemini/skills/` — Gemini CLI skills
- `.gemini/commands/` — Gemini CLI custom slash commands (TOML)
- `.mcp.json` — MCP server configuration
