"""Unit tests for volcano_submit.py and volcano_query.py (mocked HTTP).

Volcano AUC v3 carries the API status in the `X-Api-Status-Code` HTTP header
(success = "20000000"). The body is empty on submit; on a successful query
it has the shape `{"audio_info": {...}, "result": {"text": ..., "utterances": [...]}}`.
The task_id is the UUID we send in `X-Api-Request-Id` — it is not echoed.
"""
import json, sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

REPO = "/Users/houyuxin/08Coding/podcast-cutter-skills"


def _ok_submit_resp():
    r = MagicMock()
    r.headers = {"X-Api-Status-Code": "20000000", "X-Tt-Logid": "logid-1"}
    r.raise_for_status = MagicMock()
    return r


def _ok_query_resp(body):
    r = MagicMock()
    r.headers = {"X-Api-Status-Code": "20000000", "X-Tt-Logid": "logid-2"}
    r.json.return_value = body
    r.text = json.dumps(body)
    r.raise_for_status = MagicMock()
    return r


def test_submit_writes_task_id(tmp_path):
    """submit writes the UUID we sent (X-Api-Request-Id) to task_id_track1.txt."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "volcano_submit_test", f"{REPO}/shared/scripts/volcano_submit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    captured_headers = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured_headers.update(headers or {})
        return _ok_submit_resp()

    with patch("requests.post", side_effect=fake_post), \
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
    saved = task_file.read_text().strip()
    # The saved task_id must equal the X-Api-Request-Id we sent.
    assert saved == captured_headers["X-Api-Request-Id"]


def test_submit_raises_on_nonzero_status_code(tmp_path):
    """If X-Api-Status-Code != 20000000, submit raises with logid + body."""
    bad = MagicMock()
    bad.headers = {"X-Api-Status-Code": "45000132", "X-Tt-Logid": "logid-bad"}
    bad.text = '{"error":"too big"}'
    bad.raise_for_status = MagicMock()

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "volcano_submit_err", f"{REPO}/shared/scripts/volcano_submit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    with patch("requests.post", return_value=bad), \
         patch("sys.argv", [
             "volcano_submit.py",
             "--audio-url", "https://example.com/big.wav",
             "--ep-dir", str(tmp_path),
             "--track-num", "1",
             "--env", f"{REPO}/.env",
         ]):
        with pytest.raises(RuntimeError, match="45000132"):
            mod.main()


def test_query_writes_raw_json(tmp_path):
    """Query polls; on X-Api-Status-Code == 20000000 it writes the body."""
    task_dir = tmp_path / "1_transcribe"
    task_dir.mkdir()
    (task_dir / "task_id_track1.txt").write_text("uuid-abc")

    body = {
        "audio_info": {"duration": 10000},
        "result": {
            "text": "你好",
            "utterances": [
                {"words": [{"text": "你好", "start_time": 100, "end_time": 500,
                            "confidence": 0.99, "blank_duration": 0}]}
            ]
        }
    }

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "volcano_query_test", f"{REPO}/shared/scripts/volcano_query.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    with patch("requests.post", return_value=_ok_query_resp(body)), \
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
    assert raw["result"]["utterances"][0]["words"][0]["text"] == "你好"


def test_query_raises_on_hard_fail(tmp_path):
    """Query raises with logid + body on a hard-fail status code."""
    task_dir = tmp_path / "1_transcribe"
    task_dir.mkdir()
    (task_dir / "task_id_track1.txt").write_text("uuid-bad")

    bad = MagicMock()
    bad.headers = {"X-Api-Status-Code": "45000002", "X-Tt-Logid": "logid-x"}
    bad.text = '{"error":"empty audio"}'
    bad.raise_for_status = MagicMock()

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "volcano_query_err", f"{REPO}/shared/scripts/volcano_query.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    with patch("requests.post", return_value=bad), \
         patch("sys.argv", [
             "volcano_query.py",
             "--ep-dir", str(tmp_path),
             "--track-num", "1",
             "--env", f"{REPO}/.env",
             "--interval", "0",
             "--max-attempts", "1",
         ]):
        with pytest.raises(RuntimeError, match="45000002"):
            mod.main()


def test_submit_with_audio_file(tmp_path):
    """When --audio-file given, upload runs and the returned URL goes into the payload."""
    import importlib.util, unittest.mock

    SCRIPTS = Path(__file__).resolve().parents[2] / "shared" / "scripts"
    spec = importlib.util.spec_from_file_location("volcano_submit", SCRIPTS / "volcano_submit.py")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS))
    spec.loader.exec_module(mod)

    ep_dir = tmp_path / "ep"
    audio_file = tmp_path / "track1.wav"
    audio_file.write_bytes(b"RIFF" + b"\x00" * 40)

    fake_url = "https://example.com/track1.wav"
    mock_uploader = unittest.mock.MagicMock()
    mock_uploader.upload.return_value = fake_url

    with unittest.mock.patch("sys.argv", [
        "volcano_submit.py",
        "--audio-file", str(audio_file),
        "--ep-dir", str(ep_dir),
        "--track-num", "1",
    ]):
        with unittest.mock.patch("requests.post", return_value=_ok_submit_resp()), \
             unittest.mock.patch("lib.upload.select_uploader", return_value=mock_uploader):
            mod.main()

    mock_uploader.upload.assert_called_once()
    called_path = mock_uploader.upload.call_args[0][0]
    assert Path(called_path) == audio_file

    task_id_file = ep_dir / "1_transcribe" / "task_id_track1.txt"
    assert task_id_file.exists()
    # task_id is whatever uuid.uuid4() produced — just check it's a non-empty UUID-shape string.
    saved = task_id_file.read_text().strip()
    assert len(saved) >= 32
