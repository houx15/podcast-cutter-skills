# Changelog

## [0.2.0] — 2026-05-08

### Added
- `prepare_audio.py`: stage 1.0 — probe + mono 16-bit WAV conversion, writes `audio_meta.json`
- `volcano_submit.py` + `volcano_query.py`: stage 1.2 — Volcano Engine v3 AUC ASR submit + poll
- `transcribe_merge.py`: stage 1.3 — Volcano raw JSON → `words.json` (two-track merge by `start_ms`)
- `make_sentences.py`: stage 1.4 — `words.json` → `sentences.json` (pause/speaker/length splitting)
- `analyze_rough.py`: stage 2.1 — LLM rough cut analysis via ByteDance Ark (doubao)
- `analyze_fine.py`: stage 2.2 — LLM fine cut analysis (word-level fillers)
- `self_review.py`: stage 2.3 — LLM self-review of rough+fine cuts
- `generate_review_html.py` + `review_server.py`: stage 3.0 — review HTML + Flask state server
- `cut_audio.py`: stage 4.0 — sample-accurate splice with 25ms acrossfade per cut point
- `trim_silences.py`: stage 4.1 — head/tail silence trim (200ms budget)
- `shared/rules/editing/1-核心原则.md` + user defaults: editing rules and user preferences
- `LLMConfig` in `lib/config.py`; `openai>=1.0.0` and `flask>=3.0.0` dependencies
- `.claude/skills/podcast-cut-剪播客/SKILL.md`: skill definition for stages 1–4
- `docs/剪播客/阶段1-4`: detailed stage documentation

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
