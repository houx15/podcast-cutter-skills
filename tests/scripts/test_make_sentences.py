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
