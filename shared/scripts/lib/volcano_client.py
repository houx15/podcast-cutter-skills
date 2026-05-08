"""Volcano AUC v3 big-model ASR client (header building + polling + errors).

HTTP is injected so the module is unit-testable without network.
docs/volcano_asr.md is the source of truth for endpoints, headers, codes.
"""
from __future__ import annotations

import enum
import json
import time
from dataclasses import dataclass
from typing import Any, Callable

from .config import VolcanoConfig

SUBMIT_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
QUERY_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"


class QueryStatus(enum.Enum):
    SUCCESS = "success"
    PROCESSING = "processing"
    QUEUED = "queued"
    HARD_FAIL = "hard_fail"
    RETRYABLE = "retryable"


@dataclass
class VolcanoError(Exception):
    code: str
    message: str
    context: dict[str, Any]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"[{self.code}] {self.message}"


# Per docs/volcano_asr.md error code table.
_HARD_FAIL_CODES: dict[str, str] = {
    "20000003": "音频无人声，检查录音是否为空轨",
    "45000001": "请求参数无效（缺字段或值错误）",
    "45000002": "音频为空，先用 ffprobe 检查文件",
    "45000132": "音频超 512 MB Volcano 上限，建议先 ffmpeg 转 16 kHz mono mp3",
    "45000151": "音频格式不正确，先用 ffprobe 检查",
}

_RETRYABLE_CODES: set[str] = {
    "45000131",  # 30-min rate limit exceeded
    "55000031",  # service busy
}


def classify_status(code: str) -> QueryStatus:
    if code == "20000000":
        return QueryStatus.SUCCESS
    if code == "20000001":
        return QueryStatus.PROCESSING
    if code == "20000002":
        return QueryStatus.QUEUED
    if code in _HARD_FAIL_CODES:
        return QueryStatus.HARD_FAIL
    if code in _RETRYABLE_CODES:
        return QueryStatus.RETRYABLE
    if code.startswith("550"):
        return QueryStatus.RETRYABLE
    return QueryStatus.HARD_FAIL


def message_for_code(code: str) -> str:
    if code in _HARD_FAIL_CODES:
        return _HARD_FAIL_CODES[code]
    if code == "45000131":
        return "30 分钟内提交时长超过 500h 上限，需降低提交速度"
    if code == "55000031":
        return "服务繁忙，重试"
    if code.startswith("550"):
        return "服务内部错误，重试"
    return f"未知错误 {code}"


def _common_headers(cfg: VolcanoConfig, task_id: str) -> dict[str, str]:
    h = {
        "X-Api-Resource-Id": cfg.resource_id,
        "X-Api-Request-Id": task_id,
    }
    if cfg.console == "new":
        assert cfg.api_key is not None
        h["X-Api-Key"] = cfg.api_key
    else:
        assert cfg.app_key is not None and cfg.access_key is not None
        h["X-Api-App-Key"] = cfg.app_key
        h["X-Api-Access-Key"] = cfg.access_key
    return h


def build_submit_headers(cfg: VolcanoConfig, task_id: str) -> dict[str, str]:
    h = _common_headers(cfg, task_id)
    h["X-Api-Sequence"] = "-1"
    return h


def build_query_headers(cfg: VolcanoConfig, task_id: str) -> dict[str, str]:
    return _common_headers(cfg, task_id)


def build_submit_payload(
    *,
    audio_url: str,
    audio_format: str,
    uid: str,
    enable_speaker_info: bool,
    hotwords: list[str],
    enable_punc: bool = True,
    enable_itn: bool = True,
    enable_ddc: bool = False,
    show_utterances: bool = True,
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "model_name": "bigmodel",
        "enable_itn": enable_itn,
        "enable_punc": enable_punc,
        "enable_ddc": enable_ddc,
        "enable_speaker_info": enable_speaker_info,
        "show_utterances": show_utterances,
    }
    if hotwords:
        request["corpus"] = {
            "context": json.dumps({"hotwords": [{"word": w} for w in hotwords]})
        }
    return {
        "user": {"uid": uid},
        "audio": {"url": audio_url, "format": audio_format},
        "request": request,
    }


def poll_until_done(
    query_fn: Callable[[], tuple[str, dict[str, Any]]],
    *,
    interval_seconds: float,
    max_attempts: int,
) -> dict[str, Any]:
    """Drive a Volcano query loop until success / hard_fail / max_attempts.

    query_fn returns (status_code, response_body). Caller wires it to real HTTP.
    """
    last_code = ""
    last_body: dict[str, Any] = {}
    for _ in range(max_attempts):
        last_code, last_body = query_fn()
        status = classify_status(last_code)
        if status is QueryStatus.SUCCESS:
            return last_body
        if status is QueryStatus.HARD_FAIL:
            raise VolcanoError(
                code=last_code,
                message=message_for_code(last_code),
                context=last_body,
            )
        # PROCESSING, QUEUED, RETRYABLE → keep polling
        if interval_seconds > 0:
            time.sleep(interval_seconds)
    raise VolcanoError(
        code=last_code or "timeout",
        message=f"max_attempts={max_attempts} exceeded; last status={last_code}",
        context=last_body,
    )
