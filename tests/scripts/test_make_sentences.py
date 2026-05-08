# tests/scripts/test_make_sentences.py
import json, subprocess
from pathlib import Path
import pytest

REPO = "/Users/houyuxin/08Coding/podcast-cutter-skills"


def _words_json(tmp_path, words):
    ep = tmp_path / "ep01"
    td = ep / "1_transcribe"
    td.mkdir(parents=True)
    data = {
        "episode_id": "ep01", "duration_ms": 10000,
        "source": {"tracks": ["t1.wav"], "mode": "single_track"},
        "speakers": [{"id": "S1", "name": None, "track": "t1.wav"}],
        "words": words
    }
    (td / "words.json").write_text(json.dumps(data))
    return ep


def _w(idx, speaker, start, end, text, blank=0):
    return {"idx": idx, "speaker": speaker, "start_ms": start,
            "end_ms": end, "text": text, "confidence": 0.9,
            "blank_after_ms": blank, "emotion": None, "lid": None}


def test_single_sentence(tmp_path):
    ep = _words_json(tmp_path, [
        _w(0, "S1", 0, 500, "你好", 100),
        _w(1, "S1", 600, 1000, "世界", 0),
    ])
    subprocess.run(
        ["python", "shared/scripts/make_sentences.py", "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO
    )
    sents = json.loads((ep / "1_transcribe" / "sentences.json").read_text())
    assert len(sents["sentences"]) == 1
    assert sents["sentences"][0]["text"] == "你好世界"
    assert sents["sentences"][0]["word_idx_start"] == 0
    assert sents["sentences"][0]["word_idx_end"] == 1


def test_speaker_change_splits(tmp_path):
    ep = _words_json(tmp_path, [
        _w(0, "S1", 0, 500, "你好", 0),
        _w(1, "S2", 600, 1000, "世界", 0),
    ])
    subprocess.run(
        ["python", "shared/scripts/make_sentences.py", "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO
    )
    sents = json.loads((ep / "1_transcribe" / "sentences.json").read_text())
    assert len(sents["sentences"]) == 2
    assert sents["sentences"][0]["speaker"] == "S1"
    assert sents["sentences"][1]["speaker"] == "S2"


def test_long_pause_splits(tmp_path):
    ep = _words_json(tmp_path, [
        _w(0, "S1", 0, 500, "你好", 600),   # 600ms pause → split
        _w(1, "S1", 1100, 1500, "世界", 0),
    ])
    subprocess.run(
        ["python", "shared/scripts/make_sentences.py", "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO
    )
    sents = json.loads((ep / "1_transcribe" / "sentences.json").read_text())
    assert len(sents["sentences"]) == 2


def test_dual_track_interleaved_words_do_not_shred(tmp_path):
    """Two speakers in separate tracks merged by timestamp must not produce
    one tiny sentence per word. Each speaker's stream is segmented
    independently and the resulting sentences are merged by start_ms.
    """
    ep = _words_json(tmp_path, [
        # S1 says "你好世界" while S2 simultaneously says "再见朋友"
        # After timestamp-sorted merge they interleave.
        _w(0, "S1",   0, 100, "你", 0),
        _w(1, "S2",  50, 150, "再", 0),
        _w(2, "S1", 100, 200, "好", 0),
        _w(3, "S2", 150, 250, "见", 0),
        _w(4, "S1", 200, 300, "世", 0),
        _w(5, "S2", 250, 350, "朋", 0),
        _w(6, "S1", 300, 400, "界", 0),
        _w(7, "S2", 350, 450, "友", 0),
    ])
    subprocess.run(
        ["python", "shared/scripts/make_sentences.py", "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO
    )
    sents = json.loads((ep / "1_transcribe" / "sentences.json").read_text())["sentences"]
    # Expected: exactly two sentences (one per speaker), not eight.
    assert len(sents) == 2, f"got {len(sents)} sentences, want 2: {sents}"
    s1 = next(s for s in sents if s["speaker"] == "S1")
    s2 = next(s for s in sents if s["speaker"] == "S2")
    assert s1["text"] == "你好世界"
    assert s2["text"] == "再见朋友"


def test_whitespace_words_split_without_polluting_text(tmp_path):
    """Volcano emits whitespace-only tokens at utterance boundaries. They
    should force a split (so two real utterances don't get glued together)
    but never appear inside a sentence's text.
    """
    ep = _words_json(tmp_path, [
        _w(0, "S1",   0, 100, "你好", 0),
        _w(1, "S1",  -1,  -1, " ",    0),   # boundary token
        _w(2, "S1", 200, 300, "世界", 0),
    ])
    subprocess.run(
        ["python", "shared/scripts/make_sentences.py", "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO
    )
    sents = json.loads((ep / "1_transcribe" / "sentences.json").read_text())["sentences"]
    assert len(sents) == 2
    assert sents[0]["text"] == "你好"
    assert sents[1]["text"] == "世界"
