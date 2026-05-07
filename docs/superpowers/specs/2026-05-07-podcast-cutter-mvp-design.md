# Podcast Cutter Skills — MVP Design (Single-Track, Claude Code)

**Status**: design approved, awaiting implementation plan
**Date**: 2026-05-07
**Author**: houyuxin + Claude (brainstorming)
**Phase**: MVP (single-track, Claude Code only). Multi-track + cross-agent (Codex / Gemini) portability is a separate spec/plan/implement cycle.

---

## 1. Goals & non-goals

### Goals (MVP)
1. End-to-end Chinese-podcast cutting pipeline runnable from Claude Code.
2. Volcano Engine v3 big-model ASR (`volc.seedasr.auc`) for Chinese transcription with word-level timestamps and speaker info.
3. Six-stage pipeline matching the user's mental model: **转录 → 分析 → 粗剪+精剪 → 音频处理(响度+降噪) → 封装(金句开头+配乐) → 验证(3 层质检)**.
4. Both single-merged-audio and 2-track input supported (2-track is the higher-quality path).
5. AI proposes ~10 candidate 金句, user picks 4–5 in a review HTML page; opening montage enforces alternating speakers.
6. User-supplied music (intro/outro) with bundled royalty-free fallback; continuous music bed with dynamic ducking.
7. All audio processing local (ffmpeg `loudnorm` + `arnndn` RNNoise). No paid cloud audio APIs required for MVP.
8. Three-layer 质检 (data / signal / semantic) plus a final 同听 HTML review.
9. Domain-specific reviewer subagents (spec-drift / ffmpeg-invariants / prompt-eval / listening-spot-check) gate quality.

### Non-goals (deferred to Phase 2)
- N-track (>2) handling. Architecture supports it; tests and gold sets do not.
- Cross-agent invocation from Codex CLI / Gemini CLI. Repo layout reserves `.codex/` `.gemini/` slots; symlinks/mirrors arrive in Phase 2.
- Self-evolving rules loop (podcastcut's 自进化). Hooks reserved (`feedback_for_learning` field), implementation deferred.
- MCP server wrapping the CLI scripts. Scripts are MCP-friendly today (CLI in, JSON out), but the wrapper is Phase 2.
- Web UI replacing review HTMLs. Static HTML + small local server is sufficient.

### Background reference
- Closest-shape reference: `reference/podcastcut-skills/` — Claude Skills, 8-stage pipeline, but Aliyun FunASR (not Volcano) and missing 响度/降噪/金句 stages.
- Closest-ASR reference: `reference/autocut-skills/` — Volcano-based, but uses an older v1 endpoint and is a video-CLI shape.
- Volcano API source of truth: `docs/volcano_asr.md` (v3 big-model 录音文件识别, 豆包2.0 / `volc.seedasr.auc`).

---

## 2. Architecture overview

Four Claude Code Skills (slash commands), with a single shared `shared/` directory holding all scripts, templates, music assets, rules, and eval data.

```
用户:  /podcast-cut path/to/audio.mp3 [--track2 path/to/track2.mp3]

┌─────────────────────────────────────────────────────────────────┐
│  /podcast-cut-安装   (one-time)                                  │
│  - check node, ffmpeg, python, ffmpeg arnndn model              │
│  - write .env template (Volcano keys + upload backend)          │
│  - fetch RNNoise model + bundled royalty-free intro/outro       │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  /podcast-cut-剪播客   (stages 1-4)                              │
│  1. 转录   Volcano AUC submit → poll → word-level JSON          │
│  2. 分析   LLM rough (paragraph) + fine (word) + self-review    │
│  3. 审查   review_enhanced.html (file-backed state)             │
│           → delete_segments_edited.json                         │
│  4. 剪辑   cut_audio.py (sample-accurate) + trim_silences       │
│           → cut.wav                                             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  /podcast-cut-后期   (stages 5-6)                                │
│  5. 音频处理  arnndn → loudnorm I=-16/TP=-1.5/LRA=11           │
│              → clean.wav                                        │
│  6. 封装                                                        │
│     - LLM nominates ~10 golden quote candidates                 │
│     - User picks 4-5 in review_packaging.html                   │
│     - Mini-montage (acrossfade + ducking)                       │
│     - Continuous music bed (volume=eval=frame, NO amix)         │
│     - intro music ↘ duck → quotes → main body → outro           │
│     → final.mp3 + timeline_manifest.json                        │
│     - Show notes: chapters / titles / description (LLM)         │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  /podcast-cut-质检   (stage 7, optional)                         │
│  Layer A 数据  delete-range validity, intentional-fine-edit     │
│                whitelist, cut-point silence, large-deletes      │
│  Layer B 信号  spectral_jump + unnatural_silence (podcast mode  │
│                ignores energy_jump), LUFS/true-peak             │
│  Layer C 语义  re-transcribe final → LCS align main_body region │
│                only; assert each golden_quote ≈ source_text     │
│  → review_final.html (同听 review)                              │
└─────────────────────────────────────────────────────────────────┘
```

**Per-stage idempotency**: each stage writes to its own `<stage>/` subdirectory under `output/<episode-id>/`. Removing the directory triggers re-run from that stage; other stages untouched.

**Two-track branch**: in stage 1.0 (`prepare_audio.py`), if `--track2` supplied, both tracks ASR'd separately (no diarization needed; speaker = track of origin), word streams merged by `start_ms`. Single-track path uses Volcano `enable_speaker_info=true`.

---

## 3. Repository & runtime layout

### 3.1 Repository layout

```
podcast-cutter-skills/
├── .claude/
│   ├── skills/
│   │   ├── podcast-cut-安装/SKILL.md
│   │   ├── podcast-cut-剪播客/SKILL.md
│   │   ├── podcast-cut-后期/SKILL.md
│   │   └── podcast-cut-质检/SKILL.md
│   └── agents/
│       ├── spec-drift-reviewer.md
│       ├── ffmpeg-invariants-reviewer.md
│       ├── prompt-eval-reviewer.md
│       └── listening-spot-check-reviewer.md
├── .codex/        # phase 2: mirror or symlink
├── .gemini/       # phase 2: mirror or symlink
├── shared/
│   ├── scripts/
│   │   ├── install/
│   │   │   ├── check_deps.sh
│   │   │   ├── fetch_assets.sh
│   │   │   └── verify_volcano.py
│   │   ├── prepare_audio.py
│   │   ├── volcano_submit.py
│   │   ├── volcano_query.py
│   │   ├── transcribe_merge.py
│   │   ├── make_sentences.py
│   │   ├── analyze_rough.py
│   │   ├── analyze_fine.py
│   │   ├── self_review.py
│   │   ├── generate_review_html.py
│   │   ├── review_server.py
│   │   ├── cut_audio.py
│   │   ├── trim_silences.py
│   │   ├── audio_clean.py
│   │   ├── pick_golden_quotes.py
│   │   ├── generate_packaging_html.py
│   │   ├── package_final.py
│   │   ├── generate_show_notes.py
│   │   ├── qc_data.py
│   │   ├── qc_signal.py
│   │   ├── qc_ai_listen.py        # optional, Gemini
│   │   ├── qc_semantic.py
│   │   ├── qc_report.py
│   │   └── lib/
│   │       ├── config.py          # loads .env once
│   │       ├── volcano_client.py  # auto-detects old/new console headers
│   │       ├── upload.py          # TOS → S3 → uguu fallback
│   │       ├── audio_constants.py # default thresholds, LUFS, fade ms
│   │       ├── ffmpeg_wrap.py     # post-cut volumedetect check, log capture
│   │       └── json_io.py
│   ├── templates/
│   │   ├── review_enhanced.html
│   │   ├── review_packaging.html
│   │   └── review_final.html
│   ├── assets/music/              # bundled royalty-free intro/outro
│   ├── rules/
│   │   ├── editing/               # ported from podcastcut 基础剪辑规则/
│   │   │   ├── 1-核心原则.md
│   │   │   └── ...
│   │   └── users/<userId>/
│   │       ├── preferences.yaml
│   │       └── hotwords.txt       # fed to Volcano corpus.context.hotwords
│   ├── eval/
│   │   └── gold/                  # ported from podcastcut/剪播客/eval/
│   └── test_fixtures/
│       ├── tiny_2track/
│       ├── tiny_1track/
│       ├── silence_only/
│       └── over_512mb_simulated/
├── docs/
│   ├── volcano_asr.md             # existing
│   ├── 剪播客/                    # detailed stage docs (kept out of SKILL.md)
│   │   ├── 阶段1-转录.md
│   │   ├── 阶段2-分析.md
│   │   ├── 阶段3-审查.md
│   │   └── 阶段4-剪辑.md
│   ├── 后期/
│   │   ├── 反馈记录.md            # ported verbatim from podcastcut, gold
│   │   └── 封装算法.md
│   ├── 质检/
│   │   └── ...
│   └── superpowers/specs/
│       └── 2026-05-07-podcast-cutter-mvp-design.md  # this file
├── reference/                     # existing, unmodified
├── .env.example
├── .mcp.json                      # existing
├── AGENTS.md  CLAUDE.md  GEMINI.md  # existing
└── CHANGELOG.md
```

### 3.2 Per-episode runtime layout

```
output/2026-05-07-ep01/
├── input/
│   ├── working_track1.wav         # normalized, original sample-rate, 16-bit, mono
│   ├── working_track2.wav         # (only when 2-track)
│   └── audio_meta.json
├── 1_transcribe/
│   ├── volcano_raw_track1.json
│   ├── volcano_raw_track2.json    # (only when 2-track)
│   ├── words.json                 # canonical (see §4.1)
│   └── sentences.json
├── 2_analysis/
│   ├── rough_cuts.json
│   ├── fine_cuts.json
│   └── self_review.json
├── 3_review/
│   ├── review_enhanced.html
│   ├── review_state.json          # file-backed, written by review_server.py
│   └── delete_segments_edited.json
├── 4_cut/
│   └── cut.wav
├── 5_clean/
│   └── clean.wav
├── 6_packaging/
│   ├── golden_candidates.json
│   ├── golden_picked.json
│   ├── review_packaging.html
│   ├── final.mp3
│   ├── timeline_manifest.json     # see §4.6
│   └── show_notes/
│       ├── chapters.txt
│       ├── titles.md
│       └── description.md
└── 7_qc/
    ├── qc_data.json
    ├── qc_signal.json
    ├── qc_ai.json                 # optional
    ├── qc_semantic.json
    ├── qc_summary.md
    └── review_final.html
```

---

## 4. Data flow & JSON schemas

All time fields are integer milliseconds. Speaker IDs are `S1`, `S2`, …, with optional `name` populated later.

### 4.1 `1_transcribe/words.json` — canonical spine

```json
{
  "episode_id": "2026-05-07-ep01",
  "duration_ms": 7200000,
  "source": {
    "tracks": ["working_track1.wav", "working_track2.wav"],
    "mode": "two_track"
  },
  "speakers": [
    { "id": "S1", "name": null, "track": "working_track1.wav" },
    { "id": "S2", "name": null, "track": "working_track2.wav" }
  ],
  "words": [
    {
      "idx": 0,
      "speaker": "S1",
      "start_ms": 740,
      "end_ms": 860,
      "text": "这",
      "confidence": 0.97,
      "blank_after_ms": 0,
      "emotion": null,
      "lid": null
    }
  ]
}
```

When `mode == "single_track"`, both `tracks` arrays point to the same merged file and `speaker` is taken from Volcano `enable_speaker_info` output.

### 4.2 `1_transcribe/sentences.json`

Sentences reference word index ranges in `words.json`:

```json
{
  "sentences": [
    {
      "id": 0,
      "speaker": "S1",
      "start_ms": 740,
      "end_ms": 4200,
      "word_idx_start": 0,
      "word_idx_end": 23,
      "text": "这是字节跳动今日头条母公司。"
    }
  ]
}
```

### 4.3 `2_analysis/rough_cuts.json` and `fine_cuts.json`

```json
{
  "deletes": [
    {
      "start_ms": 12300,
      "end_ms": 28100,
      "level": "rough",
      "reason": "录前闲聊",
      "source": "ai_rough",
      "confidence": 0.83,
      "evidence_word_idx": [42, 138]
    }
  ]
}
```

`level ∈ {rough, fine}`. `source ∈ {ai_rough, ai_fine, self_review, user}`.

### 4.4 `3_review/delete_segments_edited.json` — single source of truth post-review

```json
{
  "deletes": [
    {
      "start_ms": 12300,
      "end_ms": 28100,
      "level": "rough",
      "reason": "录前闲聊",
      "source": "ai_rough",
      "user_action": "kept"
    }
  ],
  "user_notes": "前 3 分钟全部砍",
  "feedback_for_learning": [
    { "what": "AI 把 X 当口癖删了", "should_be": "保留" }
  ]
}
```

`user_action ∈ {kept, edited, added, rejected_by_user}`.

`cut_audio.py` reads only this file and computes KEEP-ranges = `[0, duration] − merge(deletes)` (merge collapses overlapping/adjacent deletes). Crossfade 25 ms at every splice.

### 4.5 `6_packaging/golden_candidates.json` and `golden_picked.json`

Candidates (AI-nominated, ~10 entries):

```json
{
  "candidates": [
    {
      "id": "g7",
      "speaker": "S1",
      "start_ms": 1842300,
      "end_ms": 1849600,
      "text": "做播客最难的不是开始，是……",
      "score": 0.87,
      "rationale": "完整观点 + 情绪起伏 + 7s 适合开头节奏",
      "duration_ms": 7300
    }
  ]
}
```

User selection (via `review_packaging.html`):

```json
{
  "picked": ["g7", "g3", "g11", "g2"],
  "order": ["g7", "g3", "g11", "g2"],
  "intro_music": "shared/assets/music/intro_default.mp3",
  "outro_music": "shared/assets/music/outro_default.mp3",
  "duck_db": -14
}
```

`package_final.py` validates:
- `4 ≤ len(picked) ≤ 5`
- speakers in `order` alternate (no two consecutive same speaker)

### 4.6 `6_packaging/timeline_manifest.json` — structural truth for reviewers

Written by `package_final.py` while it splices the final file. Reviewers consume this to apply different rules to different regions and to suppress false positives on intentional structures (e.g. golden quote duplication is by design, not a bug).

Regions tile the timeline `[0, duration_ms]` with no gaps and no overlaps. Crossfade regions describe the *interval during which* two clips ramp together; the audio in that interval is the mix, but conceptually it's a transition. Adjacent regions meet at the boundary timestamp (e.g. quote ends at `14000`, xfade is `14000–14400`, next quote starts at `14400`).

```json
{
  "duration_ms": 4912000,
  "regions": [
    { "kind": "intro_music", "start_ms": 0, "end_ms": 8000,
      "source": "shared/assets/music/intro_default.mp3" },
    { "kind": "golden_quote", "start_ms": 8000, "end_ms": 14000,
      "candidate_id": "g7", "speaker": "S1",
      "source_start_ms": 1842300, "source_end_ms": 1849600,
      "source_text": "做播客最难的不是开始，是…" },
    { "kind": "intra_montage_xfade", "start_ms": 14000, "end_ms": 14400 },
    { "kind": "golden_quote", "start_ms": 14400, "end_ms": 19000, "...": "..." },
    { "kind": "montage_to_main_xfade", "start_ms": 38800, "end_ms": 41800 },
    { "kind": "main_body", "start_ms": 41800, "end_ms": 4898000,
      "source": "5_clean/clean.wav" },
    { "kind": "main_to_outro_xfade", "start_ms": 4898000, "end_ms": 4901000 },
    { "kind": "outro_music", "start_ms": 4901000, "end_ms": 4912000,
      "source": "shared/assets/music/outro_default.mp3" }
  ],
  "invariants": {
    "golden_quote_count": 4,
    "alternating_speakers": true,
    "regions_cover_full_duration": true,
    "regions_no_overlap": true
  }
}
```

### 4.7 Data-flow diagram

```
input/track*.wav
       │  (Volcano v3 ASR per track + merge by timestamp)
       ▼
1_transcribe/words.json  ◄─ canonical, all downstream depends on this
       │
       ▼
1_transcribe/sentences.json
       │  (LLM rough + LLM fine + self-review)
       ▼
2_analysis/{rough_cuts.json, fine_cuts.json, self_review.json}
       │  (rendered in review HTML, user edits live in review_state.json)
       ▼
3_review/delete_segments_edited.json  ◄─ single source of truth post-human
       │  (cut_audio.py sample-accurate splice + 25ms crossfade)
       ▼
4_cut/cut.wav
       │  (arnndn → loudnorm 2-pass)
       ▼
5_clean/clean.wav
       │  (LLM nominate → user pick → splice + music bed)
       ▼
6_packaging/{golden_candidates.json, golden_picked.json,
              final.mp3, timeline_manifest.json, show_notes/}
       │  (3-layer QC reading timeline_manifest.json for region scoping)
       ▼
7_qc/{qc_data.json, qc_signal.json, qc_semantic.json,
      qc_summary.md, review_final.html}
```

### 4.8 Two deliberate design choices

1. **Persist deletes, not keeps.** Deletes are human-authored semantic ("this is filler"); keeps are mechanical complement and can be re-derived. Cuts re-run from the same `delete_segments_edited.json` always produce identical output.
2. **Every delete carries `source` and `user_action`.** This is the raw material for the future self-evolving rules loop (Phase 2). MVP doesn't read it, but recording it costs nothing and would be expensive to retrofit.

---

## 5. Per-skill responsibilities

Top-level rule: each `SKILL.md` stays slim (流程 + 接口 + 何时调). Detail goes into `docs/<skill>/...`. The 1912-line `剪播客/SKILL.md` in podcastcut is the anti-pattern.

### 5.1 `podcast-cut-安装`

One-time environment setup. SKILL.md content: register symlinks, verify deps, write `.env`, fetch model + default music, self-test.

| Script | Purpose |
|---|---|
| `shared/scripts/install/check_deps.sh` | Detect `node>=18 / ffmpeg>=6 / python>=3.10`; print install commands for missing items |
| `shared/scripts/install/fetch_assets.sh` | Download RNNoise model (`std.rnnn`) and bundled royalty-free intro/outro to `shared/assets/` |
| `shared/scripts/install/verify_volcano.py` | Send a 5-second sample to Volcano to confirm key, headers, and routing all work |

### 5.2 `podcast-cut-剪播客` (stages 1–4)

Original audio → user-reviewed `delete_segments_edited.json` → `cut.wav`.

SKILL.md structure:
- Overview (flow, inputs, outputs)
- Four-stage short description, one paragraph per stage, links to `docs/剪播客/阶段N-*.md` for detail
- Error mode table (Volcano error codes, upload failures, ffmpeg failures)

| Stage | Script | In | Out |
|---|---|---|---|
| 1.0 prepare | `prepare_audio.py` | user audio (1 or 2 files) | `working_track*.wav` (16-bit/mono per track), `audio_meta.json` |
| 1.1 upload | `lib/upload.py` | working WAV | URL (TOS / S3 / uguu, depending on env) |
| 1.2 ASR | `volcano_submit.py` + `volcano_query.py` | URL × n | `volcano_raw_track*.json` |
| 1.3 merge | `transcribe_merge.py` | volcano_raw × n | `words.json` |
| 1.4 sentences | `make_sentences.py` | words.json | `sentences.json` |
| 2.1 rough | `analyze_rough.py` (LLM) | sentences + user prefs | `rough_cuts.json` |
| 2.2 fine | `analyze_fine.py` (LLM) | sentences + words | `fine_cuts.json` |
| 2.3 self-review | `self_review.py` (LLM) | rough + fine + rules | `self_review.json` |
| 3.0 review HTML | `generate_review_html.py` + `review_server.py` | sentences + words + cuts + audio | `review_enhanced.html`, `review_state.json` (file-backed via local server) |
| 3.1 export | (manual) | browser | `delete_segments_edited.json` (incl. `feedback_for_learning`) |
| 4.0 cut | `cut_audio.py` | working_track*.wav + delete_segments_edited.json | `cut.wav` (sample-accurate, 25 ms crossfade per splice) |
| 4.1 trim | `trim_silences.py` | cut.wav | `cut.wav` (overwrite; head/tail silence trimmed to 200 ms) |

**Editing rules and user preferences**: `shared/rules/editing/*.md` (ported from podcastcut `基础剪辑规则/`) feeds the system prompts of `analyze_rough.py` / `analyze_fine.py`. `shared/rules/users/<userId>/preferences.yaml` overlays user-specific deltas. Hotwords in `shared/rules/users/<userId>/hotwords.txt` map to Volcano `corpus.context.hotwords`.

### 5.3 `podcast-cut-后期` (stages 5–6)

`cut.wav` → `final.mp3` + `timeline_manifest.json` + show notes.

SKILL.md links to `docs/后期/反馈记录.md` (ported verbatim from podcastcut — the FFmpeg gotchas there are battle-tested) and `docs/后期/封装算法.md` (continuous music bed details).

| Stage | Script | In | Out |
|---|---|---|---|
| 5.0 denoise | `audio_clean.py --denoise` | cut.wav | `cut.dn.wav` (`-af arnndn=m=std.rnnn`) |
| 5.1 loudness | `audio_clean.py --loudnorm` | cut.dn.wav | `clean.wav` (`loudnorm=I=-16:TP=-1.5:LRA=11`, 2-pass) |
| 6.0 nominate | `pick_golden_quotes.py` (LLM) | sentences + user prefs | `golden_candidates.json` (~10) |
| 6.1 review | `generate_packaging_html.py` + `review_server.py` | candidates + clean.wav | `review_packaging.html` |
| 6.2 export | (manual) | browser | `golden_picked.json` |
| 6.3 splice | `package_final.py` | golden_picked + clean.wav + music | `final.mp3` + `timeline_manifest.json` |
| 6.4 show notes | `generate_show_notes.py` (LLM) | sentences + manifest | `chapters.txt` (offset-corrected), `titles.md`, `description.md` |

**`package_final.py` algorithm** (inherited from podcastcut `mix_highlights_with_music.py`):
1. Validate `golden_picked.json` (count 4–5, alternating speakers; otherwise hard fail with actionable message).
2. Extract each quote clip from `clean.wav`; apply `afade in=30ms / out=50ms` per clip to prevent click/pop.
3. Crossfade between adjacent quotes: `acrossfade=d=0.4:c1=tri:c2=tri`.
4. Build a continuous intro music bed using `volume=eval=frame:volume='if(...,1.0,0.08)'` with 1.5 s ramps. Voice regions duck to 0.08; transitions stay at 1.0.
5. Mix bed + voice with `amerge=inputs=2,pan=stereo|c0=c0+c2|c1=c1+c3`. **Never `amix`** (per podcastcut 反馈记录 2026-02-14: amix normalizes inputs, drops voice).
6. After main_body, apply `afade out` over its last 3 s, then `acrossfade=d=3` into outro music.
7. Encode mp3 192 kbps VBR. Run `volumedetect` post-encode and assert `max_volume > -10 dB` (catches the -91 dB silence trap from 反馈记录 2026-02-02).
8. Write `timeline_manifest.json` describing every region with absolute timestamps in the final file.

### 5.4 `podcast-cut-质检` (stage 7)

Three-layer check + 同听 review HTML. Architecture inherited from podcastcut 质检; only the transcription engine swaps.

| Layer | Script | Checks |
|---|---|---|
| A 数据 | `qc_data.py` | delete-range validity (no negative, no overlap), intentional-fine-edit whitelist, cut-point silence (>0.3 s), large deletes (>5 s) listed for human attention. Also validates `timeline_manifest.json` invariants. |
| B 信号 | `qc_signal.py` (librosa) | spectral_jump + unnatural_silence at cut points within `main_body` only. **Skip `*_xfade` regions** (intentional). Ignore energy_jump (podcast mode — verified false-positive in podcastcut 实际运行数据 2026-02-22). Verify LUFS/true-peak. |
| B+ AI (optional) | `qc_ai_listen.py` (Gemini) | Global sample 6×30 s + Layer-A HIGH replay. Receives `timeline_manifest.json` so it doesn't flag golden quote reuse. |
| C 语义 | `qc_semantic.py` | Re-transcribe `final.mp3` via Volcano. LCS-align **only `main_body` regions** vs `sentences.json` (deletes filtered). For each `golden_quote`, assert re-transcribed text ≈ `source_text` (Levenshtein < 10%). |
| Report | `qc_report.py` | Merge layers → `qc_summary.md` + serve `review_final.html` (same review_server.py infrastructure). |

---

## 6. Quality gates (reviewer subagents)

Four custom subagents shipped in `.claude/agents/` (mirrored to `.codex/agents/` and `.gemini/agents/` in Phase 2). Each spawns with no memory of design or implementation conversation; each reads only the spec, the timeline manifest (where applicable), and a focused rule book.

| Agent | Trigger | Reads | Hard fail conditions |
|---|---|---|---|
| `spec-drift-reviewer` | every PR / per-stage merge | this spec doc + git diff | unimplemented spec items; undocumented divergence from spec |
| `ffmpeg-invariants-reviewer` | any diff touching `*.py` / `*.js` with ffmpeg or audio code | `docs/后期/反馈记录.md` (rule book) + diff | use of `amix`, `-ss` placed after `-i` when `-af` is present, missing fade in/out on extracted clips, absolute music-file paths |
| `prompt-eval-reviewer` | any diff to `analyze_*.py`, `pick_golden_quotes.py`, or `shared/rules/editing/*` | `shared/eval/gold/` + new prompt | metric regression vs baseline beyond threshold (precision/recall/F1) |
| `listening-spot-check-reviewer` | end of `/podcast-cut-后期` and `/podcast-cut-质检` runs | `final.mp3` + `timeline_manifest.json` + qc reports (Gemini API) | xfade artifact at any region boundary; golden quote unintelligible; main_body discontinuity that `qc_signal` missed |

These compose with generic gates already on the system (`superpowers:requesting-code-review`, `superpowers:verification-before-completion`). Domain agents enforce *podcast-specific* invariants those generic agents cannot know.

**Why structural manifest matters here**: without `timeline_manifest.json`, `qc_semantic` would flag every golden quote as a "missing/duplicated" content bug, and `listening-spot-check-reviewer` would flag intentional reuse as a defect. With the manifest, every reviewer scopes its rules per region kind.

---

## 7. Polish list (port-from-podcastcut deltas)

Findings from a critical scan of `reference/podcastcut-skills/`. Each item is a fix to apply during the port.

| # | Issue | Reference location | Fix |
|---|---|---|---|
| 1 | Hard-coded absolute path in SKILL.md | `剪播客/SKILL.md:135` `cd /Volumes/T9/...` | Use `$SKILL_DIR` / argv; never absolute |
| 2 | `剪播客/SKILL.md` is 1912 lines (cognitive overload) | whole file | Split: SKILL.md = overview + flow only; details → `docs/剪播客/阶段N-*.md` |
| 3 | Review HTML state in browser localStorage; "永远不要 regenerate" warnings everywhere | `剪播客/SKILL.md:39-42` | Add `review_server.py` (small Flask/Node) that PATCHes `review_state.json` on every user action. Regenerate-safe; warnings dropped |
| 4 | Aliyun-only ASR scripts | `aliyun_funasr_transcribe.sh`, `generate_subtitles_from_aliyun.js`, `identify_speakers.js` | Replace with `volcano_submit.py`, `volcano_query.py`, `transcribe_merge.py` |
| 5 | Single-track only | whole 剪播客 pipeline | New `prepare_audio.py` branches on input count; 2-track merges word streams by `start_ms`, speaker = track |
| 6 | No 响度/降噪 stage | Removed from 后期 (`后期 SKILL.md` 反馈记录 2026-02-21) but never reinstated | New stage 5 (`audio_clean.py`) between cut and 封装. ffmpeg `arnndn` + `loudnorm` 2-pass |
| 7 | DeepFilterNet (~1 GB model) for denoise | `安装/SKILL.md:54` | Use ffmpeg's built-in `arnndn` (RNNoise, ships with ffmpeg ≥4.4). Keep DeepFilterNet as opt-in `--strong-denoise` for stubborn noise |
| 8 | Upload strategy unclear (autocut uses uguu.se with no privacy warning) | `autocut/transcribe.ts:62` | `lib/upload.py` priority: ① Volcano TOS → ② S3-compat → ③ uguu.se with explicit privacy warning |
| 9 | Stray ffmpeg code outside `<details>` block | `后期/SKILL.md:836-841` | Editing artifact. Drop during port |
| 10 | API key handling scattered (env, .env, --flags) | various | `lib/config.py` loads `.env` once, exposes `cfg.volcano_api_key` etc. All scripts import |
| 11 | Volcano API supports old & new console headers | `docs/volcano_asr.md` | `volcano_client.py` auto-detects: `VOLC_API_KEY` → new (`X-Api-Key`); else `VOLC_APP_KEY+VOLC_ACCESS_KEY` → old |
| 12 | Hotwords / 术语词典 not used | autocut has it, podcastcut doesn't | Support `shared/rules/users/<userId>/hotwords.txt` → Volcano `corpus.context.hotwords` (≤5000 词) |
| 13 | 反馈记录 (FFmpeg gotchas) is gold | `后期/SKILL.md:893-984` | Port verbatim to `docs/后期/反馈记录.md`; `ffmpeg-invariants-reviewer` consumes it as rule book |
| 14 | JS/Python mixed without rationale | various | Document split: Python = audio/numerical (cut, qc, package), Node = orchestration + HTML serve |
| 15 | Default speaker count unclear | `剪播客/SKILL.md:31-37` requires user input | Default to 2 (most common); prompt only when 1-track input *and* user count not given. 2-track input bypasses this entirely |
| 16 | CHANGELOG.md discipline (good, keep) | `剪播客/CHANGELOG.md` | Adopt per-skill |
| 17 | Eval system | `剪播客/eval/` (gold sets, batch eval) | Port to `shared/eval/`; required for `prompt-eval-reviewer` |
| 18 | "Never regenerate review" prose | `剪播客/SKILL.md:39-42` | Drop entirely once #3 fixed |

---

## 8. Error handling & idempotency

### 8.1 Idempotency
Every stage writes to `<stage>/`. Re-running a stage requires `rm -rf <stage>/` (or `--force` flag). Stages assert upstream existence; fail fast with actionable message if missing.

### 8.2 Volcano error code matrix (`volcano_query.py`)

| Code | Meaning | Action |
|---|---|---|
| `20000000` | success | proceed |
| `20000001 / 20000002` | processing / queued | continue polling (5 s interval, 60 min cap) |
| `20000003` | silent audio | hard fail: "音频无人声，检查录音是否为空轨" |
| `45000001` | invalid params | hard fail; print request payload for debugging |
| `45000002` | empty audio | hard fail; ffprobe before retry |
| `45000131` | rate-limit (>500 h / 30 min) | exponential backoff (10 → 20 → 40 min); prompt user after 2 retries |
| `45000132` | >512 MB | hard fail: "音频超 512 MB Volcano 上限，建议先 ffmpeg 转 16 kHz mono mp3" |
| `45000151` | bad format | hard fail; show ffprobe output |
| `550xxxx / 55000031` | server-side / busy | retry with jitter (3 attempts) then fail |

### 8.3 Upload failures (`lib/upload.py`)
Try TOS → S3 → uguu in order. If all fail, print "no upload backend reachable" and the env vars to set. Never silently fall through to a less-private backend without explicit consent.

### 8.4 FFmpeg failures
Every shell-out captures stderr to `<stage>/ffmpeg.log`; surfaces last 20 lines on error. After every cut/concat, auto-runs `ffprobe + volumedetect` per `lib/ffmpeg_wrap.py`. The −91 dB silence trap from podcastcut 反馈记录 2026-02-02 is real — every cut output is checked.

### 8.5 Reviewer / eval failures
Do not hard-block local dev (would slow iteration). Block at gates: pre-commit hook, PR review, `superpowers:finishing-a-development-branch` step.

---

## 9. Testing strategy

### 9.1 Test fixtures (`shared/test_fixtures/`)
- `tiny_2track/` — 60 s 2-track sample (real recording, trimmed and consented for repo) + golden `words.json`, `delete_segments_edited.json`, `final.mp3` checksum.
- `tiny_1track/` — same content merged → tests speaker diarization path.
- `silence_only/` — exercises Volcano `20000003` error path.
- `over_512mb_simulated/` — synthetic; exercises pre-upload size check.

### 9.2 Unit tests (`pytest`)
- `prepare_audio.py`: format detection, sample-rate normalization, 2-track timestamp alignment.
- `transcribe_merge.py`: word-stream merge by `start_ms`, speaker assignment.
- `cut_audio.py`: KEEP-range derivation from deletes, sample-accurate splice (compare WAV checksums).
- `package_final.py`: `timeline_manifest.json` invariants — alternating speakers, region count, gap/overlap detection.
- `volcano_client.py`: header building (old vs new console), error code mapping.

### 9.3 Integration test (`make e2e`)
Full pipeline on `tiny_2track`. Asserts `final.mp3` and `timeline_manifest.json` match goldens within encoding tolerance: compare via duration + LUFS + waveform RMS, not byte-exact (mp3 encoders are not bit-reproducible across versions).

### 9.4 Eval set (`shared/eval/gold/`)
Port podcastcut `eval/eval_gold_reviewed.json` as starting baseline. `prompt-eval-reviewer` runs `analyze_fine.py` against this set and reports precision / recall / F1 vs baseline. Required gate before merging prompt changes.

### 9.5 Reviewer agents as TDD harness
The four reviewer subagents (§6) collectively form the project's TDD harness. Each gates a specific kind of change:
- Code that changes ffmpeg invocation → `ffmpeg-invariants-reviewer`
- Prompt or rule change → `prompt-eval-reviewer`
- Any merge → `spec-drift-reviewer`
- Any final-output change → `listening-spot-check-reviewer`

---

## 10. Phase-2 hooks (designed in, not implemented)

1. **Multi-agent (Codex / Gemini)**: scripts live in `shared/`, agents in `.claude/agents/`. Phase-2 work = symlink `.codex/skills/` and `.gemini/skills/` to `.claude/skills/`, mirror agents (or provide TOML for Gemini), test cross-agent invocation. `AGENTS.md` already exists and is the single source of truth for cross-agent context.
2. **N-track (>2)**: `prepare_audio.py` is designed around N tracks; today's `--track2` becomes `--track <path> --track <path> ...`; speaker count auto-derives from track count. ASR per track scales linearly. The 2-track special case is just N=2.
3. **MCP exposure**: scripts are CLI in / JSON out today. Phase-2 = wrap in MCP server. No refactor needed.
4. **Self-evolving rules** (podcastcut's 自进化): hooks reserved via `delete_segments_edited.json.feedback_for_learning` field + `shared/rules/users/`. Phase-2 = port `apply_feedback_to_rules.js` + `analyze_feedback.js` from podcastcut and wire to the user-prefs overlay.

---

## 11. Open questions (deferred to plan or implementation)

These are not design ambiguities — they are decisions that fit better in the implementation plan than the design.

1. **Specific Volcano region/endpoint** for users in mainland China vs overseas. Default `https://openspeech.bytedance.com` per docs; if latency or reachability issues appear in real use, switch to a regional endpoint.
2. **Default crossfade values** (25 ms splice, 0.4 s inter-quote, 3 s main↔outro) — taken from podcastcut 反馈记录; tunable via `lib/audio_constants.py`. Real recordings may show these need adjusting.
3. **Gemini model for `qc_ai_listen` and `listening-spot-check-reviewer`**: `gemini-2.5-flash` per podcastcut 陷阱 2 (2026-02-22). Re-verify model availability at implementation time.
4. **uguu.se reachability from mainland China**: if blocked, the third fallback may need swapping. TOS + S3 paths cover the primary case.

---

## 12. Acceptance criteria for MVP

- [ ] `/podcast-cut-安装` runs clean on a fresh macOS box; `verify_volcano.py` round-trips a sample.
- [ ] `/podcast-cut-剪播客` end-to-end on `tiny_2track` produces `cut.wav` matching golden within tolerance.
- [ ] `/podcast-cut-后期` produces `final.mp3` with valid `timeline_manifest.json` (4–5 alternating-speaker quotes, no overlaps, full coverage).
- [ ] `/podcast-cut-质检` produces `qc_summary.md` with `qc_data.json` invariants passing and Layer B + C running on `final.mp3`.
- [ ] All four reviewer agents callable; `spec-drift` and `ffmpeg-invariants` block on contrived violations.
- [ ] Real today-recording (user's 2-track + merged) processable end to end; user listens to `final.mp3` and judges it acceptable.

The last bullet is the only one that matters. Everything above exists to make it true and to keep it true.
