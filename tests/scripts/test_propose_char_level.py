"""Tests for propose_char_level.py — deterministic word-level cut proposals.

Critical invariant: every proposal's start_ms/end_ms is derived from word
timestamps in the input words.json. No ratio-based char→time mapping.
"""
import json, subprocess
from pathlib import Path

REPO = Path("/Users/houyuxin/08Coding/podcast-cutter-skills")
SCRIPT = REPO / "shared/scripts/propose_char_level.py"


def _make_words(items):
    """Helper: list of (idx, speaker, text, start_ms, end_ms) → words dict."""
    return {"words": [
        {"idx": idx, "speaker": spk, "text": text,
         "start_ms": s, "end_ms": e, "confidence": 1.0,
         "blank_after_ms": 0, "emotion": "neutral", "lid": "zh"}
        for idx, spk, text, s, e in items
    ]}


def _run(words_path: Path, out_path: Path, label: str = "coarse"):
    r = subprocess.run(
        ["python", str(SCRIPT),
         "--input-words", str(words_path),
         "--output", str(out_path),
         "--label", label],
        check=True, capture_output=True, text=True, cwd=str(REPO),
    )
    return r


def test_stutter_3plus_same_char_kept_last(tmp_path):
    words = _make_words([
        (0, "S1", "我", 1000, 1100),
        (1, "S1", "我", 1150, 1250),
        (2, "S1", "我", 1300, 1400),
        (3, "S1", "觉", 1450, 1550),
        (4, "S1", "得", 1550, 1650),
    ])
    wp = tmp_path / "words.json"
    wp.write_text(json.dumps(words))
    op = tmp_path / "char_level.json"
    _run(wp, op)
    proposals = json.loads(op.read_text())["proposals"]
    stutters = [p for p in proposals if p["category"] == "stutter"]
    assert len(stutters) == 1
    p = stutters[0]
    # Should delete first 2 (1000–1250) and keep last 我 at 1300+
    assert p["start_ms"] <= 1000
    assert p["end_ms"] <= 1300, f"should not include the kept third 我; got end={p['end_ms']}"


def test_no_stutter_for_2_repetitions(tmp_path):
    words = _make_words([
        (0, "S1", "我", 1000, 1100),
        (1, "S1", "我", 1150, 1250),
        (2, "S1", "觉", 1300, 1400),
    ])
    wp = tmp_path / "words.json"
    wp.write_text(json.dumps(words))
    op = tmp_path / "out.json"
    _run(wp, op)
    proposals = json.loads(op.read_text())["proposals"]
    assert not any(p["category"] == "stutter" for p in proposals)


def test_stutter_doesnt_cross_speaker(tmp_path):
    words = _make_words([
        (0, "S1", "我", 1000, 1100),
        (1, "S2", "我", 1150, 1250),
        (2, "S1", "我", 1300, 1400),
    ])
    wp = tmp_path / "words.json"
    wp.write_text(json.dumps(words))
    op = tmp_path / "out.json"
    _run(wp, op)
    proposals = json.loads(op.read_text())["proposals"]
    assert not any(p["category"] == "stutter" for p in proposals)


def test_filler_run_4plus_consecutive(tmp_path):
    words = _make_words([
        (0, "S1", "嗯", 1000, 1100),
        (1, "S1", "啊", 1150, 1250),
        (2, "S1", "呃", 1300, 1400),
        (3, "S1", "嗯", 1450, 1550),
        (4, "S1", "我", 1600, 1700),
    ])
    wp = tmp_path / "words.json"
    wp.write_text(json.dumps(words))
    op = tmp_path / "out.json"
    _run(wp, op)
    proposals = json.loads(op.read_text())["proposals"]
    fillers = [p for p in proposals if p["category"] == "filler-run"]
    assert len(fillers) == 1
    p = fillers[0]
    assert p["start_ms"] <= 1000
    assert p["end_ms"] >= 1550 and p["end_ms"] < 1700


def test_marker_phrase_exact_word_match(tmp_path):
    # Build words spelling "考真问题…稍等我耳机掉了对…" — marker should land on
    # 稍等我 only, not earlier 考真 content.
    words = _make_words([
        (0, "S1", "考", 100, 200),
        (1, "S1", "真", 200, 300),
        (2, "S1", "问", 300, 400),
        (3, "S1", "题", 400, 500),
        (4, "S1", "稍", 5000, 5100),
        (5, "S1", "等", 5100, 5200),
        (6, "S1", "我", 5200, 5300),
        (7, "S1", "耳", 5300, 5400),
        (8, "S1", "机", 5400, 5500),
        (9, "S1", "掉", 5500, 5600),
        (10, "S1", "了", 5600, 5700),
    ])
    wp = tmp_path / "words.json"
    wp.write_text(json.dumps(words))
    op = tmp_path / "out.json"
    _run(wp, op)
    proposals = json.loads(op.read_text())["proposals"]
    markers = [p for p in proposals if p["category"] == "marker"]
    assert len(markers) >= 1
    p = markers[0]
    # Must land at the actual 稍等我 timing (5000+), not the earlier 考真 (100s)
    assert p["start_ms"] >= 4900, f"marker landed at {p['start_ms']} but 稍等我 is at 5000"
    assert p["end_ms"] >= 5300


def test_marker_doesnt_match_across_speakers(tmp_path):
    words = _make_words([
        (0, "S1", "稍", 1000, 1100),
        (1, "S2", "等", 1100, 1200),  # different speaker — should not match
        (2, "S1", "我", 1200, 1300),
    ])
    wp = tmp_path / "words.json"
    wp.write_text(json.dumps(words))
    op = tmp_path / "out.json"
    _run(wp, op)
    proposals = json.loads(op.read_text())["proposals"]
    assert not any(p["category"] == "marker" for p in proposals)


def test_habit_run_3plus_within_5s_same_speaker(tmp_path):
    # 就是 appears 3 times within 4 seconds by S1
    words = _make_words([
        (0, "S1", "就是", 1000, 1500),
        (1, "S1", "我", 1500, 1700),
        (2, "S1", "觉得", 1700, 2000),
        (3, "S1", "就是", 3000, 3500),
        (4, "S1", "这", 3500, 3700),
        (5, "S1", "件事", 3700, 4000),
        (6, "S1", "就是", 4500, 5000),
    ])
    wp = tmp_path / "words.json"
    wp.write_text(json.dumps(words))
    op = tmp_path / "out.json"
    _run(wp, op)
    proposals = json.loads(op.read_text())["proposals"]
    habits = [p for p in proposals if p["category"] == "habit"]
    # 3 instances within 4500-1000=3.5s window; should propose
    assert len(habits) >= 1


def test_proposal_timestamps_are_word_aligned(tmp_path):
    """Critical: every proposal start/end must equal a word boundary ±100ms padding."""
    words = _make_words([
        (0, "S1", "我", 1000, 1100),
        (1, "S1", "我", 1150, 1250),
        (2, "S1", "我", 1300, 1400),
        (3, "S1", "嗯", 2000, 2100),
        (4, "S1", "啊", 2150, 2250),
        (5, "S1", "呃", 2300, 2400),
        (6, "S1", "嗯", 2450, 2550),
        (7, "S1", "Sorry我", 3000, 3500),
    ])
    wp = tmp_path / "words.json"
    wp.write_text(json.dumps(words))
    op = tmp_path / "out.json"
    _run(wp, op)
    proposals = json.loads(op.read_text())["proposals"]
    word_starts = {w["start_ms"] for w in words["words"]}
    word_ends = {w["end_ms"] for w in words["words"]}
    for p in proposals:
        # start_ms must be within 200ms of some word's start; end_ms within 200ms of some word's end
        assert any(abs(p["start_ms"] - ws) <= 200 for ws in word_starts), \
            f"proposal start {p['start_ms']} not aligned to any word boundary"
        assert any(abs(p["end_ms"] - we) <= 200 for we in word_ends), \
            f"proposal end {p['end_ms']} not aligned to any word boundary"


def test_label_in_id(tmp_path):
    """--label coarse → ids start with 'coarse-'; --label fine → 'fine-'."""
    words = _make_words([
        (0, "S1", "我", 1000, 1100),
        (1, "S1", "我", 1150, 1250),
        (2, "S1", "我", 1300, 1400),
    ])
    wp = tmp_path / "words.json"
    wp.write_text(json.dumps(words))
    op = tmp_path / "out.json"
    _run(wp, op, label="coarse")
    proposals = json.loads(op.read_text())["proposals"]
    assert proposals
    assert all(p["id"].startswith("coarse-") for p in proposals)

    _run(wp, op, label="fine")
    proposals = json.loads(op.read_text())["proposals"]
    assert all(p["id"].startswith("fine-") for p in proposals)
