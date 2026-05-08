from __future__ import annotations
import importlib.util, json, sys, unittest.mock
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load():
    spec = importlib.util.spec_from_file_location("run_pipeline", SCRIPTS / "run_pipeline.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_meta(ep_dir: Path, n_tracks: int = 1) -> None:
    in_dir = ep_dir / "input"
    in_dir.mkdir(parents=True, exist_ok=True)
    tracks = [{"file": f"working_track{i}.wav", "duration_ms": 60000, "sample_rate": 44100}
              for i in range(1, n_tracks + 1)]
    (in_dir / "audio_meta.json").write_text(json.dumps({
        "episode_id": "test", "total_duration_ms": 60000, "tracks": tracks
    }))


def test_resume_requires_delete_segments(tmp_path):
    """--resume without delete_segments_edited.json exits with code 1."""
    mod = _load()
    ep_dir = tmp_path / "ep"
    (ep_dir / "3_review").mkdir(parents=True)
    with unittest.mock.patch("sys.argv", ["run_pipeline.py", "--ep-dir", str(ep_dir), "--resume"]):
        with unittest.mock.patch("sys.exit") as mock_exit, \
             unittest.mock.patch("subprocess.run") as mock_run:
            mod.main()
    mock_exit.assert_called_once_with(1)
    mock_run.assert_not_called()


def test_resume_runs_stage4(tmp_path):
    """--resume with delete_segments_edited.json runs cut_audio.py and trim_silences.py."""
    mod = _load()
    ep_dir = tmp_path / "ep"
    review_dir = ep_dir / "3_review"
    review_dir.mkdir(parents=True)
    (review_dir / "delete_segments_edited.json").write_text('{"deletes": []}')

    with unittest.mock.patch("sys.argv", ["run_pipeline.py", "--ep-dir", str(ep_dir), "--resume"]):
        with unittest.mock.patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mod.main()

    scripts_called = [Path(c.args[0][1]).name for c in mock_run.call_args_list]
    assert "cut_audio.py" in scripts_called
    assert "trim_silences.py" in scripts_called


def test_skips_done_stages(tmp_path):
    """All outputs already exist: no subprocess.run calls, prints review message."""
    mod = _load()
    ep_dir = tmp_path / "ep"
    _make_meta(ep_dir, n_tracks=1)

    td = ep_dir / "1_transcribe"
    td.mkdir(parents=True)
    for f in ["volcano_raw_track1.json", "words.json", "sentences.json"]:
        (td / f).write_text("{}")
    ad = ep_dir / "2_analysis"
    ad.mkdir(parents=True)
    for f in ["rough_cuts.json", "fine_cuts.json", "self_review.json"]:
        (ad / f).write_text("{}")
    rd = ep_dir / "3_review"
    rd.mkdir(parents=True)
    (rd / "review_enhanced.html").write_text("<html/>")

    with unittest.mock.patch("sys.argv", ["run_pipeline.py", "--ep-dir", str(ep_dir)]):
        with unittest.mock.patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mod.main()

    mock_run.assert_not_called()


def test_new_episode_runs_prepare_audio_first(tmp_path):
    """New episode: prepare_audio.py is the first subprocess called."""
    mod = _load()
    ep_dir = tmp_path / "ep"
    track = tmp_path / "track1.wav"
    track.write_bytes(b"RIFF" + b"\x00" * 40)

    def fake_run(cmd, **kw):
        script_name = Path(cmd[1]).name if len(cmd) > 1 else ""
        if script_name == "prepare_audio.py":
            _make_meta(ep_dir, n_tracks=1)
        return unittest.mock.MagicMock(returncode=0)

    with unittest.mock.patch("sys.argv", ["run_pipeline.py",
                                           "--ep-dir", str(ep_dir),
                                           "--track1", str(track)]):
        with unittest.mock.patch("subprocess.run", side_effect=fake_run) as mock_run:
            mod.main()

    first_script = Path(mock_run.call_args_list[0].args[0][1]).name
    assert first_script == "prepare_audio.py"
