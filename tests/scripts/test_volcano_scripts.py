"""Unit tests for volcano_submit.py and volcano_query.py (mocked HTTP)."""
import json, sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

REPO = "/Users/houyuxin/08Coding/podcast-cutter-skills"


def test_submit_writes_task_id(tmp_path):
    """submit should write task_id_track1.txt in 1_transcribe/."""
    fake_resp = MagicMock()
    fake_resp.json.return_value = {"resp": {"task_id": "fake-task-123"}}
    fake_resp.raise_for_status = MagicMock()

    import importlib.util, sys as _sys
    spec = importlib.util.spec_from_file_location(
        "volcano_submit_test", f"{REPO}/shared/scripts/volcano_submit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    with patch("requests.post", return_value=fake_resp), \
         patch("sys.argv", [
             "volcano_submit.py",
             "--audio-url", "https://example.com/audio.wav",
             "--audio-format", "wav",
             "--ep-dir", str(tmp_path),
             "--track-num", "1",
             "--env", f"{REPO}/.env",
         ]):
        mod.main()

    task_file = tmp_path / "1_transcribe" / "task_id_track1.txt"
    assert task_file.exists()
    assert task_file.read_text().strip() == "fake-task-123"


def test_query_writes_raw_json(tmp_path):
    """query should poll and write volcano_raw_track1.json on success."""
    task_dir = tmp_path / "1_transcribe"
    task_dir.mkdir()
    (task_dir / "task_id_track1.txt").write_text("fake-task-123")

    # Simulate Volcano returning SUCCESS code "20000000"
    fake_resp = MagicMock()
    fake_resp.json.return_value = {
        "resp": {
            "code": "20000000",
            "task_id": "fake-task-123",
            "utterances": [
                {"words": [{"text": "你好", "start_time": 100, "end_time": 500,
                            "confidence": 0.99, "blank_duration": 0}]}
            ]
        }
    }
    fake_resp.raise_for_status = MagicMock()

    import importlib.util, sys as _sys
    spec = importlib.util.spec_from_file_location(
        "volcano_query_test", f"{REPO}/shared/scripts/volcano_query.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    with patch("requests.post", return_value=fake_resp), \
         patch("sys.argv", [
             "volcano_query.py",
             "--ep-dir", str(tmp_path),
             "--track-num", "1",
             "--env", f"{REPO}/.env",
             "--interval", "0",
             "--max-attempts", "3",
         ]):
        mod.main()

    raw = json.loads((task_dir / "volcano_raw_track1.json").read_text())
    assert "resp" in raw
    assert raw["resp"]["task_id"] == "fake-task-123"


def test_submit_with_audio_file(tmp_path):
    import importlib.util, sys, json, unittest.mock
    from pathlib import Path

    SCRIPTS = Path(__file__).resolve().parents[2] / "shared" / "scripts"
    spec = importlib.util.spec_from_file_location("volcano_submit", SCRIPTS / "volcano_submit.py")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS))
    spec.loader.exec_module(mod)

    ep_dir = tmp_path / "ep"
    audio_file = tmp_path / "track1.wav"
    audio_file.write_bytes(b"RIFF" + b"\x00" * 40)

    fake_url = "https://example.com/track1.wav"
    fake_task_id = "task-abc-123"
    fake_resp_data = {"resp": {"task_id": fake_task_id}}

    mock_uploader = unittest.mock.MagicMock()
    mock_uploader.upload.return_value = fake_url

    with unittest.mock.patch("sys.argv", [
        "volcano_submit.py",
        "--audio-file", str(audio_file),
        "--ep-dir", str(ep_dir),
        "--track-num", "1",
    ]):
        with unittest.mock.patch("requests.post") as mock_post, \
             unittest.mock.patch("lib.upload.select_uploader", return_value=mock_uploader):
            mock_post.return_value.status_code = 200
            mock_post.return_value.raise_for_status = lambda: None
            mock_post.return_value.json.return_value = fake_resp_data
            mod.main()

    mock_uploader.upload.assert_called_once()
    called_path = mock_uploader.upload.call_args[0][0]
    assert Path(called_path) == audio_file

    task_id_file = ep_dir / "1_transcribe" / "task_id_track1.txt"
    assert task_id_file.exists()
    assert task_id_file.read_text().strip() == fake_task_id
