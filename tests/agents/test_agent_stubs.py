"""Verify reviewer subagent files exist with correct frontmatter."""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AGENTS_DIR = REPO_ROOT / ".claude" / "agents"


REQUIRED_AGENTS = [
    "spec-drift-reviewer",
    "ffmpeg-invariants-reviewer",
    "prompt-eval-reviewer",
    "listening-spot-check-reviewer",
]


@pytest.mark.parametrize("name", REQUIRED_AGENTS)
def test_agent_file_exists(name: str) -> None:
    path = AGENTS_DIR / f"{name}.md"
    assert path.exists(), f"missing reviewer agent: {path}"


@pytest.mark.parametrize("name", REQUIRED_AGENTS)
def test_agent_has_yaml_frontmatter(name: str) -> None:
    path = AGENTS_DIR / f"{name}.md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{name} missing frontmatter"
    end = text.find("\n---\n", 4)
    assert end > 0, f"{name} frontmatter not closed"
    fm = text[4:end]
    assert "name:" in fm
    assert "description:" in fm


def test_ffmpeg_reviewer_references_反馈记录() -> None:
    text = (AGENTS_DIR / "ffmpeg-invariants-reviewer.md").read_text(encoding="utf-8")
    assert "反馈记录" in text


def test_prompt_eval_reviewer_references_eval_gold() -> None:
    text = (AGENTS_DIR / "prompt-eval-reviewer.md").read_text(encoding="utf-8")
    assert "shared/eval/gold" in text


def test_listening_reviewer_references_timeline_manifest() -> None:
    text = (AGENTS_DIR / "listening-spot-check-reviewer.md").read_text(
        encoding="utf-8"
    )
    assert "timeline_manifest.json" in text
