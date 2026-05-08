# tests/scripts/test_self_review.py
import json, sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

REPO = "/Users/houyuxin/08Coding/podcast-cutter-skills"
sys.path.insert(0, f"{REPO}/shared/scripts")


def _setup_ep(tmp_path):
    ep = tmp_path / "ep01"
    (ep / "1_transcribe").mkdir(parents=True)
    (ep / "2_analysis").mkdir(parents=True)
    sents = {"sentences": [
        {"id": 0, "speaker": "S1", "start_ms": 0, "end_ms": 5000,
         "word_idx_start": 0, "word_idx_end": 5, "text": "测试句子"}
    ]}
    (ep / "1_transcribe" / "sentences.json").write_text(json.dumps(sents))
    (ep / "2_analysis" / "rough_cuts.json").write_text(json.dumps({"deletes": []}))
    (ep / "2_analysis" / "fine_cuts.json").write_text(json.dumps({"deletes": []}))
    return ep


def _mock_llm(content: str):
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = content
    return mock_resp


def test_self_review_written(tmp_path):
    ep = _setup_ep(tmp_path)
    fake = json.dumps({
        "deletes": [],
        "flags": [],
        "summary": "No issues found."
    })
    with patch("openai.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = _mock_llm(fake)
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "self_review_test", f"{REPO}/shared/scripts/self_review.py")
        mod = importlib.util.module_from_spec(spec)
        sys.argv = ["self_review.py", "--ep-dir", str(ep), "--env", f"{REPO}/.env"]
        spec.loader.exec_module(mod)
        mod.main()

    result = json.loads((ep / "2_analysis" / "self_review.json").read_text())
    assert "deletes" in result
    assert "summary" in result
    assert result["summary"] == "No issues found."


def test_self_review_with_additional_deletes(tmp_path):
    ep = _setup_ep(tmp_path)
    fake = json.dumps({
        "deletes": [
            {"start_ms": 1000, "end_ms": 2000, "level": "fine",
             "reason": "missed filler", "source": "self_review",
             "confidence": 0.7, "evidence_word_idx": [2, 3]}
        ],
        "flags": [],
        "summary": "Found one missed cut."
    })
    with patch("openai.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = _mock_llm(fake)
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "self_review_test2", f"{REPO}/shared/scripts/self_review.py")
        mod = importlib.util.module_from_spec(spec)
        sys.argv = ["self_review.py", "--ep-dir", str(ep), "--env", f"{REPO}/.env"]
        spec.loader.exec_module(mod)
        mod.main()

    result = json.loads((ep / "2_analysis" / "self_review.json").read_text())
    assert len(result["deletes"]) == 1
    assert result["deletes"][0]["source"] == "self_review"


def test_self_review_missing_summary_raises(tmp_path):
    ep = _setup_ep(tmp_path)
    fake = json.dumps({"deletes": []})  # missing summary key
    with patch("openai.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = _mock_llm(fake)
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "self_review_test3", f"{REPO}/shared/scripts/self_review.py")
        mod = importlib.util.module_from_spec(spec)
        sys.argv = ["self_review.py", "--ep-dir", str(ep), "--env", f"{REPO}/.env"]
        spec.loader.exec_module(mod)
        with pytest.raises(ValueError, match="summary"):
            mod.main()
