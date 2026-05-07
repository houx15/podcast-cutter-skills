"""Tests for shared.scripts.lib.audio_constants."""
from __future__ import annotations

from shared.scripts.lib import audio_constants as ac


def test_lufs_target_is_apple_podcasts_compatible() -> None:
    assert ac.LUFS_TARGET == -16
    assert ac.TRUE_PEAK_DB == -1.5
    assert ac.LRA == 11


def test_splice_xfade_is_25_ms() -> None:
    assert ac.SPLICE_XFADE_MS == 25


def test_golden_quote_count_is_4_to_5() -> None:
    assert ac.MIN_QUOTE_COUNT == 4
    assert ac.MAX_QUOTE_COUNT == 5
    assert ac.MIN_QUOTE_COUNT < ac.MAX_QUOTE_COUNT


def test_volume_check_threshold_catches_silence_trap() -> None:
    """podcastcut 反馈记录 2026-02-02: -91 dB silence after a bad cut."""
    assert ac.MIN_OUTPUT_PEAK_DB == -10  # any quieter is suspicious


def test_constants_are_immutable_frozen_module() -> None:
    """Constants module should not have setters or behavior."""
    with_callable = [
        name for name in dir(ac)
        if not name.startswith("_") and callable(getattr(ac, name))
    ]
    assert with_callable == [], f"audio_constants must be data-only: {with_callable}"
