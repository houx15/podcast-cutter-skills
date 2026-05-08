# Project Instructions

> Podcast cutter skills toolkit

## Guidelines

This is a **Chinese podcast editing toolkit**. It turns raw recordings into a clean `cut.wav` via ASR transcription, agent analysis, and human review.

### How the agent runs a podcast episode

The agent drives the workflow by following `.claude/skills/podcast-cut-剪播客/SKILL.md` (or the Codex mirror in `.codex/skills/`). Each stage is one or more scripts:

- **Stage 1 (transcribe)**: prepare_audio → align_tracks (if dual-track) → volcano_submit/query (per track) → transcribe_merge → make_sentences
- **Stage 2 (analyze)**: agent reads sentences.json + `shared/rules/editing/*.md` + preferences.yaml, writes rough_cuts.json + fine_cuts.json + self_review.json
- **Stage 3 (review)**: generate_review_html → review_server (human reviews in browser, exports delete_segments_edited.json)
- **Stage 4 (cut)**: cut_audio → trim_silences

Each stage's output is its own file. To redo a stage, delete its output and rerun the script.

### Key files

- `shared/scripts/lib/` — config, ffmpeg_wrap, volcano_client, upload, json_io, audio_constants
- `shared/rules/editing/` — editing rules (Chinese Markdown, read by agent during analysis)
- `shared/rules/users/default/` — user preferences YAML + hotwords.txt
- `.env` — API keys (Volcano ASR only); never commit this file

### Stage outputs (per-episode directory `output/<ep-id>/`)

| Path | Written by |
|------|------------|
| `input/audio_meta.json` | prepare_audio.py |
| `input/track_offsets_ms` (in audio_meta.json) | align_tracks.py |
| `1_transcribe/words.json` | transcribe_merge.py |
| `1_transcribe/sentences.json` | make_sentences.py |
| `2_analysis/rough_cuts.json` | **Agent** (reads sentences.json + rules) |
| `2_analysis/fine_cuts.json` | **Agent** (reads sentences.json + rules) |
| `2_analysis/self_review.json` | **Agent** (reads sentences.json + rules) |
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
