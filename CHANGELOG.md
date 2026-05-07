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
