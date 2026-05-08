---
name: podcast-cut-剪播客
description: 播客剪辑技能 — 转录 → 分析 → 审查 → 剪辑（按步运行脚本）
---

# /podcast-cut-剪播客

按下面顺序逐步执行。每一步运行一个脚本，检查输出文件后再进入下一步。`EP_DIR = output/<EP_ID>/`。

## 前提

`.env` 配置 `VOLC_API_KEY`（或 `VOLC_APP_KEY` + `VOLC_ACCESS_KEY`）。

## 阶段 1：转录

```bash
# 1.0 准备音频
python shared/scripts/prepare_audio.py --ep-dir EP_DIR --track1 recordings/host.wav [--track2 recordings/guest.wav]

# 1.05 对齐（仅双轨。clap/timestamp 模式在 ASR 前；transcript 模式默认，在 ASR 后）
python shared/scripts/align_tracks.py --ep-dir EP_DIR [--clap | --t1 HH:MM:SS --t2 HH:MM:SS]

# 1.2 ASR（每个 track 一组 submit + query）
python shared/scripts/volcano_submit.py --audio-file EP_DIR/input/working_track1.wav --track-num 1 --ep-dir EP_DIR
python shared/scripts/volcano_query.py --track-num 1 --ep-dir EP_DIR

# 1.3 合并 + 1.4 分句
python shared/scripts/transcribe_merge.py --ep-dir EP_DIR
python shared/scripts/make_sentences.py --ep-dir EP_DIR
```

## 阶段 2：你做分析

读取 `EP_DIR/1_transcribe/sentences.json` + `shared/rules/editing/*.md` + `shared/rules/users/default/preferences.yaml`，写入：

- `EP_DIR/2_analysis/rough_cuts.json`（粗剪，内容级）
- `EP_DIR/2_analysis/fine_cuts.json`（精剪，词级）
- `EP_DIR/2_analysis/self_review.json`（自审）

字段：`start_ms`、`end_ms`、`level`（rough/fine）、`reason`、`source`（agent_rough/agent_fine/agent_self_review）、`confidence`。`self_review.json` 还含 `flags` 数组和 `summary` 字符串。

## 阶段 3：审查

```bash
python shared/scripts/generate_review_html.py --ep-dir EP_DIR
python shared/scripts/review_server.py --ep-dir EP_DIR --port 5050
```

告诉用户在浏览器审查，点击 Export 生成 `EP_DIR/3_review/delete_segments_edited.json`，然后告知"完毕"。

## 阶段 4：剪辑

```bash
python shared/scripts/cut_audio.py --ep-dir EP_DIR
python shared/scripts/trim_silences.py --ep-dir EP_DIR
```

输出：`EP_DIR/4_cut/cut.wav`

## 续传

每脚本输出唯一文件。删掉对应输出后重跑即可。

## 常见错误

| 错误 | 处理 |
|------|------|
| Volcano `45000001` | 检查 VOLC_API_KEY |
| Volcano `45000132` | 音频超 512MB，转码 |
| uguu.se 失败 | 配置 TOS/S3 |
| `silence trap` | 输入音频可能无效 |
