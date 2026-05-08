"""Tests for shared.scripts.lib.upload."""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest

from shared.scripts.lib import config, upload


def _empty_cfg(backend: str = "uguu") -> config.Config:
    volcano = config.VolcanoConfig(
        console="new",
        api_key="newkey",
        app_key=None,
        access_key=None,
        resource_id="volc.seedasr.auc",
    )
    tos = (
        config.TOSConfig(
            access_key="ak",
            secret_key="sk",
            bucket="b",
            endpoint="https://tos.example",
        )
        if backend == "tos"
        else None
    )
    s3 = (
        config.S3Config(
            endpoint="https://r2.example",
            bucket="b",
            access_key="ak",
            secret_key="sk",
            region="auto",
        )
        if backend == "s3"
        else None
    )
    return config.Config(
        volcano=volcano,
        tos=tos,
        s3=s3,
        gemini_api_key=None,
        upload_backend=backend,  # type: ignore[arg-type]
    )


def test_uguu_uploader_posts_file_and_returns_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = tmp_path / "in.wav"
    audio.write_bytes(b"fake-audio")

    captured: dict[str, Any] = {}

    class FakeResponse:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return {
                "success": True,
                "files": [{"url": "https://uguu.example/abc.wav"}],
            }

        def raise_for_status(self) -> None:
            return None

    def fake_post(url: str, files: dict[str, Any], timeout: int) -> FakeResponse:
        captured["url"] = url
        captured["files"] = files
        return FakeResponse()

    monkeypatch.setattr(upload.requests, "post", fake_post)
    uploader = upload.UguuUploader()
    url = uploader.upload(audio)
    assert url == "https://uguu.example/abc.wav"
    assert "uguu" in captured["url"]


def test_uguu_uploader_raises_on_upstream_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = tmp_path / "in.wav"
    audio.write_bytes(b"fake")

    class BadResponse:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return {"success": False, "description": "rate limited"}

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(upload.requests, "post", lambda *a, **k: BadResponse())
    with pytest.raises(upload.UploadError) as exc:
        upload.UguuUploader().upload(audio)
    assert "rate limited" in str(exc.value)


def test_s3_uploader_calls_put_object_with_presigned_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = tmp_path / "in.wav"
    audio.write_bytes(b"abc")

    captured: dict[str, Any] = {}

    class FakeS3Client:
        def upload_file(
            self, Filename: str, Bucket: str, Key: str, ExtraArgs: dict[str, Any]
        ) -> None:
            captured["filename"] = Filename
            captured["bucket"] = Bucket
            captured["key"] = Key
            captured["extra"] = ExtraArgs

        def generate_presigned_url(
            self, op: str, Params: dict[str, Any], ExpiresIn: int
        ) -> str:
            captured["presign"] = (op, Params, ExpiresIn)
            return f"https://r2.example/{Params['Bucket']}/{Params['Key']}?sig=fake"

    def fake_boto_client(*args: Any, **kwargs: Any) -> FakeS3Client:
        captured["client_args"] = (args, kwargs)
        return FakeS3Client()

    monkeypatch.setattr(upload, "_boto3_client", fake_boto_client)

    cfg = _empty_cfg("s3").s3
    assert cfg is not None
    uploader = upload.S3Uploader(cfg)
    url = uploader.upload(audio)
    assert url.startswith("https://r2.example/b/")
    assert captured["bucket"] == "b"
    assert captured["filename"] == str(audio)
    assert captured["presign"][2] == upload.PRESIGN_EXPIRES_SECONDS


def test_select_uploader_returns_tos_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _empty_cfg("tos")
    monkeypatch.setattr(upload, "_boto3_client", lambda *a, **k: object())
    uploader = upload.select_uploader(cfg)
    assert isinstance(uploader, upload.TOSUploader)


def test_select_uploader_returns_s3(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _empty_cfg("s3")
    monkeypatch.setattr(upload, "_boto3_client", lambda *a, **k: object())
    uploader = upload.select_uploader(cfg)
    assert isinstance(uploader, upload.S3Uploader)


def test_select_uploader_falls_back_to_uguu_with_warning(
    capsys: pytest.CaptureFixture[str],
) -> None:
    cfg = _empty_cfg("uguu")
    uploader = upload.select_uploader(cfg)
    assert isinstance(uploader, upload.UguuUploader)
    captured = capsys.readouterr()
    assert "uguu.se" in captured.err
    assert "私密" in captured.err or "privacy" in captured.err.lower()
