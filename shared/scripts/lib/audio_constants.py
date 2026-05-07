"""Tunable audio defaults for the podcast cutter pipeline.

This module is intentionally data-only: no functions, no classes with methods.
Every constant should have a citation in either the spec
(docs/superpowers/specs/2026-05-07-podcast-cutter-mvp-design.md) or
docs/后期/反馈记录.md once that file is ported.
"""
from __future__ import annotations

# Loudness target (Apple Podcasts / spec §5.3 step 5.1).
LUFS_TARGET: int = -16
TRUE_PEAK_DB: float = -1.5
LRA: int = 11

# Sample-accurate splice (spec §4.4: cut_audio.py crossfade per splice).
SPLICE_XFADE_MS: int = 25

# Inter-quote crossfade in the opening montage (spec §5.3 step 6.3 #3).
MONTAGE_XFADE_MS: int = 400

# Main-body to outro crossfade (spec §5.3 step 6.3 #6).
OUTRO_XFADE_MS: int = 3000

# Per-quote in/out micro-fade to prevent click/pop (spec §5.3 step 6.3 #2).
QUOTE_FADE_IN_MS: int = 30
QUOTE_FADE_OUT_MS: int = 50

# Continuous music bed levels (spec §5.3 step 6.3 #4 / podcastcut 反馈记录 2026-02-21).
MUSIC_BED_VOICE_LEVEL: float = 0.08
MUSIC_BED_TRANSITION_LEVEL: float = 1.0
MUSIC_BED_RAMP_MS: int = 1500

# Golden quote count invariants (spec §4.6 / §5.3 step 6.3 #1).
MIN_QUOTE_COUNT: int = 4
MAX_QUOTE_COUNT: int = 5

# Cut-point silence detection (spec §5.4 / podcastcut 质检 Layer A).
CUT_POINT_SILENCE_MS: int = 300

# Head/tail trim threshold (spec §5.2 stage 4.1 trim_silences).
TRIM_HEAD_TAIL_MS: int = 200

# Output sanity check (podcastcut 反馈记录 2026-02-02 -91 dB trap).
MIN_OUTPUT_PEAK_DB: float = -10

# Volcano hard limits (docs/volcano_asr.md error 45000132).
VOLCANO_MAX_AUDIO_BYTES: int = 512 * 1024 * 1024  # 512 MB

# Output encoding (spec §2 final.mp3 192 VBR).
MP3_OUTPUT_BITRATE: str = "192k"
MP3_OUTPUT_VBR: str = "2"  # ffmpeg libmp3lame -q:a 2 ≈ V0
