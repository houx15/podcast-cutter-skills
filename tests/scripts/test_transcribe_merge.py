# tests/scripts/test_transcribe_merge.py
import json, subprocess
from pathlib import Path
import pytest

REPO = "/Users/houyuxin/08Coding/podcast-cutter-skills"


def _raw(task_id="t1", words=None):
    words = words or [{"text": "你", "start_time": 100, "end_time": 300,
                        "confidence": 0.9, "blank_duration": 50}]
    return {"resp": {"code": "20000000", "task_id": task_id,
                     "utterances": [{"words": words}]}}


def test_single_track_words_json(tmp_path):
    ep = tmp_path / "ep01"
    td = ep / "1_transcribe"
    td.mkdir(parents=True)
    (td / "volcano_raw_track1.json").write_text(json.dumps(_raw()))

    subprocess.run(
        ["python", "shared/scripts/transcribe_merge.py", "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO
    )

    words = json.loads((td / "words.json").read_text())
    assert words["source"]["mode"] == "single_track"
    assert len(words["words"]) == 1
    assert words["words"][0]["speaker"] == "S1"
    assert words["words"][0]["start_ms"] == 100
    assert words["words"][0]["text"] == "你"


def test_two_track_merge_sorted(tmp_path):
    ep = tmp_path / "ep01"
    td = ep / "1_transcribe"
    td.mkdir(parents=True)
    raw1 = _raw("t1", [{"text": "A", "start_time": 200, "end_time": 400,
                         "confidence": 0.9, "blank_duration": 0}])
    raw2 = _raw("t2", [{"text": "B", "start_time": 100, "end_time": 300,
                         "confidence": 0.8, "blank_duration": 0}])
    (td / "volcano_raw_track1.json").write_text(json.dumps(raw1))
    (td / "volcano_raw_track2.json").write_text(json.dumps(raw2))

    subprocess.run(
        ["python", "shared/scripts/transcribe_merge.py", "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO
    )

    words = json.loads((td / "words.json").read_text())
    assert words["source"]["mode"] == "two_track"
    assert words["words"][0]["text"] == "B"    # start_ms=100 comes first
    assert words["words"][0]["speaker"] == "S2"
    assert words["words"][1]["speaker"] == "S1"
    assert words["words"][0]["idx"] == 0
    assert words["words"][1]["idx"] == 1


def test_duration_from_audio_meta(tmp_path):
    ep = tmp_path / "ep01"
    td = ep / "1_transcribe"
    td.mkdir(parents=True)
    in_dir = ep / "input"
    in_dir.mkdir()
    (td / "volcano_raw_track1.json").write_text(json.dumps(_raw()))
    meta = {"episode_id": "ep01", "mode": "single_track",
            "tracks": [{"file": "working_track1.wav", "duration_ms": 60000, "sample_rate": 44100}],
            "total_duration_ms": 60000}
    (in_dir / "audio_meta.json").write_text(json.dumps(meta))

    subprocess.run(
        ["python", "shared/scripts/transcribe_merge.py", "--ep-dir", str(ep)],
        check=True, capture_output=True, cwd=REPO
    )

    words = json.loads((td / "words.json").read_text())
    assert words["duration_ms"] == 60000
