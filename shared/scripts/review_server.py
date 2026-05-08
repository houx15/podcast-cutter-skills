#!/usr/bin/env python3
"""Stage 3.0: Flask server for file-backed review state."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

from flask import Flask, jsonify, request

app = Flask(__name__)
_ep_dir: Path = Path(".")


@app.route("/state", methods=["GET"])
def get_state():
    state_file = _ep_dir / "3_review" / "review_state.json"
    if not state_file.exists():
        return jsonify({"deletes": []}), 200
    return jsonify(json.loads(state_file.read_text())), 200


@app.route("/state", methods=["PATCH"])
def patch_state():
    data = request.get_json()
    state_file = _ep_dir / "3_review" / "review_state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return jsonify({"ok": True}), 200


@app.route("/export", methods=["POST"])
def export():
    body = request.get_json() or {}
    state_file = _ep_dir / "3_review" / "review_state.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else {"deletes": []}
    out = {
        "deletes": state["deletes"],
        "user_notes": body.get("user_notes", ""),
        "feedback_for_learning": body.get("feedback_for_learning", []),
    }
    out_file = _ep_dir / "3_review" / "delete_segments_edited.json"
    out_file.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    return jsonify({"ok": True, "path": str(out_file)}), 200


def main() -> None:
    global _ep_dir
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep-dir", required=True)
    ap.add_argument("--port", type=int, default=5050)
    ap.add_argument("--no-serve", action="store_true",
                    help="init module only, skip app.run() (for tests)")
    args = ap.parse_args()
    _ep_dir = Path(args.ep_dir)
    if not args.no_serve:
        app.run(host="127.0.0.1", port=args.port, debug=False)


if __name__ == "__main__":
    main()
