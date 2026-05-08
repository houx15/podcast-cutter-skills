#!/usr/bin/env python3
"""Build an analysis context Markdown file for the agent editing stage.

Reads sentences.json, editing rules, and user preferences, then writes
EP_DIR/2_analysis/analysis_context.md with all context the agent needs to
produce rough_cuts.json, fine_cuts.json, and self_review.json.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_RULES_DIR = REPO_ROOT / "shared" / "rules" / "editing"
DEFAULT_PREFS_FILE = REPO_ROOT / "shared" / "rules" / "users" / "default" / "preferences.yaml"

OUTPUT_FORMAT = """\
## 输出格式要求

你（agent）需要在 `2_analysis/` 目录下写入三个 JSON 文件：

### rough_cuts.json（粗剪 — 大段内容级删除）
```json
{
  "deletes": [
    {
      "start_ms": <整数毫秒>,
      "end_ms": <整数毫秒>,
      "level": "rough",
      "reason": "<删除原因（中文）>",
      "source": "agent_rough",
      "confidence": <0.0-1.0>
    }
  ]
}
```

### fine_cuts.json（精剪 — 词/句级细节删除）
```json
{
  "deletes": [
    {
      "start_ms": <整数毫秒>,
      "end_ms": <整数毫秒>,
      "level": "fine",
      "reason": "<删除原因>",
      "source": "agent_fine",
      "confidence": <0.0-1.0>
    }
  ]
}
```

### self_review.json（自审 — 审查粗剪和精剪结果）
```json
{
  "deletes": [...],
  "flags": [
    {
      "start_ms": <整数毫秒>,
      "end_ms": <整数毫秒>,
      "flag": "false_positive",
      "reason": "<为什么这条建议是误删>"
    }
  ],
  "summary": "<总体评估，1-3句>"
}
```

所有时间戳必须是整数毫秒，与下方 sentences 列表中的 start_ms/end_ms 对应。"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ms_to_ts(ms: int) -> str:
    """Convert milliseconds to MM:SS timestamp string."""
    s = ms // 1000
    return f"{s // 60:02d}:{s % 60:02d}"


def _load_rules(rules_dir: Path) -> str:
    """Read all *.md files from rules_dir, sorted, concatenated."""
    md_files = sorted(rules_dir.glob("*.md"))
    parts = [f.read_text(encoding="utf-8") for f in md_files]
    return "\n\n---\n\n".join(parts)


def _format_sentences(sentences: list[dict]) -> str:
    """Format sentences as [MM:SS] SPEAKER: text lines."""
    lines: list[str] = []
    for s in sentences:
        ts = _ms_to_ts(s["start_ms"])
        lines.append(f"[{ts}] {s['speaker']}: {s['text']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assemble analysis context Markdown for the agent editing stage."
    )
    parser.add_argument("--ep-dir", required=True, help="Episode output directory")
    parser.add_argument(
        "--rules-dir",
        default=str(DEFAULT_RULES_DIR),
        help="Directory containing editing rules *.md files",
    )
    parser.add_argument(
        "--prefs-file",
        default=str(DEFAULT_PREFS_FILE),
        help="User preferences YAML file",
    )
    args = parser.parse_args()

    ep_dir = Path(args.ep_dir)
    rules_dir = Path(args.rules_dir)
    prefs_file = Path(args.prefs_file)

    # Read sentences.json — raises FileNotFoundError if missing
    sentences_path = ep_dir / "1_transcribe" / "sentences.json"
    if not sentences_path.exists():
        raise FileNotFoundError(f"sentences.json not found: {sentences_path}")

    data = json.loads(sentences_path.read_text(encoding="utf-8"))
    sentences: list[dict] = data["sentences"]
    n = len(sentences)

    # Read rules
    rules_text = _load_rules(rules_dir)

    # Read prefs (raw YAML text); fall back gracefully if file is absent
    prefs_text = (
        prefs_file.read_text(encoding="utf-8")
        if prefs_file.exists()
        else "(preferences not found)"
    )

    # Format sentences block
    sentences_text = _format_sentences(sentences)

    # Assemble output Markdown
    out_md = "\n\n".join(
        [
            "## 剪辑规则",
            rules_text,
            "## 用户偏好",
            f"```yaml\n{prefs_text.rstrip()}\n```",
            OUTPUT_FORMAT,
            f"## 完整文本（共 {n} 句）",
            sentences_text,
        ]
    )

    # Write output
    out_dir = ep_dir / "2_analysis"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "analysis_context.md"
    out_path.write_text(out_md, encoding="utf-8")

    byte_count = out_path.stat().st_size
    print(f"analysis_context.md written ({n} sentences, {byte_count} bytes)")


if __name__ == "__main__":
    main()
