#!/usr/bin/env python3
"""Stage 2.3: LLM self-review of rough+fine cuts → self_review.json."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).parent.parent.parent


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
    args = ap.parse_args()

    repo = _repo_root()
    env_path = Path(args.env) if args.env else repo / ".env"

    sys.path.insert(0, str(Path(__file__).parent))
    from lib.config import load
    import openai

    cfg = load(env_path)
    ep_dir = Path(args.ep_dir)
    td = ep_dir / "1_transcribe"
    ad = ep_dir / "2_analysis"
    ad.mkdir(parents=True, exist_ok=True)

    sentences = json.loads((td / "sentences.json").read_text())["sentences"]
    rough = json.loads((ad / "rough_cuts.json").read_text())
    fine = json.loads((ad / "fine_cuts.json").read_text())

    system_prompt = """你是一个严格的播客剪辑质检员，负责审查AI提出的剪辑建议。
请评估rough_cuts和fine_cuts中的每个删除建议：
1. 是否有误删（false positive）—— 不该删的被删了？
2. 是否有遗漏（false negative）—— 应该删的没删？

输出JSON格式：
{
  "deletes": [
    {
      "start_ms": <ms>, "end_ms": <ms>,
      "level": "fine",
      "reason": "<reason>",
      "source": "self_review",
      "confidence": <0.0-1.0>,
      "evidence_word_idx": [<start_idx>, <end_idx>]
    }
  ],
  "flags": [
    {
      "start_ms": <ms>, "end_ms": <ms>,
      "flag": "false_positive",
      "reason": "<reason>"
    }
  ],
  "summary": "<总体评估，1-3句>"
}

只输出JSON。"""

    user_prompt = (
        f"句子列表：\n{json.dumps(sentences, ensure_ascii=False, indent=2)}\n\n"
        f"粗剪建议：\n{json.dumps(rough['deletes'], ensure_ascii=False)}\n\n"
        f"精剪建议：\n{json.dumps(fine['deletes'], ensure_ascii=False)}"
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

    # Validate required keys
    if "deletes" not in result:
        raise ValueError("self_review response missing 'deletes' key")
    if "summary" not in result:
        raise ValueError("self_review response missing 'summary' key")

    (ad / "self_review.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"self_review.json written. Summary: {result.get('summary', '')[:100]}")


if __name__ == "__main__":
    main()
