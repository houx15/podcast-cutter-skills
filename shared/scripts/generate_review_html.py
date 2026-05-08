#!/usr/bin/env python3
"""Stage 3.0: Generate review_enhanced.html for human review."""
from __future__ import annotations
import argparse, json
from pathlib import Path


def _ms_to_ts(ms: int) -> str:
    s = ms // 1000
    return f"{s // 60:02d}:{s % 60:02d}"


HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh">
<head><meta charset="UTF-8"><title>播客剪辑审查</title>
<style>
body {{ font-family: sans-serif; max-width: 900px; margin: 2em auto; }}
.delete {{ background: #ffe0e0; border-left: 4px solid #c00; padding: 8px; margin: 8px 0; }}
.sentence {{ padding: 4px 0; border-bottom: 1px solid #eee; }}
.timestamp {{ color: #888; font-size: 0.85em; margin-right: 6px; }}
.speaker {{ font-weight: bold; margin-right: 8px; }}
</style>
</head>
<body>
<h1>播客剪辑审查</h1>
<p>Episode: <strong>{episode_id}</strong> | 句子数: {sent_count} | 建议删除: {delete_count}</p>
<h2>删除建议</h2>
{delete_html}
<h2>完整文本</h2>
{transcript_html}
</body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep-dir", required=True)
    args = ap.parse_args()

    ep_dir = Path(args.ep_dir)
    td = ep_dir / "1_transcribe"
    ad = ep_dir / "2_analysis"
    rd = ep_dir / "3_review"
    rd.mkdir(parents=True, exist_ok=True)

    sentences = json.loads((td / "sentences.json").read_text())["sentences"]
    rough = json.loads((ad / "rough_cuts.json").read_text())["deletes"]
    fine = json.loads((ad / "fine_cuts.json").read_text())["deletes"]
    sr_data = json.loads((ad / "self_review.json").read_text()) if (ad / "self_review.json").exists() else {}
    all_deletes = rough + fine + sr_data.get("deletes", [])

    delete_html = ""
    for d in all_deletes:
        conf = d.get("confidence", 0.0)
        delete_html += (
            f'<div class="delete">'
            f'[{_ms_to_ts(d["start_ms"])} - {_ms_to_ts(d["end_ms"])}] '
            f'<b>{d["level"]}</b> ({d["source"]}, conf={conf:.2f}): '
            f'{d["reason"]}'
            f'</div>\n'
        )

    transcript_html = ""
    for s in sentences:
        transcript_html += (
            f'<div class="sentence">'
            f'<span class="speaker">{s["speaker"]}</span>'
            f'<span class="timestamp">{_ms_to_ts(s["start_ms"])}</span>'
            f'{s["text"]}'
            f'</div>\n'
        )

    html = HTML_TEMPLATE.format(
        episode_id=ep_dir.name,
        sent_count=len(sentences),
        delete_count=len(all_deletes),
        delete_html=delete_html,
        transcript_html=transcript_html,
    )
    (rd / "review_enhanced.html").write_text(html, encoding="utf-8")
    print(f"review_enhanced.html written ({len(sentences)} sentences, {len(all_deletes)} deletes)")

    # initialize review_state.json from all deletes (if not already present)
    state_file = rd / "review_state.json"
    if not state_file.exists():
        state_deletes = [{**d, "user_action": "kept"} for d in all_deletes]
        state_file.write_text(json.dumps({"deletes": state_deletes}, ensure_ascii=False, indent=2))
        print(f"review_state.json initialized with {len(state_deletes)} entries")


if __name__ == "__main__":
    main()
