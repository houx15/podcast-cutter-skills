"""Audio upload backends: TOS → S3 → uguu.se fallback chain.

The first two require credentials; uguu.se is a public temp host
and is only used as a last resort, with a privacy warning to stderr.
TOS is exposed via Volcano's S3-compatible interface; we use boto3
for both TOS and generic S3, so the implementations share most code.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any, Protocol

import requests

from .config import Config, S3Config, TOSConfig

UGUU_ENDPOINT = "https://uguu.se/upload"
PRESIGN_EXPIRES_SECONDS = 3600


class UploadError(Exception):
    pass


class Uploader(Protocol):
    def upload(self, path: Path) -> str: ...


def _boto3_client(service: str, **kwargs: Any) -> Any:
    """Wrapped so tests can monkeypatch without importing boto3 in test scope."""
    import boto3  # noqa: WPS433  (lazy import keeps test import-fast)

    return boto3.client(service, **kwargs)


class _S3LikeUploader:
    """Shared logic for TOS and generic S3 uploaders."""

    def __init__(
        self,
        *,
        endpoint: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str = "auto",
        addressing_style: str | None = None,
    ) -> None:
        if not endpoint.startswith(("http://", "https://")):
            endpoint = f"https://{endpoint}"
        from botocore.config import Config as _BotoConfig

        boto_cfg_kwargs: dict[str, object] = {"signature_version": "s3v4"}
        if addressing_style:
            boto_cfg_kwargs["s3"] = {"addressing_style": addressing_style}

        self._client = _boto3_client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=_BotoConfig(**boto_cfg_kwargs),
        )
        self._bucket = bucket

    def upload(self, path: Path) -> str:
        path = Path(path)
        key = f"podcast-cutter/{uuid.uuid4().hex}/{path.name}"
        try:
            self._client.upload_file(
                Filename=str(path),
                Bucket=self._bucket,
                Key=key,
                ExtraArgs={"ContentType": "audio/mpeg"},
            )
        except Exception as exc:  # noqa: BLE001
            raise UploadError(f"S3-compatible upload failed: {exc}") from exc
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=PRESIGN_EXPIRES_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001
            raise UploadError(f"presign failed: {exc}") from exc


def _normalize_tos_endpoint(endpoint: str) -> str:
    """Volcano TOS exposes two endpoints per region:
       - tos-{region}.volces.com         (native TOS protocol)
       - tos-s3-{region}.volces.com      (S3-compatible protocol — what boto3 needs)
    Users naturally paste the bucket-domain endpoint (no `s3-`); we promote it.
    """
    e = endpoint.replace("https://", "").replace("http://", "")
    if e.startswith("tos-") and not e.startswith("tos-s3-") and ".volces.com" in e:
        return f"https://tos-s3-{e[len('tos-'):]}"
    return endpoint


def _region_from_tos_endpoint(endpoint: str) -> str:
    e = endpoint.replace("https://", "").replace("http://", "")
    if e.startswith("tos-s3-") and ".volces.com" in e:
        return e[len("tos-s3-"):].split(".", 1)[0]
    if e.startswith("tos-") and ".volces.com" in e:
        return e[len("tos-"):].split(".", 1)[0]
    return "auto"


class TOSUploader(_S3LikeUploader):
    def __init__(self, cfg: TOSConfig) -> None:
        endpoint = _normalize_tos_endpoint(cfg.endpoint)
        super().__init__(
            endpoint=endpoint,
            bucket=cfg.bucket,
            access_key=cfg.access_key,
            secret_key=cfg.secret_key,
            region=_region_from_tos_endpoint(endpoint),
            addressing_style="virtual",
        )


class S3Uploader(_S3LikeUploader):
    def __init__(self, cfg: S3Config) -> None:
        super().__init__(
            endpoint=cfg.endpoint,
            bucket=cfg.bucket,
            access_key=cfg.access_key,
            secret_key=cfg.secret_key,
            region=cfg.region,
        )


class UguuUploader:
    def upload(self, path: Path) -> str:
        path = Path(path)
        with path.open("rb") as fh:
            resp = requests.post(
                UGUU_ENDPOINT,
                files={"files[]": (path.name, fh)},
                timeout=120,
            )
        try:
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise UploadError(f"uguu HTTP error: {exc}") from exc
        if not payload.get("success"):
            raise UploadError(
                f"uguu rejected upload: {payload.get('description', payload)}"
            )
        files = payload.get("files") or []
        if not files or "url" not in files[0]:
            raise UploadError(f"uguu returned no url: {payload}")
        return files[0]["url"]


def select_uploader(cfg: Config) -> Uploader:
    if cfg.upload_backend == "tos":
        assert cfg.tos is not None
        return TOSUploader(cfg.tos)
    if cfg.upload_backend == "s3":
        assert cfg.s3 is not None
        return S3Uploader(cfg.s3)
    print(
        "[upload] WARNING: 未配置 TOS 或 S3，回退到 uguu.se 公共托管。"
        "音频会被上传到公网临时主机，私密内容请先在 .env 配置 TOS_* 或 S3_*。",
        file=sys.stderr,
    )
    return UguuUploader()
