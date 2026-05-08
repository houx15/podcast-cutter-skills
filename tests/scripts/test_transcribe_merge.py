# tests/scripts/test_transcribe_merge.py
import json, subprocess
from pathlib import Path
import pytest

REPO = "/Users/houyuxin/08Coding/podcast-cutter-skills"


def _raw(task_id="t1", words=None):
    """Volcano AUC v3 query body: utterances live under `result`, not `resp`."""
    words = words or [{"text": "你", "start_time": 100, "end_time": 300,
                        "confidence": 0.9, "blank_duration": 50}]
    return {
        "audio_info": {"duration": 1000},
        "result": {"text": "test", "utterances": [{"words": words}]},
    }


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


def test_track_offsets_applied(tmp_path):
    """track_offsets_ms in audio_meta.json shifts word timestamps before merge."""
    ep_dir = tmp_path / "ep"
    td = ep_dir / "1_transcribe"
    in_dir = ep_dir / "input"
    td.mkdir(parents=True)
    in_dir.mkdir(parents=True)

    raw1 = {"result": {"utterances": [{"words": [
        {"text": "嗯", "start_time": 0, "end_time": 300, "confidence": 0.9, "blank_duration": 50},
    ]}]}}
    raw2 = {"result": {"utterances": [{"words": [
        {"text": "对", "start_time": 0, "end_time": 300, "confidence": 0.9, "blank_duration": 50},
    ]}]}}
    (td / "volcano_raw_track1.json").write_text(json.dumps(raw1))
    (td / "volcano_raw_track2.json").write_text(json.dumps(raw2))

    meta = {
        "episode_id": "test", "total_duration_ms": 5000,
        "tracks": [
            {"file": "working_track1.wav", "duration_ms": 5000, "sample_rate": 44100},
            {"file": "working_track2.wav", "duration_ms": 5000, "sample_rate": 44100},
        ],
        "track_offsets_ms": [0, 500],
    }
    (in_dir / "audio_meta.json").write_text(json.dumps(meta))

    subprocess.run(
        ["python", "shared/scripts/transcribe_merge.py", "--ep-dir", str(ep_dir)],
        check=True, capture_output=True, cwd=REPO
    )

    words_json = json.loads((td / "words.json").read_text())
    words = words_json["words"]
    s1 = next(w for w in words if w["speaker"] == "S1")
    s2 = next(w for w in words if w["speaker"] == "S2")
    assert s1["start_ms"] == 0
    assert s2["start_ms"] == 500
    assert words[0]["speaker"] == "S1"
    assert words[1]["speaker"] == "S2"
