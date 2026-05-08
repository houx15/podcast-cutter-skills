# tests/scripts/test_analyze_rough.py
import json, sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

REPO = "/Users/houyuxin/08Coding/podcast-cutter-skills"
sys.path.insert(0, f"{REPO}/shared/scripts")


def _setup_ep(tmp_path):
    ep = tmp_path / "ep01"
    td = ep / "1_transcribe"
    td.mkdir(parents=True)
    (ep / "2_analysis").mkdir(parents=True)
    sents = {"sentences": [
        {"id": 0, "speaker": "S1", "start_ms": 0, "end_ms": 5000,
         "word_idx_start": 0, "word_idx_end": 10, "text": "这是录前闲聊内容"},
        {"id": 1, "speaker": "S1", "start_ms": 6000, "end_ms": 60000,
         "word_idx_start": 11, "word_idx_end": 200, "text": "正式内容开始了"},
    ]}
    (td / "sentences.json").write_text(json.dumps(sents))
    return ep


def _mock_llm_response(content: str):
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = content
    return mock_resp


def test_rough_cuts_written(tmp_path):
    ep = _setup_ep(tmp_path)
    fake_content = json.dumps({"deletes": [
        {"start_ms": 0, "end_ms": 5000, "level": "rough",
         "reason": "录前闲聊", "source": "ai_rough",
         "confidence": 0.9, "evidence_word_idx": [0, 10]}
    ]})
    with patch("openai.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = _mock_llm_response(fake_content)
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "analyze_rough", f"{REPO}/shared/scripts/analyze_rough.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.argv = ["analyze_rough.py", "--ep-dir", str(ep), "--env", f"{REPO}/.env"]
        mod.main()

    cuts = json.loads((ep / "2_analysis" / "rough_cuts.json").read_text())
    assert len(cuts["deletes"]) == 1
    assert cuts["deletes"][0]["level"] == "rough"
    assert cuts["deletes"][0]["source"] == "ai_rough"


def test_rough_cuts_schema_validated(tmp_path):
    """LLM response missing required fields should raise ValueError."""
    ep = _setup_ep(tmp_path)
    fake_content = json.dumps({"deletes": [
        {"start_ms": 0, "end_ms": 5000}  # missing level/reason/source/confidence
    ]})
    with patch("openai.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = _mock_llm_response(fake_content)
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "analyze_rough2", f"{REPO}/shared/scripts/analyze_rough.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.argv = ["analyze_rough.py", "--ep-dir", str(ep), "--env", f"{REPO}/.env"]
        with pytest.raises(ValueError, match="missing fields"):
            mod.main()


def test_strips_code_fences(tmp_path):
    """LLM wrapping response in markdown code fences should still work."""
    ep = _setup_ep(tmp_path)
    inner = json.dumps({"deletes": [
        {"start_ms": 0, "end_ms": 5000, "level": "rough",
         "reason": "test", "source": "ai_rough", "confidence": 0.8,
         "evidence_word_idx": [0, 5]}
    ]})
    fenced = f"```json\n{inner}\n```"
    with patch("openai.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = _mock_llm_response(fenced)
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "analyze_rough3", f"{REPO}/shared/scripts/analyze_rough.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.argv = ["analyze_rough.py", "--ep-dir", str(ep), "--env", f"{REPO}/.env"]
        mod.main()

    cuts = json.loads((ep / "2_analysis" / "rough_cuts.json").read_text())
    assert len(cuts["deletes"]) == 1
