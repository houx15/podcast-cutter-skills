#!/usr/bin/env python3
"""Stage 4.4: browser-based fine review of coarse_cut.wav.

Plays the post-coarse-cut audio with sentence list (cut timeline). User
accepts or rejects each proposal (or marks new ones manually), and accepted
deletes are written to `4_cut/fine_deletes.json` with `cut_start_ms` /
`cut_end_ms` in the COARSE_CUT.wav timeline. **No cut→orig translation.**

`cut_audio_fine.py` then applies fine_deletes.json directly to coarse_cut.wav
to produce final_cut.wav. Re-running iterations doesn't accumulate drift.

This is the timeline-isolation refactor of the old cut_review.py which
translated cut→orig and merged into delete_segments_edited.json (broken,
caused 5-10s drift across iterations — see memory/feedback_timeline_isolation.md).
"""
from __future__ import annotations
import argparse, json
from pathlib import Path

from flask import Flask, jsonify, request, send_file

app = Flask(__name__)
_ep_dir: Path = Path(".")


def _audio_path() -> Path:
    """coarse_cut.wav (preferred) or cut.wav (legacy fallback)."""
    coarse = _ep_dir / "4_cut" / "coarse_cut.wav"
    if coarse.exists():
        return coarse
    return _ep_dir / "4_cut" / "cut.wav"


def _proposals_path() -> Path:
    """4_cut/fine_proposals.json (preferred) or 3_review/proposed_cuts.json (legacy)."""
    new = _ep_dir / "4_cut" / "fine_proposals.json"
    if new.exists():
        return new
    return _ep_dir / "3_review" / "proposed_cuts.json"


def _sentences_path() -> Path:
    new = _ep_dir / "4_cut" / "cut_sentences.json"
    if new.exists():
        return new
    return _ep_dir / "5_shownotes" / "cut_transcript.json"


def _fine_deletes_path() -> Path:
    return _ep_dir / "4_cut" / "fine_deletes.json"


def _load_proposals() -> list[dict]:
    p = _proposals_path()
    if not p.exists():
        return []
    data = json.loads(p.read_text())
    return data.get("proposals", [])


def _save_proposal_status(pid: str, status: str, comment: str) -> None:
    p = _proposals_path()
    if not p.exists():
        return
    data = json.loads(p.read_text())
    for prop in data.get("proposals", []):
        if prop.get("id") == pid:
            prop["status"] = status
            if comment.strip():
                prop["user_comment"] = comment.strip()
            elif "user_comment" in prop:
                del prop["user_comment"]
            break
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def _proposal_cut_span(p: dict) -> tuple[int, int]:
    """Accept either {cut_start_ms, cut_end_ms} (legacy fine schema) or
    {start_ms, end_ms} (general schema). Always cut.wav timeline."""
    if "cut_start_ms" in p:
        return int(p["cut_start_ms"]), int(p["cut_end_ms"])
    return int(p["start_ms"]), int(p["end_ms"])


def _rebuild_fine_deletes() -> None:
    """Reconstruct 4_cut/fine_deletes.json from accepted proposals + manual cuts."""
    proposals = _load_proposals()
    deletes = []
    for p in proposals:
        if p.get("status") != "accepted":
            continue
        cs, ce = _proposal_cut_span(p)
        reason = f"[{p.get('category', '?')}] {p.get('reason', '')}"
        if p.get("user_comment", "").strip():
            reason += f" | 用户备注: {p['user_comment'].strip()}"
        deletes.append({
            "cut_start_ms": cs,
            "cut_end_ms": ce,
            "category": p.get("category", "?"),
            "reason": reason,
            "source": "proposal_accepted",
            "confidence": p.get("confidence", 1.0),
            "user_action": "kept",
        })

    # Preserve any manual deletes (added via /add-cut), stored separately
    manual_path = _ep_dir / "4_cut" / "fine_deletes_manual.json"
    if manual_path.exists():
        manual = json.loads(manual_path.read_text()).get("deletes", [])
        deletes.extend(manual)

    deletes.sort(key=lambda d: d["cut_start_ms"])
    out_path = _fine_deletes_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(
        {"deletes": deletes, "user_notes": "", "feedback_for_learning": []},
        ensure_ascii=False, indent=2,
    ))


@app.route("/")
def index():
    sents_path = _sentences_path()
    sents = json.loads(sents_path.read_text())["sentences"] if sents_path.exists() else []
    proposals = _load_proposals()
    return _render_html(sents, proposals)


@app.route("/audio")
def audio():
    return send_file(str(_audio_path()), mimetype="audio/wav", conditional=True)


@app.route("/accept-proposal", methods=["POST"])
def accept_proposal():
    body = request.get_json() or {}
    pid = body["id"]
    comment = body.get("comment", "")
    _save_proposal_status(pid, "accepted", comment)
    _rebuild_fine_deletes()
    return jsonify({"ok": True})


@app.route("/reject-proposal", methods=["POST"])
def reject_proposal():
    body = request.get_json() or {}
    pid = body["id"]
    comment = body.get("comment", "")
    _save_proposal_status(pid, "rejected", comment)
    _rebuild_fine_deletes()
    return jsonify({"ok": True})


@app.route("/save-comment", methods=["POST"])
def save_comment():
    body = request.get_json() or {}
    pid = body["id"]
    comment = body.get("comment", "")
    proposals = _load_proposals()
    p = next((x for x in proposals if x.get("id") == pid), None)
    if p:
        _save_proposal_status(pid, p.get("status", "pending"), comment)
    return jsonify({"ok": True})


@app.route("/add-cut", methods=["POST"])
def add_cut():
    """Manual cut marked by S/E/Enter — stored in cut timeline directly."""
    body = request.get_json() or {}
    cs = int(body["cut_start_ms"])
    ce = int(body["cut_end_ms"])
    reason = body.get("reason", "manual")
    if ce <= cs:
        return jsonify({"ok": False, "error": "end <= start"}), 400

    manual_path = _ep_dir / "4_cut" / "fine_deletes_manual.json"
    if manual_path.exists():
        data = json.loads(manual_path.read_text())
    else:
        data = {"deletes": []}
    data["deletes"].append({
        "cut_start_ms": cs,
        "cut_end_ms": ce,
        "category": "manual",
        "reason": f"[manual] {reason}",
        "source": "human_review",
        "confidence": 1.0,
        "user_action": "kept",
    })
    data["deletes"].sort(key=lambda d: d["cut_start_ms"])
    manual_path.parent.mkdir(parents=True, exist_ok=True)
    manual_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    _rebuild_fine_deletes()
    return jsonify({"ok": True, "cut_start_ms": cs, "cut_end_ms": ce})


def _render_html(sents: list, proposals: list) -> str:
    sents_js = json.dumps(sents, ensure_ascii=False)
    props_js = json.dumps(proposals, ensure_ascii=False)
    return r"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>coarse_cut.wav 二次审查 (Stage 4.4)</title>
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
.cut-list { background: #fff8e0; padding: 0.6em 1em; border-radius: 4px; font-size: 0.9em; }
.cut-item { padding: 2px 0; font-family: monospace; }

.tabs { display: flex; gap: 0; margin-top: 1em; border-bottom: 2px solid #ddd; }
.tab { padding: 8px 16px; cursor: pointer; border: 1px solid #ddd; border-bottom: none; background: #f5f5f5; }
.tab.active { background: white; font-weight: bold; border-bottom: 2px solid white; margin-bottom: -2px; }
.tab-body { display: none; }
.tab-body.active { display: block; }

.proposal { padding: 8px 12px; border-left: 4px solid #aaa; margin: 8px 0; background: #fafafa; border-radius: 0 4px 4px 0; }
.proposal.silence { border-left-color: #69c; }
.proposal.stutter { border-left-color: #a36; }
.proposal.filler-run { border-left-color: #c90; }
.proposal.marker { border-left-color: #c66; }
.proposal.habit { border-left-color: #cb6; }
.proposal.editorial { border-left-color: #6a3; }
.proposal.accepted { opacity: 0.5; background: #e8f5e8; border-left-color: #2a2; }
.proposal.rejected { opacity: 0.5; background: #f5e8e8; border-left-color: #a22; text-decoration: line-through; }
.prop-head { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.prop-cat { font-size: 0.75em; padding: 2px 6px; border-radius: 3px; background: #eee; font-weight: bold; }
.prop-cat.silence { background: #cde; }
.prop-cat.stutter { background: #fcd; }
.prop-cat.filler-run { background: #fec; }
.prop-cat.marker { background: #fcc; }
.prop-cat.habit { background: #fec; }
.prop-cat.editorial { background: #cea; }
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
kbd { background: #eee; padding: 2px 4px; border-radius: 2px; font-family: monospace; }
.hint { color: #666; font-size: 0.85em; }
.summary { font-size: 0.85em; color: #666; }
</style>
</head>
<body>
<h1>coarse_cut.wav 二次审查 <span class="hint">(Stage 4.4 — 接受/拒绝写入 4_cut/fine_deletes.json，cut 时间轴；之后跑 cut_audio_fine.py)</span></h1>

<div class="player">
<audio id="audio" controls preload="metadata"><source src="/audio" type="audio/wav"></audio>
<div class="controls">
  <span>当前: <span id="cur-time">00:00.0</span></span>
  <button onclick="markStart()">[ 起点 (S)</button>
  <button onclick="markEnd()">] 终点 (E)</button>
  <span>选择: <span id="range">—</span></span>
  <button onclick="addCut()">+ 加入 (Enter)</button>
  <span class="hint">键盘: <kbd>S</kbd>起点 / <kbd>E</kbd>终点 / <kbd>Enter</kbd>加入</span>
</div>
</div>

<div class="tabs">
  <div class="tab active" data-target="proposals">候选删除 <span id="prop-count" class="summary"></span></div>
  <div class="tab" data-target="manual">手动加入 <span id="manual-count" class="summary"></span></div>
  <div class="tab" data-target="sentences">完整文本</div>
</div>

<div id="proposals" class="tab-body active">
  <div class="hint">点 <b>▶ 试听</b> 听 ±1.5 s 上下文，<b>✓ 接受</b> 或 <b>✗ 拒绝</b>。也可以用 S/E/Enter 自己加。</div>
  <div class="controls">
    <span>类别:</span>
    <label><input type="checkbox" data-filter="silence" checked> 静音</label>
    <label><input type="checkbox" data-filter="stutter" checked> 口吃</label>
    <label><input type="checkbox" data-filter="filler-run" checked> 语气词连</label>
    <label><input type="checkbox" data-filter="marker" checked> 自纠/打断</label>
    <label><input type="checkbox" data-filter="habit" checked> 口癖</label>
    <label><input type="checkbox" data-filter="editorial" checked> 编辑判断</label>
  </div>
  <div class="controls">
    <span>状态:</span>
    <label><input type="checkbox" data-filter="pending" checked> 待审</label>
    <label><input type="checkbox" data-filter="accepted"> 已接受</label>
    <label><input type="checkbox" data-filter="rejected"> 已拒绝</label>
  </div>
  <div id="proposal-list"></div>
</div>

<div id="manual" class="tab-body">
  <div id="manual-list" class="cut-list">还没有手动加入。播放音频，按 <kbd>S</kbd>/<kbd>E</kbd>/<kbd>Enter</kbd> 加入。</div>
</div>

<div id="sentences" class="tab-body">
  <div id="sentence-list"></div>
</div>

<script>
const SENTS = __SENTS__;
const PROPOSALS = __PROPS__;
const audio = document.getElementById("audio");
const cuts = [];
let cutStart = null, cutEnd = null;

function fmt(s) {
  const m = Math.floor(s/60), x = (s % 60).toFixed(1);
  return String(m).padStart(2,'0') + ':' + String(x).padStart(4,'0');
}
audio.addEventListener("timeupdate", () => {
  document.getElementById("cur-time").textContent = fmt(audio.currentTime);
});
function markStart() {
  cutStart = audio.currentTime;
  document.getElementById("range").textContent = fmt(cutStart) + " — ?";
}
function markEnd() {
  cutEnd = audio.currentTime;
  document.getElementById("range").textContent = fmt(cutStart || 0) + " — " + fmt(cutEnd);
}
function addCut() {
  if (cutStart == null || cutEnd == null || cutEnd <= cutStart) {
    alert("请先设起点和终点（终点必须在起点之后）"); return;
  }
  const reason = prompt("理由（可空）：", "听感不好") || "";
  fetch("/add-cut", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({cut_start_ms: Math.round(cutStart*1000), cut_end_ms: Math.round(cutEnd*1000), reason})
  }).then(r => r.json()).then(data => {
    if (!data.ok) { alert("写入失败: " + (data.error || "未知")); return; }
    cuts.push({cs: cutStart, ce: cutEnd, reason});
    renderManualList();
    cutStart = cutEnd = null;
    document.getElementById("range").textContent = "—";
  });
}
function renderManualList() {
  const div = document.getElementById("manual-list");
  document.getElementById("manual-count").textContent = cuts.length ? `(${cuts.length})` : "";
  if (cuts.length === 0) {
    div.innerHTML = '还没有手动加入。播放音频，按 <kbd>S</kbd>/<kbd>E</kbd>/<kbd>Enter</kbd> 加入。';
    return;
  }
  div.innerHTML = `<b>已加入（${cuts.length}）：</b><br>` +
    cuts.map(c => `<div class="cut-item">cut@${fmt(c.cs)}-${fmt(c.ce)}  ${c.reason}</div>`).join("");
}

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

function spanOf(p) {
  return p.cut_start_ms !== undefined
    ? [p.cut_start_ms, p.cut_end_ms]
    : [p.start_ms, p.end_ms];
}
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
  }).then(r => r.json()).then(() => {
    p.status = "accepted"; p.user_comment = commentOf(p.id); renderProposals();
  });
}
function rejectProposal(pid) {
  const p = findProposal(pid);
  if (!p) return;
  fetch("/reject-proposal", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({id: p.id, comment: commentOf(p.id)})
  }).then(r => r.json()).then(() => {
    p.status = "rejected"; p.user_comment = commentOf(p.id); renderProposals();
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

const CATEGORY_FILTERS = ["silence", "stutter", "filler-run", "marker", "habit", "editorial"];
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
    const [cs, ce] = spanOf(p);
    const dur = ((ce - cs)/1000).toFixed(1);
    const escapedComment = (p.user_comment || "").replace(/"/g, "&quot;");
    const savedMark = (p.user_comment || "").trim() ? "✓ 已存" : "";
    return `
    <div class="proposal ${p.category} ${p.status}" id="prop-${p.id}">
      <div class="prop-head">
        <span class="prop-cat ${p.category}">${p.category}</span>
        <span class="prop-time">cut@${fmt(cs/1000)}-${fmt(ce/1000)} (${dur}s)</span>
        <div class="prop-actions">
          <button class="play" onclick="playSpan(${cs - 1500}, ${ce + 1500})">▶ 试听 ±1.5s</button>
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

document.addEventListener("keydown", e => {
  if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
  if (e.key === "s" || e.key === "S") markStart();
  else if (e.key === "e" || e.key === "E") markEnd();
  else if (e.key === "Enter") addCut();
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
renderManualList();
</script>
</body></html>
""".replace("__SENTS__", sents_js).replace("__PROPS__", props_js)


def main():
    global _ep_dir
    ap = argparse.ArgumentParser()
    ap.add_argument("--ep-dir", required=True)
    ap.add_argument("--port", type=int, default=5070)
    ap.add_argument("--no-serve", action="store_true", help="for tests")
    args = ap.parse_args()
    _ep_dir = Path(args.ep_dir).resolve()

    if not _audio_path().exists():
        raise FileNotFoundError(
            f"No coarse_cut.wav or cut.wav found in {_ep_dir}/4_cut/"
        )

    print(f"coarse_cut.wav 二次审查 → http://127.0.0.1:{args.port}/")
    print(f"接受/拒绝写入 {_fine_deletes_path()} (cut 时间轴)")
    print("审完后跑：cut_audio_fine.py 应用精修删除 → final_cut.wav")
    if not args.no_serve:
        app.run(host="127.0.0.1", port=args.port, debug=False)


if __name__ == "__main__":
    main()
