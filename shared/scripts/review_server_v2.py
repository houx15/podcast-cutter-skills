#!/usr/bin/env python3
"""Stage 3: browser-based coarse review of agent-proposed cuts on mixed_orig.wav.

Loads:
  input/mixed_orig.wav                    — audio to audition
  1_transcribe/sentences.json             — full transcript for context
  2_analysis/char_level.json              — deterministic stutter / filler / marker / habit
  2_analysis/agent_picks.json (optional)  — agent-written region + editorial cuts

All proposals carry start_ms / end_ms in ORIGINAL timeline. No cut→orig
translation happens here — that's the bug that caused 5-10s drift across
iterations. Accepted cuts are written directly to 3_review/delete_segments_edited.json
in original timeline (the same file cut_audio.py consumes). Each round of
review starts fresh: rerun this script to load the latest proposals from disk.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path

from flask import Flask, jsonify, request, send_file

app = Flask(__name__)
_ep_dir: Path = Path(".")


def _load_proposals() -> list[dict]:
    """Load char_level.json + agent_picks.json. Both should already be in
    orig timeline with start_ms/end_ms fields."""
    out: list[dict] = []
    char_path = _ep_dir / "2_analysis" / "char_level.json"
    if char_path.exists():
        out.extend(json.loads(char_path.read_text())["proposals"])

    picks_path = _ep_dir / "2_analysis" / "agent_picks.json"
    if picks_path.exists():
        for p in json.loads(picks_path.read_text())["proposals"]:
            # agent_picks may use "deletes" array — accept both
            out.append(p)

    # Normalize: ensure status field, sort by time
    for p in out:
        p.setdefault("status", "pending")
    out.sort(key=lambda p: p["start_ms"])
    return out


def _save_proposal_status(pid: str, status: str, comment: str) -> None:
    """Persist accept/reject + comment back to the source JSON files."""
    for fname in ("char_level.json", "agent_picks.json"):
        path = _ep_dir / "2_analysis" / fname
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        changed = False
        for p in data["proposals"]:
            if p.get("id") == pid:
                p["status"] = status
                if comment.strip():
                    p["user_comment"] = comment.strip()
                elif "user_comment" in p:
                    del p["user_comment"]
                changed = True
                break
        if changed:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            return


def _rebuild_coarse_deletes_from_proposals() -> None:
    """Reconstruct 3_review/delete_segments_edited.json from accepted proposals.
    Idempotent — safe to call after any accept/reject."""
    rd = _ep_dir / "3_review"
    rd.mkdir(parents=True, exist_ok=True)

    proposals = _load_proposals()
    deletes = []
    for p in proposals:
        if p.get("status") != "accepted":
            continue
        reason = f"[{p.get('category', '?')}] {p.get('reason', '')}"
        if p.get("user_comment", "").strip():
            reason += f" | 用户备注: {p['user_comment'].strip()}"
        deletes.append({
            "start_ms": p["start_ms"],
            "end_ms": p["end_ms"],
            "level": "rough" if p.get("category") in {"region", "editorial"} else "fine",
            "reason": reason,
            "source": p.get("source", "agent_proposal_accepted"),
            "confidence": p.get("confidence", 1.0),
            "user_action": "kept",
        })

    out_path = rd / "delete_segments_edited.json"
    out_path.write_text(json.dumps(
        {"deletes": deletes, "user_notes": "", "feedback_for_learning": []},
        ensure_ascii=False, indent=2,
    ))


@app.route("/")
def index():
    sents = json.loads((_ep_dir / "1_transcribe" / "sentences.json").read_text())["sentences"]
    proposals = _load_proposals()
    return _render_html(sents, proposals)


@app.route("/audio")
def audio():
    return send_file(str(_ep_dir / "input" / "mixed_orig.wav"),
                     mimetype="audio/wav", conditional=True)


@app.route("/accept-proposal", methods=["POST"])
def accept_proposal():
    body = request.get_json() or {}
    pid = body["id"]
    comment = body.get("comment", "")
    _save_proposal_status(pid, "accepted", comment)
    _rebuild_coarse_deletes_from_proposals()
    return jsonify({"ok": True})


@app.route("/reject-proposal", methods=["POST"])
def reject_proposal():
    body = request.get_json() or {}
    pid = body["id"]
    comment = body.get("comment", "")
    _save_proposal_status(pid, "rejected", comment)
    _rebuild_coarse_deletes_from_proposals()
    return jsonify({"ok": True})


@app.route("/save-comment", methods=["POST"])
def save_comment():
    body = request.get_json() or {}
    pid = body["id"]
    comment = body.get("comment", "")
    # Save without changing status
    proposals = _load_proposals()
    p = next((x for x in proposals if x.get("id") == pid), None)
    if p:
        _save_proposal_status(pid, p.get("status", "pending"), comment)
    return jsonify({"ok": True})


@app.route("/add-cut", methods=["POST"])
def add_cut():
    """Add a manually-marked cut directly to coarse_deletes.json (orig timeline)."""
    body = request.get_json() or {}
    s = int(body["start_ms"])
    e = int(body["end_ms"])
    reason = body.get("reason", "manual")
    if e <= s:
        return jsonify({"ok": False, "error": "end <= start"}), 400

    out_path = _ep_dir / "3_review" / "delete_segments_edited.json"
    if out_path.exists():
        data = json.loads(out_path.read_text())
    else:
        data = {"deletes": [], "user_notes": "", "feedback_for_learning": []}
    data["deletes"].append({
        "start_ms": s, "end_ms": e, "level": "rough",
        "reason": f"[manual] {reason}",
        "source": "human_review",
        "confidence": 1.0,
        "user_action": "kept",
    })
    data["deletes"].sort(key=lambda d: d["start_ms"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return jsonify({"ok": True})


def _render_html(sents: list, proposals: list) -> str:
    sents_js = json.dumps(sents, ensure_ascii=False)
    props_js = json.dumps(proposals, ensure_ascii=False)
    return r"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>原始音频审查 (Stage 3)</title>
<style>
body { font-family: -apple-system, sans-serif; max-width: 1100px; margin: 1em auto; padding: 0 1em; }
.player { position: sticky; top: 0; background: white; padding: 1em 0; border-bottom: 1px solid #ccc; z-index: 100; }
audio { width: 100%; }
.controls { display: flex; gap: 1em; align-items: center; margin: 0.5em 0; flex-wrap: wrap; }
.sentence { padding: 4px 0; border-bottom: 1px solid #eee; cursor: pointer; }
.sentence:hover { background: #f0f8ff; }
.timestamp { color: #888; font-size: 0.85em; margin-right: 6px; font-family: monospace; min-width: 60px; display: inline-block; }
.speaker { font-weight: bold; margin-right: 8px; color: #06a; }
.s2 .speaker { color: #c50; }

.tabs { display: flex; gap: 0; margin-top: 1em; border-bottom: 2px solid #ddd; }
.tab { padding: 8px 16px; cursor: pointer; border: 1px solid #ddd; border-bottom: none; background: #f5f5f5; }
.tab.active { background: white; font-weight: bold; border-bottom: 2px solid white; margin-bottom: -2px; }
.tab-body { display: none; }
.tab-body.active { display: block; }

.proposal { padding: 8px 12px; border-left: 4px solid #aaa; margin: 8px 0; background: #fafafa; border-radius: 0 4px 4px 0; }
.proposal.region { border-left-color: #939; }
.proposal.editorial { border-left-color: #6a3; }
.proposal.stutter { border-left-color: #a36; }
.proposal.filler-run { border-left-color: #c90; }
.proposal.marker { border-left-color: #c66; }
.proposal.habit { border-left-color: #cb6; }
.proposal.accepted { opacity: 0.5; background: #e8f5e8; border-left-color: #2a2; }
.proposal.rejected { opacity: 0.5; background: #f5e8e8; border-left-color: #a22; text-decoration: line-through; }
.prop-head { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.prop-cat { font-size: 0.75em; padding: 2px 6px; border-radius: 3px; background: #eee; font-weight: bold; }
.prop-cat.region { background: #ecd; }
.prop-cat.editorial { background: #cea; }
.prop-cat.stutter { background: #fcd; }
.prop-cat.filler-run { background: #fec; }
.prop-cat.marker { background: #fcc; }
.prop-cat.habit { background: #fec0; background: #fec; }
.prop-time { font-family: monospace; font-size: 0.9em; color: #555; }
.prop-actions { margin-left: auto; display: flex; gap: 4px; }
.prop-reason { margin-top: 4px; font-size: 0.9em; color: #444; }
.prop-comment-row { margin-top: 6px; display: flex; gap: 6px; align-items: center; }
.prop-comment-row label { font-size: 0.8em; color: #888; min-width: 36px; }
.prop-comment { flex: 1; padding: 3px 6px; font-size: 0.85em; border: 1px solid #ddd; border-radius: 3px; font-family: inherit; }
.prop-comment.dirty { border-color: #f80; background: #fffaf0; }
.prop-comment.saved { border-color: #2a2; background: #f0fff0; }
.prop-comment-saved-mark { font-size: 0.75em; color: #2a2; min-width: 30px; }

button { padding: 4px 12px; cursor: pointer; border: 1px solid #ccc; background: white; border-radius: 3px; }
button:hover { background: #f0f0f0; }
button.play { background: #def; }
button.accept { background: #cfc; }
button.reject { background: #fcc; }
.hint { color: #666; font-size: 0.85em; }
.summary { font-size: 0.85em; color: #666; }
</style>
</head>
<body>
<h1>原始音频审查 <span class="hint">(Stage 3 — 接受/拒绝写入 3_review/delete_segments_edited.json)</span></h1>

<div class="player">
<audio id="audio" controls preload="metadata"><source src="/audio" type="audio/wav"></audio>
<div class="controls">
  <span>当前: <span id="cur-time">00:00.0</span></span>
</div>
</div>

<div class="tabs">
  <div class="tab active" data-target="proposals">候选删除 <span id="prop-count" class="summary"></span></div>
  <div class="tab" data-target="sentences">完整文本</div>
</div>

<div id="proposals" class="tab-body active">
  <div class="hint">点 <b>▶ 试听</b> 听上下文 ±1.5s，<b>✓ 接受</b> 写入删除列表，<b>✗ 拒绝</b> 跳过。</div>
  <div class="controls">
    <span>类别:</span>
    <label><input type="checkbox" data-filter="region" checked> 整段</label>
    <label><input type="checkbox" data-filter="editorial" checked> 编辑判断</label>
    <label><input type="checkbox" data-filter="marker" checked> 自纠/打断</label>
    <label><input type="checkbox" data-filter="stutter" checked> 口吃</label>
    <label><input type="checkbox" data-filter="filler-run" checked> 语气词连</label>
    <label><input type="checkbox" data-filter="habit" checked> 口癖</label>
  </div>
  <div class="controls">
    <span>状态:</span>
    <label><input type="checkbox" data-filter="pending" checked> 待审</label>
    <label><input type="checkbox" data-filter="accepted"> 已接受</label>
    <label><input type="checkbox" data-filter="rejected"> 已拒绝</label>
  </div>
  <div id="proposal-list"></div>
</div>

<div id="sentences" class="tab-body">
  <div id="sentence-list"></div>
</div>

<script>
const SENTS = __SENTS__;
const PROPOSALS = __PROPS__;
const audio = document.getElementById("audio");

function fmt(s) {
  const m = Math.floor(s/60), x = (s % 60).toFixed(1);
  return String(m).padStart(2,'0') + ':' + String(x).padStart(4,'0');
}
audio.addEventListener("timeupdate", () => {
  document.getElementById("cur-time").textContent = fmt(audio.currentTime);
});

let stopAtMs = null;
function playSpan(startMs, endMs) {
  audio.currentTime = Math.max(0, startMs / 1000);
  stopAtMs = endMs;
  audio.play();
}
audio.addEventListener("timeupdate", () => {
  if (stopAtMs != null && audio.currentTime * 1000 >= stopAtMs) {
    audio.pause();
    stopAtMs = null;
  }
});

function commentOf(pid) {
  const el = document.querySelector(`#prop-${pid} .prop-comment`);
  return el ? el.value : "";
}
function findProposal(pid) { return PROPOSALS.find(x => x.id === pid); }

function acceptProposal(pid) {
  const p = findProposal(pid);
  if (!p) return;
  fetch("/accept-proposal", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({id: p.id, comment: commentOf(p.id)})
  }).then(r => r.json()).then(data => {
    if (!data.ok) { alert("接受失败"); return; }
    p.status = "accepted";
    p.user_comment = commentOf(p.id);
    renderProposals();
  });
}
function rejectProposal(pid) {
  const p = findProposal(pid);
  if (!p) return;
  fetch("/reject-proposal", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({id: p.id, comment: commentOf(p.id)})
  }).then(r => r.json()).then(data => {
    p.status = "rejected";
    p.user_comment = commentOf(p.id);
    renderProposals();
  });
}
function saveCommentNow(pid, ev) {
  const el = ev.target;
  const comment = el.value;
  fetch("/save-comment", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({id: pid, comment})
  }).then(r => r.json()).then(() => {
    el.classList.remove("dirty"); el.classList.add("saved");
    setTimeout(() => el.classList.remove("saved"), 1200);
    const mark = document.querySelector(`#prop-${pid} .prop-comment-saved-mark`);
    if (mark) mark.textContent = comment.trim() ? "✓ 已存" : "";
  });
}
function commentDirty(ev) { ev.target.classList.add("dirty"); ev.target.classList.remove("saved"); }

const CATEGORY_FILTERS = ["region", "editorial", "marker", "stutter", "filler-run", "habit"];
function activeFilters() {
  const cats = new Set();
  const states = new Set();
  document.querySelectorAll('input[data-filter]:checked').forEach(cb => {
    const f = cb.dataset.filter;
    if (CATEGORY_FILTERS.includes(f)) cats.add(f);
    else states.add(f);
  });
  return {cats, states};
}

function renderProposals() {
  const list = document.getElementById("proposal-list");
  const {cats, states} = activeFilters();
  const visible = PROPOSALS.filter(p => cats.has(p.category) && states.has(p.status));
  const counts = {pending: 0, accepted: 0, rejected: 0};
  PROPOSALS.forEach(p => counts[p.status]++);
  document.getElementById("prop-count").textContent =
    `(${counts.pending} 待审 / ${counts.accepted} 接受 / ${counts.rejected} 拒绝, 共 ${PROPOSALS.length})`;

  if (visible.length === 0) {
    list.innerHTML = '<p class="hint">（当前过滤条件下没有候选）</p>';
    return;
  }
  list.innerHTML = visible.map(p => {
    const dur = ((p.end_ms - p.start_ms)/1000).toFixed(1);
    const escapedComment = (p.user_comment || "").replace(/"/g, "&quot;");
    const savedMark = (p.user_comment || "").trim() ? "✓ 已存" : "";
    return `
    <div class="proposal ${p.category} ${p.status}" id="prop-${p.id}">
      <div class="prop-head">
        <span class="prop-cat ${p.category}">${p.category}</span>
        <span class="prop-time">orig@${fmt(p.start_ms/1000)}-${fmt(p.end_ms/1000)} (${dur}s)</span>
        <div class="prop-actions">
          <button class="play" onclick="playSpan(${p.start_ms - 1500}, ${p.end_ms + 1500})">▶ 试听 ±1.5s</button>
          ${p.status === "pending" ? `
            <button class="accept" onclick="acceptProposal('${p.id}')">✓ 接受</button>
            <button class="reject" onclick="rejectProposal('${p.id}')">✗ 拒绝</button>
          ` : `<span class="hint">${p.status}</span>`}
        </div>
      </div>
      <div class="prop-reason">${p.reason}</div>
      <div class="prop-comment-row">
        <label>备注</label>
        <input type="text" class="prop-comment" placeholder="给 agent 留言（可选）"
               value="${escapedComment}"
               oninput="commentDirty(event)"
               onblur="saveCommentNow('${p.id}', event)"
               onkeydown="if (event.key === 'Enter') saveCommentNow('${p.id}', event)" />
        <span class="prop-comment-saved-mark">${savedMark}</span>
      </div>
    </div>`;
  }).join("");
}

document.querySelectorAll('input[data-filter]').forEach(cb => cb.addEventListener("change", renderProposals));
document.querySelectorAll('.tab').forEach(t => {
  t.onclick = () => {
    document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.tab-body').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    document.getElementById(t.dataset.target).classList.add('active');
  };
});

const sentDiv = document.getElementById("sentence-list");
SENTS.forEach(s => {
  const ts = (s.start_ms/1000);
  const div = document.createElement("div");
  div.className = "sentence" + (s.speaker === "S2" ? " s2" : "");
  div.innerHTML = `<span class="speaker">${s.speaker}</span><span class="timestamp">${fmt(ts)}</span>${s.text}`;
  div.onclick = () => { audio.currentTime = ts; stopAtMs = null; audio.play(); };
  sentDiv.appendChild(div);
});

renderProposals();
</script>
</body></html>
""".replace("__SENTS__", sents_js).replace("__PROPS__", props_js)


def main():
    global _ep_dir
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep-dir", required=True)
    ap.add_argument("--port", type=int, default=5050)
    ap.add_argument("--no-serve", action="store_true", help="for tests")
    args = ap.parse_args()
    _ep_dir = Path(args.ep_dir).resolve()

    # Sanity checks
    audio_path = _ep_dir / "input" / "mixed_orig.wav"
    if not audio_path.exists():
        raise FileNotFoundError(
            f"{audio_path} not found. Run prepare_mixed_orig.py first."
        )
    sents_path = _ep_dir / "1_transcribe" / "sentences.json"
    if not sents_path.exists():
        raise FileNotFoundError(f"{sents_path} not found.")

    char_path = _ep_dir / "2_analysis" / "char_level.json"
    picks_path = _ep_dir / "2_analysis" / "agent_picks.json"
    if not char_path.exists() and not picks_path.exists():
        raise FileNotFoundError(
            f"No proposals to review. Run propose_char_level.py and/or have "
            f"agent write 2_analysis/agent_picks.json first."
        )

    print(f"原始音频审查 → http://127.0.0.1:{args.port}/")
    print(f"接受/拒绝实时写入 {_ep_dir}/3_review/delete_segments_edited.json")
    if not args.no_serve:
        app.run(host="127.0.0.1", port=args.port, debug=False)


if __name__ == "__main__":
    main()
