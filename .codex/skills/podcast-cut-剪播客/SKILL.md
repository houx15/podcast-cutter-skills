---
name: podcast-cut-剪播客
description: 播客剪辑技能 — 三步：转录→分析→剪辑
---

# /podcast-cut-剪播客

## 前提

`.env` 已配置 `VOLC_API_KEY`（或 `VOLC_APP_KEY` + `VOLC_ACCESS_KEY`）。

## 三步流程

**第一步：转录（自动，~5-30分钟）**

```bash
python shared/scripts/run_pipeline.py \
  --ep-dir output/EP_ID \
  --track1 recordings/host.wav \
  [--track2 recordings/guest.wav] \
  [--align clap|timestamp] [--t1 HH:MM:SS --t2 HH:MM:SS]
```

结束时打印 `analysis_context.md` 路径，等待分析。

**第二步：你做分析（三轮）**

读取 `EP_DIR/2_analysis/analysis_context.md`，写入三个 JSON：

1. `rough_cuts.json` — 粗剪（内容级，录前闲聊、题外话、技术故障）
2. `fine_cuts.json` — 精剪（词级，口头禅、冗余解释）
3. `self_review.json` — 自审（检查误删和遗漏）

格式见 `analysis_context.md` 中的"输出格式要求"节。所有字段：`start_ms`、`end_ms`、`level`、`reason`、`source`、`confidence`。

**第三步：审查 + 剪辑（两次 --resume）**

```bash
# 第一次：生成 HTML 审查界面
python shared/scripts/run_pipeline.py --ep-dir output/EP_ID --resume

# 人工审查（浏览器）
python shared/scripts/review_server.py --ep-dir output/EP_ID --port 5050
# 点击 Export → 保存 delete_segments_edited.json

# 第二次：生成 cut.wav
python shared/scripts/run_pipeline.py --ep-dir output/EP_ID --resume
```

输出：`output/EP_ID/4_cut/cut.wav`

## 续传

所有阶段幂等。中断后重新运行同样命令即可续传。

## 常见错误

| 错误 | 处理 |
|------|------|
| Volcano `45000001` | 检查 VOLC_API_KEY |
| Volcano `45000132` | 音频超 512MB，先转码 |
| `Agent analysis not complete` | 写完三个 JSON 后再 --resume |
| `delete_segments_edited.json not found` | 在浏览器点击 Export |
