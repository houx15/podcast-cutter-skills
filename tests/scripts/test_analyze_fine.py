# tests/scripts/test_analyze_fine.py
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
    ad = ep / "2_analysis"
    ad.mkdir(parents=True)
    sents = {"sentences": [
        {"id": 0, "speaker": "S1", "start_ms": 0, "end_ms": 5000,
         "word_idx_start": 0, "word_idx_end": 4, "text": "嗯嗯嗯对对对"}
    ]}
    (td / "sentences.json").write_text(json.dumps(sents))
    words_data = {"words": [
        {"idx": i, "speaker": "S1", "start_ms": i * 500, "end_ms": i * 500 + 400,
         "text": c, "confidence": 0.9, "blank_after_ms": 0,
         "emotion": None, "lid": None}
        for i, c in enumerate(["嗯", "嗯", "嗯", "对", "对"])
    ]}
    (td / "words.json").write_text(json.dumps(words_data))
    rough = {"deletes": []}
    (ad / "rough_cuts.json").write_text(json.dumps(rough))
    return ep


def _mock_llm(content: str):
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = content
    return mock_resp


def test_fine_cuts_written(tmp_path):
    ep = _setup_ep(tmp_path)
    fake = json.dumps({"deletes": [
        {"start_ms": 0, "end_ms": 1500, "level": "fine",
         "reason": "重复语气词", "source": "ai_fine",
         "confidence": 0.85, "evidence_word_idx": [0, 2]}
    ]})
    with patch("openai.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = _mock_llm(fake)
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "analyze_fine_test", f"{REPO}/shared/scripts/analyze_fine.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.argv = ["analyze_fine.py", "--ep-dir", str(ep), "--env", f"{REPO}/.env"]
        mod.main()

    cuts = json.loads((ep / "2_analysis" / "fine_cuts.json").read_text())
    assert len(cuts["deletes"]) == 1
    assert cuts["deletes"][0]["level"] == "fine"
    assert cuts["deletes"][0]["source"] == "ai_fine"


def test_fine_cuts_schema_validated(tmp_path):
    ep = _setup_ep(tmp_path)
    fake = json.dumps({"deletes": [{"start_ms": 0, "end_ms": 1500}]})  # missing fields
    with patch("openai.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = _mock_llm(fake)
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "analyze_fine_test2", f"{REPO}/shared/scripts/analyze_fine.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.argv = ["analyze_fine.py", "--ep-dir", str(ep), "--env", f"{REPO}/.env"]
        with pytest.raises(ValueError, match="missing fields"):
            mod.main()


def test_fine_cuts_respects_rough_cuts(tmp_path):
    """Fine pass should see rough_cuts.json context in system prompt."""
    ep = _setup_ep(tmp_path)
    # Add a rough cut that should be visible to the system prompt
    rough_cuts = {"deletes": [
        {"start_ms": 5000, "end_ms": 10000, "level": "rough",
         "reason": "test rough cut", "source": "ai_rough",
         "confidence": 0.9, "evidence_word_idx": [10, 15]}
    ]}
    (ep / "2_analysis" / "rough_cuts.json").write_text(json.dumps(rough_cuts))

    fake = json.dumps({"deletes": [
        {"start_ms": 0, "end_ms": 500, "level": "fine",
         "reason": "语气词", "source": "ai_fine",
         "confidence": 0.8, "evidence_word_idx": [0, 0]}
    ]})
    with patch("openai.OpenAI") as MockClient:
        mock_create = MagicMock(return_value=_mock_llm(fake))
        MockClient.return_value.chat.completions.create = mock_create
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "analyze_fine_test3", f"{REPO}/shared/scripts/analyze_fine.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.argv = ["analyze_fine.py", "--ep-dir", str(ep), "--env", f"{REPO}/.env"]
        mod.main()

    # Verify system prompt includes rough_cuts
    call_args = mock_create.call_args
    system_msg = call_args[1]["messages"][0]["content"]
    assert "已标记的粗剪" in system_msg

    cuts = json.loads((ep / "2_analysis" / "fine_cuts.json").read_text())
    assert len(cuts["deletes"]) == 1
    assert cuts["deletes"][0]["level"] == "fine"


def test_fine_cuts_with_code_fences(tmp_path):
    """LLM wrapping response in markdown code fences should still work."""
    ep = _setup_ep(tmp_path)
    inner = json.dumps({"deletes": [
        {"start_ms": 0, "end_ms": 500, "level": "fine",
         "reason": "test", "source": "ai_fine", "confidence": 0.8,
         "evidence_word_idx": [0, 0]}
    ]})
    fenced = f"```json\n{inner}\n```"
    with patch("openai.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = _mock_llm(fenced)
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "analyze_fine_test4", f"{REPO}/shared/scripts/analyze_fine.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.argv = ["analyze_fine.py", "--ep-dir", str(ep), "--env", f"{REPO}/.env"]
        mod.main()

    cuts = json.loads((ep / "2_analysis" / "fine_cuts.json").read_text())
    assert len(cuts["deletes"]) == 1
