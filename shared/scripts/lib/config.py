"""Single .env loader for the podcast cutter library.

Replaces the scattered env handling found in podcastcut-skills (some
scripts read .env, some os.environ, some --flag). Every script imports
config.load() and uses cfg.volcano.api_key / cfg.upload_backend / etc.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from dotenv import dotenv_values


class ConfigError(Exception):
    """Raised when required env vars are missing or malformed."""


@dataclass(frozen=True)
class VolcanoConfig:
    console: Literal["new", "old"]
    api_key: Optional[str]
    app_key: Optional[str]
    access_key: Optional[str]
    resource_id: str


@dataclass(frozen=True)
class TOSConfig:
    access_key: str
    secret_key: str
    bucket: str
    endpoint: str


@dataclass(frozen=True)
class S3Config:
    endpoint: str
    bucket: str
    access_key: str
    secret_key: str
    region: str


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    base_url: str
    model: str


@dataclass(frozen=True)
class Config:
    volcano: VolcanoConfig
    tos: Optional[TOSConfig]
    s3: Optional[S3Config]
    gemini_api_key: Optional[str]
    upload_backend: Literal["tos", "s3", "uguu"]
    llm: LLMConfig


def _nonempty(d: dict[str, str | None], key: str) -> Optional[str]:
    v = d.get(key)
    return v if v else None


def load(env_path: Path) -> Config:
    env_path = Path(env_path)
    if not env_path.is_file():
        raise ConfigError(f".env not found at {env_path}")
    raw = {k: v for k, v in dotenv_values(env_path).items()}

    volcano = _build_volcano(raw)
    tos = _build_tos(raw)
    s3 = _build_s3(raw)
    llm = _build_llm(raw)
    upload_backend: Literal["tos", "s3", "uguu"] = (
        "tos" if tos else "s3" if s3 else "uguu"
    )

    return Config(
        volcano=volcano,
        tos=tos,
        s3=s3,
        gemini_api_key=_nonempty(raw, "GEMINI_API_KEY"),
        upload_backend=upload_backend,
        llm=llm,
    )


def _build_volcano(raw: dict[str, str | None]) -> VolcanoConfig:
    api_key = _nonempty(raw, "VOLC_API_KEY")
    app_key = _nonempty(raw, "VOLC_APP_KEY")
    access_key = _nonempty(raw, "VOLC_ACCESS_KEY")
    resource_id = _nonempty(raw, "VOLC_RESOURCE_ID") or "volc.seedasr.auc"

    if api_key:
        return VolcanoConfig(
            console="new",
            api_key=api_key,
            app_key=None,
            access_key=None,
            resource_id=resource_id,
        )
    if app_key and access_key:
        return VolcanoConfig(
            console="old",
            api_key=None,
            app_key=app_key,
            access_key=access_key,
            resource_id=resource_id,
        )
    if app_key and not access_key:
        raise ConfigError("VOLC_APP_KEY set but VOLC_ACCESS_KEY missing")
    if access_key and not app_key:
        raise ConfigError("VOLC_ACCESS_KEY set but VOLC_APP_KEY missing")
    raise ConfigError(
        "no Volcano credentials. Set VOLC_API_KEY (new console, preferred) "
        "or VOLC_APP_KEY + VOLC_ACCESS_KEY (old console)."
    )


def _build_tos(raw: dict[str, str | None]) -> Optional[TOSConfig]:
    keys = ["TOS_ACCESS_KEY", "TOS_SECRET_KEY", "TOS_BUCKET", "TOS_ENDPOINT"]
    vals = [_nonempty(raw, k) for k in keys]
    if all(vals):
        return TOSConfig(
            access_key=vals[0],  # type: ignore[arg-type]
            secret_key=vals[1],  # type: ignore[arg-type]
            bucket=vals[2],  # type: ignore[arg-type]
            endpoint=vals[3],  # type: ignore[arg-type]
        )
    return None


def _build_s3(raw: dict[str, str | None]) -> Optional[S3Config]:
    required = ["S3_ENDPOINT", "S3_BUCKET", "S3_ACCESS_KEY", "S3_SECRET_KEY"]
    if all(_nonempty(raw, k) for k in required):
        return S3Config(
            endpoint=raw["S3_ENDPOINT"],  # type: ignore[arg-type]
            bucket=raw["S3_BUCKET"],  # type: ignore[arg-type]
            access_key=raw["S3_ACCESS_KEY"],  # type: ignore[arg-type]
            secret_key=raw["S3_SECRET_KEY"],  # type: ignore[arg-type]
            region=_nonempty(raw, "S3_REGION") or "auto",
        )
    return None


def _build_llm(raw: dict[str, str | None]) -> LLMConfig:
    for key in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        if not _nonempty(raw, key):
            raise ConfigError(key)
    return LLMConfig(
        api_key=raw["LLM_API_KEY"],  # type: ignore[arg-type]
        base_url=raw["LLM_BASE_URL"],  # type: ignore[arg-type]
        model=raw["LLM_MODEL"],  # type: ignore[arg-type]
    )
