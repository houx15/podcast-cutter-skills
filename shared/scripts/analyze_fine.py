#!/usr/bin/env python3
"""Stage 2.2: LLM fine cut analysis → fine_cuts.json."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).parent.parent.parent


REQUIRED_DELETE_FIELDS = {"start_ms", "end_ms", "level", "reason", "source", "confidence"}


def _load_rules(rules_dir: Path) -> str:
    parts = []
    for md in sorted(rules_dir.glob("*.md")):
        parts.append(md.read_text())
    return "\n\n---\n\n".join(parts)


def _validate_deletes(deletes: list[dict]) -> None:
    for d in deletes:
        missing = REQUIRED_DELETE_FIELDS - set(d.keys())
        if missing:
            raise ValueError(f"Delete entry missing fields: {missing}. Got: {d}")
        if d.get("level") not in ("rough", "fine"):
            raise ValueError(f"Delete level must be 'rough' or 'fine', got: {d.get('level')}")


def _strip_code_fences(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:])
        if content.rstrip().endswith("```"):
            content = content.rstrip()[:-3]
    return content.strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep-dir", required=True)
    ap.add_argument("--env", default=None)
    ap.add_argument("--rules-dir", default=None)
    args = ap.parse_args()

    repo = _repo_root()
    env_path = Path(args.env) if args.env else repo / ".env"
    rules_dir = Path(args.rules_dir) if args.rules_dir else repo / "shared/rules/editing"

    sys.path.insert(0, str(Path(__file__).parent))
    from lib.config import load
    import openai

    cfg = load(env_path)
    ep_dir = Path(args.ep_dir)
    td = ep_dir / "1_transcribe"
    ad = ep_dir / "2_analysis"
    ad.mkdir(parents=True, exist_ok=True)

    sentences = json.loads((td / "sentences.json").read_text())["sentences"]
    words = json.loads((td / "words.json").read_text())["words"]
    rough = json.loads((ad / "rough_cuts.json").read_text())
    rules_text = _load_rules(rules_dir)

    system_prompt = f"""你是一个播客精剪助手，负责词级别的精剪分析。
粗剪已经标记了大段删除，现在需要找出剩余内容中的词级别口头禅、语气词等应删除的细节。

{rules_text}

已标记的粗剪区间（fine pass中请跳过这些区间内的内容）：
{json.dumps(rough['deletes'], ensure_ascii=False)}

输出严格的JSON，格式：
{{
  "deletes": [
    {{
      "start_ms": <整数毫秒>,
      "end_ms": <整数毫秒>,
      "level": "fine",
      "reason": "<删除原因>",
      "source": "ai_fine",
      "confidence": <0.0-1.0>,
      "evidence_word_idx": [<起始词idx>, <结束词idx>]
    }}
  ]
}}

只输出JSON，不要任何解释。"""

    user_prompt = (
        f"句子列表：\n{json.dumps(sentences, ensure_ascii=False, indent=2)}\n\n"
        f"词列表（前200个）：\n{json.dumps(words[:200], ensure_ascii=False, indent=2)}"
    )

    client = openai.OpenAI(api_key=cfg.llm.api_key, base_url=cfg.llm.base_url)
    response = client.chat.completions.create(
        model=cfg.llm.model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
    )
    content = _strip_code_fences(response.choices[0].message.content)
    result = json.loads(content)
    _validate_deletes(result["deletes"])

    (ad / "fine_cuts.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"fine_cuts.json: {len(result['deletes'])} deletes")


if __name__ == "__main__":
    main()
