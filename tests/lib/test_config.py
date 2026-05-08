"""Tests for shared.scripts.lib.config."""
from __future__ import annotations

from pathlib import Path

import pytest

from shared.scripts.lib import config


def test_load_picks_new_console_api_key(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "VOLC_API_KEY=newkey\n"
        "VOLC_RESOURCE_ID=volc.seedasr.auc\n"
    )
    cfg = config.load(env_path=env)
    assert cfg.volcano.api_key == "newkey"
    assert cfg.volcano.console == "new"
    assert cfg.volcano.app_key is None
    assert cfg.volcano.access_key is None


def test_load_picks_old_console_when_only_pair_present(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "VOLC_APP_KEY=appid\n"
        "VOLC_ACCESS_KEY=token\n"
        "VOLC_RESOURCE_ID=volc.seedasr.auc\n"
    )
    cfg = config.load(env_path=env)
    assert cfg.volcano.console == "old"
    assert cfg.volcano.app_key == "appid"
    assert cfg.volcano.access_key == "token"
    assert cfg.volcano.api_key is None


def test_load_prefers_new_when_both_present(tmp_path: Path) -> None:
    """If user has both old and new creds, new wins (per spec §7 #11)."""
    env = tmp_path / ".env"
    env.write_text(
        "VOLC_API_KEY=newkey\n"
        "VOLC_APP_KEY=appid\n"
        "VOLC_ACCESS_KEY=token\n"
        "VOLC_RESOURCE_ID=volc.seedasr.auc\n"
    )
    cfg = config.load(env_path=env)
    assert cfg.volcano.console == "new"
    assert cfg.volcano.api_key == "newkey"


def test_load_raises_when_no_volcano_creds(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("VOLC_RESOURCE_ID=volc.seedasr.auc\n")
    with pytest.raises(config.ConfigError) as exc:
        config.load(env_path=env)
    assert "VOLC_API_KEY" in str(exc.value)


def test_load_raises_when_old_console_pair_incomplete(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "VOLC_APP_KEY=appid\n"
        "VOLC_RESOURCE_ID=volc.seedasr.auc\n"
        # missing VOLC_ACCESS_KEY
    )
    with pytest.raises(config.ConfigError) as exc:
        config.load(env_path=env)
    assert "VOLC_ACCESS_KEY" in str(exc.value)


def test_upload_backend_is_tos_when_tos_keys_present(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "VOLC_API_KEY=newkey\nVOLC_RESOURCE_ID=volc.seedasr.auc\n"
        "TOS_ACCESS_KEY=ak\nTOS_SECRET_KEY=sk\n"
        "TOS_BUCKET=b\nTOS_ENDPOINT=https://tos.example\n"
    )
    cfg = config.load(env_path=env)
    assert cfg.upload_backend == "tos"


def test_upload_backend_is_s3_when_only_s3_keys_present(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "VOLC_API_KEY=newkey\nVOLC_RESOURCE_ID=volc.seedasr.auc\n"
        "S3_ENDPOINT=https://r2.example\nS3_BUCKET=b\n"
        "S3_ACCESS_KEY=ak\nS3_SECRET_KEY=sk\n"
    )
    cfg = config.load(env_path=env)
    assert cfg.upload_backend == "s3"


def test_upload_backend_is_uguu_when_no_storage_keys(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("VOLC_API_KEY=newkey\nVOLC_RESOURCE_ID=volc.seedasr.auc\n")
    cfg = config.load(env_path=env)
    assert cfg.upload_backend == "uguu"


def test_load_missing_env_file_raises(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError) as exc:
        config.load(env_path=tmp_path / "nope.env")
    assert "not found" in str(exc.value).lower()


