# tests/scripts/test_review_server.py
import json, sys
from pathlib import Path
import pytest

REPO = "/Users/houyuxin/08Coding/podcast-cutter-skills"
sys.path.insert(0, f"{REPO}/shared/scripts")


def _setup_ep(tmp_path):
    ep = tmp_path / "ep01"
    rev = ep / "3_review"
    rev.mkdir(parents=True)
    state = {"deletes": [
        {"start_ms": 0, "end_ms": 5000, "level": "rough",
         "reason": "test", "source": "ai_rough",
         "confidence": 0.9, "user_action": "kept"}
    ]}
    (rev / "review_state.json").write_text(json.dumps(state))
    return ep


def _load_server(tmp_path):
    """Load review_server module with ep_dir configured via --no-serve."""
    ep = _setup_ep(tmp_path)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        f"review_server_{id(tmp_path)}", f"{REPO}/shared/scripts/review_server.py")
    mod = importlib.util.module_from_spec(spec)
    sys.argv = ["review_server.py", "--ep-dir", str(ep), "--no-serve"]
    spec.loader.exec_module(mod)
    mod.main()
    return mod, ep


def test_get_state(tmp_path):
    mod, ep = _load_server(tmp_path)
    client = mod.app.test_client()
    resp = client.get("/state")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "deletes" in data
    assert len(data["deletes"]) == 1


def test_patch_state(tmp_path):
    mod, ep = _load_server(tmp_path)
    client = mod.app.test_client()
    new_state = {"deletes": [
        {"start_ms": 0, "end_ms": 5000, "level": "rough",
         "reason": "test", "source": "ai_rough",
         "confidence": 0.9, "user_action": "rejected_by_user"}
    ]}
    resp = client.patch("/state", json=new_state)
    assert resp.status_code == 200
    saved = json.loads((ep / "3_review" / "review_state.json").read_text())
    assert saved["deletes"][0]["user_action"] == "rejected_by_user"


def test_export_creates_delete_segments(tmp_path):
    mod, ep = _load_server(tmp_path)
    client = mod.app.test_client()
    resp = client.post(
        "/export",
        json={"user_notes": "test notes", "feedback_for_learning": []}
    )
    assert resp.status_code == 200
    exported = json.loads((ep / "3_review" / "delete_segments_edited.json").read_text())
    assert "deletes" in exported
    assert exported["user_notes"] == "test notes"
    assert "feedback_for_learning" in exported
