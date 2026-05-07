"""Tests for shared.scripts.lib.volcano_client."""
from __future__ import annotations

from typing import Any

import pytest

from shared.scripts.lib import config, volcano_client


def _new_console_cfg() -> config.VolcanoConfig:
    return config.VolcanoConfig(
        console="new",
        api_key="newkey",
        app_key=None,
        access_key=None,
        resource_id="volc.seedasr.auc",
    )


def _old_console_cfg() -> config.VolcanoConfig:
    return config.VolcanoConfig(
        console="old",
        api_key=None,
        app_key="appid",
        access_key="token",
        resource_id="volc.seedasr.auc",
    )


def test_submit_headers_new_console_uses_single_api_key() -> None:
    headers = volcano_client.build_submit_headers(
        _new_console_cfg(), task_id="t-1"
    )
    assert headers["X-Api-Key"] == "newkey"
    assert headers["X-Api-Resource-Id"] == "volc.seedasr.auc"
    assert headers["X-Api-Request-Id"] == "t-1"
    assert headers["X-Api-Sequence"] == "-1"
    assert "X-Api-App-Key" not in headers
    assert "X-Api-Access-Key" not in headers


def test_submit_headers_old_console_uses_pair() -> None:
    headers = volcano_client.build_submit_headers(
        _old_console_cfg(), task_id="t-2"
    )
    assert headers["X-Api-App-Key"] == "appid"
    assert headers["X-Api-Access-Key"] == "token"
    assert "X-Api-Key" not in headers


def test_query_headers_omit_x_api_sequence() -> None:
    """Per docs/volcano_asr.md: query has no Sequence header."""
    headers = volcano_client.build_query_headers(_new_console_cfg(), task_id="t-3")
    assert "X-Api-Sequence" not in headers
    assert headers["X-Api-Request-Id"] == "t-3"


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("20000000", volcano_client.QueryStatus.SUCCESS),
        ("20000001", volcano_client.QueryStatus.PROCESSING),
        ("20000002", volcano_client.QueryStatus.QUEUED),
    ],
)
def test_classify_status_in_progress(code: str, expected: volcano_client.QueryStatus) -> None:
    assert volcano_client.classify_status(code) is expected


@pytest.mark.parametrize(
    "code",
    ["20000003", "45000001", "45000002", "45000132", "45000151"],
)
def test_classify_status_hard_fail(code: str) -> None:
    """These codes must map to HARD_FAIL with the message from the spec."""
    assert volcano_client.classify_status(code) is volcano_client.QueryStatus.HARD_FAIL


@pytest.mark.parametrize("code", ["45000131", "55000031", "5500999"])
def test_classify_status_retryable(code: str) -> None:
    assert volcano_client.classify_status(code) is volcano_client.QueryStatus.RETRYABLE


def test_message_for_silent_audio() -> None:
    msg = volcano_client.message_for_code("20000003")
    assert "无人声" in msg


def test_message_for_oversize_audio_mentions_512mb() -> None:
    msg = volcano_client.message_for_code("45000132")
    assert "512" in msg


def test_submit_payload_minimal() -> None:
    p = volcano_client.build_submit_payload(
        audio_url="https://example/audio.mp3",
        audio_format="mp3",
        uid="user-1",
        enable_speaker_info=True,
        hotwords=["热词1", "热词2"],
    )
    assert p["audio"]["url"] == "https://example/audio.mp3"
    assert p["audio"]["format"] == "mp3"
    assert p["request"]["enable_speaker_info"] is True
    assert p["user"]["uid"] == "user-1"
    # Hotwords go through corpus.context as documented JSON string.
    import json as _json
    ctx = _json.loads(p["request"]["corpus"]["context"])
    assert ctx == {"hotwords": [{"word": "热词1"}, {"word": "热词2"}]}


def test_submit_payload_omits_corpus_when_no_hotwords() -> None:
    p = volcano_client.build_submit_payload(
        audio_url="https://example/audio.mp3",
        audio_format="mp3",
        uid="user-1",
        enable_speaker_info=True,
        hotwords=[],
    )
    assert "corpus" not in p["request"]


def test_poll_until_done_returns_result_on_success() -> None:
    calls: list[int] = []

    def fake_query() -> tuple[str, dict[str, Any]]:
        calls.append(1)
        if len(calls) < 3:
            return ("20000001", {})
        return ("20000000", {"result": {"text": "ok"}})

    result = volcano_client.poll_until_done(
        fake_query, interval_seconds=0, max_attempts=10
    )
    assert result == {"result": {"text": "ok"}}
    assert len(calls) == 3


def test_poll_until_done_raises_on_hard_fail() -> None:
    def fake_query() -> tuple[str, dict[str, Any]]:
        return ("20000003", {})

    with pytest.raises(volcano_client.VolcanoError) as exc:
        volcano_client.poll_until_done(
            fake_query, interval_seconds=0, max_attempts=10
        )
    assert exc.value.code == "20000003"
    assert "无人声" in str(exc.value)


def test_poll_until_done_retries_then_gives_up() -> None:
    def fake_query() -> tuple[str, dict[str, Any]]:
        return ("55000031", {})

    with pytest.raises(volcano_client.VolcanoError) as exc:
        volcano_client.poll_until_done(
            fake_query, interval_seconds=0, max_attempts=3
        )
    assert exc.value.code == "55000031"
