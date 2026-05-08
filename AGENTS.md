# Project Instructions

> Podcast cutter skills toolkit

## Guidelines

This is a **Chinese podcast editing toolkit**. It turns raw recordings into a clean `cut.wav` via ASR transcription, agent analysis, and human review.

### Entry point for running a podcast episode

The primary interface is `run_pipeline.py`:

```bash
# Step 1: Transcription (automatic — runs stages 1.x):
python shared/scripts/run_pipeline.py \
  --ep-dir output/EP_ID \
  --track1 recordings/host.wav \
  [--track2 recordings/guest.wav]

# Step 2: Agent analysis — read analysis_context.md, write rough_cuts.json,
#   fine_cuts.json, self_review.json (see SKILL.md for details)

# Step 3a: Resume after analysis → generates review HTML:
python shared/scripts/run_pipeline.py --ep-dir EP_DIR --resume

# Step 3b: Resume after human review → cut.wav:
python shared/scripts/run_pipeline.py --ep-dir EP_DIR --resume
```

The pipeline skips stages whose output already exists — safe to re-run or resume after interruption.

### Key files

- `shared/scripts/run_pipeline.py` — orchestrates all stages
- `shared/scripts/lib/` — config, ffmpeg_wrap, volcano_client, upload, json_io, audio_constants
- `shared/rules/editing/` — editing rules (Chinese Markdown, used by agent analysis)
- `shared/rules/users/default/` — user preferences YAML + hotwords.txt
- `.env` — API keys (Volcano ASR only); never commit this file

### Stage outputs (per-episode directory `output/<ep-id>/`)

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

### Never commit

- `.env` — contains API keys
- `recordings/` — raw audio, personal data
- `output/` — generated episode artifacts
- `configs/secrets` — legacy secrets file

## Shared Memory

**Always write new instructions, rules, and memory to `AGENTS.md` only.**

Never modify `CLAUDE.md` or `GEMINI.md` directly - they only import `AGENTS.md`.
This ensures Claude Code, Codex CLI, and Gemini CLI share the same context consistently.

## Project Structure

- `.claude/agents/` - Custom subagents for specialized tasks
- `.claude/skills/` - Claude Code skills (slash commands)
- `.claude/rules/` - Modular rules auto-loaded into context
- `.codex/skills/` - Codex CLI skills
- `.codex/prompts/` - Codex CLI custom slash commands
- `.gemini/skills/` - Gemini CLI skills
- `.gemini/commands/` - Gemini CLI custom slash commands (TOML)
- `.mcp.json` - MCP server configuration
