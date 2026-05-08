"""Tests for cut_transcript.py — re-time sentences against cut.wav."""
import importlib.util, json, sys, unittest.mock
from pathlib import Path
import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load():
    spec = importlib.util.spec_from_file_location(
        "cut_transcript", SCRIPTS / "cut_transcript.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _setup(tmp_path, sentences, deletes):
    ep = tmp_path / "ep"
    (ep / "1_transcribe").mkdir(parents=True)
    (ep / "3_review").mkdir(parents=True)
    (ep / "1_transcribe" / "sentences.json").write_text(
        json.dumps({"sentences": sentences})
    )
    (ep / "3_review" / "delete_segments_edited.json").write_text(
        json.dumps({"deletes": deletes})
    )
    return ep


def _run(ep):
    mod = _load()
    with unittest.mock.patch("sys.argv", [
        "cut_transcript.py", "--ep-dir", str(ep),
    ]):
        mod.main()
    return json.loads((ep / "5_shownotes" / "cut_transcript.json").read_text())


def test_no_deletes_passes_through(tmp_path):
    """No deletes → every sentence kept, timestamps unchanged."""
    sents = [
        {"id": 0, "speaker": "S1", "start_ms": 0, "end_ms": 1000, "text": "你好"},
        {"id": 1, "speaker": "S1", "start_ms": 1500, "end_ms": 3000, "text": "世界"},
    ]
    out = _run(_setup(tmp_path, sents, []))
    assert out["total_deleted_ms"] == 0
    assert out["sentence_count_cut"] == 2
    assert out["sentences"][0]["start_ms"] == 0
    assert out["sentences"][1]["start_ms"] == 1500


def test_drops_sentence_inside_delete(tmp_path):
    """Sentence whose midpoint falls inside a delete is dropped."""
    sents = [
        {"id": 0, "speaker": "S1", "start_ms": 0, "end_ms": 1000, "text": "保留"},
        {"id": 1, "speaker": "S1", "start_ms": 2000, "end_ms": 4000, "text": "删掉"},
        {"id": 2, "speaker": "S1", "start_ms": 5000, "end_ms": 6000, "text": "保留二"},
    ]
    deletes = [{"start_ms": 1500, "end_ms": 4500}]
    out = _run(_setup(tmp_path, sents, deletes))
    assert out["sentence_count_cut"] == 2
    texts = [s["text"] for s in out["sentences"]]
    assert texts == ["保留", "保留二"]


def test_retimes_remaining_sentences(tmp_path):
    """Remaining sentences are shifted left by the cumulative deleted duration."""
    sents = [
        {"id": 0, "speaker": "S1", "start_ms": 0, "end_ms": 1000, "text": "A"},
        {"id": 1, "speaker": "S1", "start_ms": 5000, "end_ms": 6000, "text": "B"},
    ]
    # Delete 1000–4000ms (3 seconds)
    deletes = [{"start_ms": 1000, "end_ms": 4000}]
    out = _run(_setup(tmp_path, sents, deletes))
    a, b = out["sentences"]
    assert a["start_ms"] == 0  # before the delete, unchanged
    assert b["start_ms"] == 2000  # 5000 - 3000 deleted
    assert b["end_ms"] == 3000
    # Original timestamps preserved for traceability
    assert b["orig_start_ms"] == 5000


def test_merges_overlapping_deletes(tmp_path):
    """Overlapping delete spans are merged before shift calculation."""
    sents = [{"id": 0, "speaker": "S1", "start_ms": 5000, "end_ms": 6000, "text": "X"}]
    deletes = [
        {"start_ms": 0, "end_ms": 2000},
        {"start_ms": 1500, "end_ms": 3000},  # overlaps the first
    ]
    out = _run(_setup(tmp_path, sents, deletes))
    # Merged delete is 0–3000ms (3 seconds total deleted, not 3500)
    assert out["total_deleted_ms"] == 3000
    assert out["sentences"][0]["start_ms"] == 2000  # 5000 - 3000


def test_rejected_action_is_not_applied(tmp_path):
    """A delete entry marked user_action='rejected' is treated as kept."""
    sents = [{"id": 0, "speaker": "S1", "start_ms": 5000, "end_ms": 6000, "text": "X"}]
    deletes = [
        {"start_ms": 1000, "end_ms": 2000, "user_action": "rejected"},
    ]
    out = _run(_setup(tmp_path, sents, deletes))
    assert out["total_deleted_ms"] == 0
    assert out["sentences"][0]["start_ms"] == 5000  # unchanged


def test_missing_files_raise(tmp_path):
    """Missing inputs raise FileNotFoundError with a clear message."""
    ep = tmp_path / "ep"
    (ep / "1_transcribe").mkdir(parents=True)
    (ep / "3_review").mkdir(parents=True)
    mod = _load()
    with unittest.mock.patch("sys.argv", [
        "cut_transcript.py", "--ep-dir", str(ep),
    ]):
        with pytest.raises(FileNotFoundError, match="sentences.json"):
            mod.main()
