"""Tests for cut_review.py — Stage 4.4 fine review.

Critical invariant: accepted proposals are written to 4_cut/fine_deletes.json
in cut.wav timeline. NO cut→orig translation. cut_audio_fine.py applies these
directly to coarse_cut.wav.
"""
import importlib.util, json, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load():
    spec = importlib.util.spec_from_file_location("cut_review", SCRIPTS / "cut_review.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _setup(tmp_path, proposals):
    ep = tmp_path / "ep"
    (ep / "4_cut").mkdir(parents=True)
    # Marker file so _audio_path() resolves cleanly (server checks existence)
    (ep / "4_cut" / "coarse_cut.wav").write_bytes(b"")
    (ep / "4_cut" / "fine_proposals.json").write_text(
        json.dumps({"proposals": proposals})
    )
    (ep / "4_cut" / "cut_sentences.json").write_text(
        json.dumps({"sentences": []})
    )
    return ep


def test_accept_proposal_writes_cut_timeline_delete(tmp_path):
    ep = _setup(tmp_path, [
        {"id": "fine-0001", "cut_start_ms": 5000, "cut_end_ms": 6000,
         "category": "stutter", "reason": "test", "status": "pending"},
    ])
    mod = _load()
    mod._ep_dir = ep
    mod._save_proposal_status("fine-0001", "accepted", "")
    mod._rebuild_fine_deletes()

    fine = json.loads((ep / "4_cut" / "fine_deletes.json").read_text())
    assert len(fine["deletes"]) == 1
    d = fine["deletes"][0]
    assert d["cut_start_ms"] == 5000, "must preserve cut timeline (no translation)"
    assert d["cut_end_ms"] == 6000
    assert "start_ms" not in d, "cut timeline only — no orig translation"


def test_reject_proposal_excludes_from_fine_deletes(tmp_path):
    ep = _setup(tmp_path, [
        {"id": "fine-0001", "cut_start_ms": 5000, "cut_end_ms": 6000,
         "category": "stutter", "reason": "test", "status": "pending"},
        {"id": "fine-0002", "cut_start_ms": 8000, "cut_end_ms": 9000,
         "category": "stutter", "reason": "test", "status": "pending"},
    ])
    mod = _load()
    mod._ep_dir = ep
    mod._save_proposal_status("fine-0001", "accepted", "")
    mod._save_proposal_status("fine-0002", "rejected", "")
    mod._rebuild_fine_deletes()

    fine = json.loads((ep / "4_cut" / "fine_deletes.json").read_text())
    assert len(fine["deletes"]) == 1
    assert fine["deletes"][0]["cut_start_ms"] == 5000


def test_supports_general_start_end_schema(tmp_path):
    """Proposals can carry start_ms/end_ms (from propose_char_level.py output)
    OR cut_start_ms/cut_end_ms (legacy). Both end up as cut_start_ms in fine_deletes.json."""
    ep = _setup(tmp_path, [
        {"id": "fine-0001", "start_ms": 7000, "end_ms": 7500,
         "category": "marker", "reason": "test", "status": "pending"},
    ])
    mod = _load()
    mod._ep_dir = ep
    mod._save_proposal_status("fine-0001", "accepted", "")
    mod._rebuild_fine_deletes()

    fine = json.loads((ep / "4_cut" / "fine_deletes.json").read_text())
    assert fine["deletes"][0]["cut_start_ms"] == 7000
    assert fine["deletes"][0]["cut_end_ms"] == 7500


def test_status_persisted_to_proposal_file(tmp_path):
    ep = _setup(tmp_path, [
        {"id": "fine-0001", "cut_start_ms": 5000, "cut_end_ms": 6000,
         "category": "stutter", "reason": "test", "status": "pending"},
    ])
    mod = _load()
    mod._ep_dir = ep
    mod._save_proposal_status("fine-0001", "accepted", "tighter please")

    data = json.loads((ep / "4_cut" / "fine_proposals.json").read_text())
    assert data["proposals"][0]["status"] == "accepted"
    assert data["proposals"][0]["user_comment"] == "tighter please"


def test_reject_then_accept_overrides(tmp_path):
    """Re-accepting a rejected proposal updates state correctly."""
    ep = _setup(tmp_path, [
        {"id": "fine-0001", "cut_start_ms": 5000, "cut_end_ms": 6000,
         "category": "stutter", "reason": "test", "status": "pending"},
    ])
    mod = _load()
    mod._ep_dir = ep
    mod._save_proposal_status("fine-0001", "rejected", "")
    mod._rebuild_fine_deletes()
    fine1 = json.loads((ep / "4_cut" / "fine_deletes.json").read_text())
    assert len(fine1["deletes"]) == 0

    mod._save_proposal_status("fine-0001", "accepted", "")
    mod._rebuild_fine_deletes()
    fine2 = json.loads((ep / "4_cut" / "fine_deletes.json").read_text())
    assert len(fine2["deletes"]) == 1
