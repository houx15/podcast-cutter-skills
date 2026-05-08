---
name: podcast-cut-剪播客
description: |
  将原始播客录音（单轨或双轨）转录、AI分析、人工审查后裁剪为 cut.wav。
  触发词：剪播客、cut podcast、裁剪录音、处理录音
---

# /podcast-cut-剪播客

按下面顺序逐步执行。每一步运行一个脚本，检查输出文件存在后再进入下一步。所有路径以仓库根目录为基准。

## 前提条件

`.env` 已配置：
- `VOLC_API_KEY`（或 `VOLC_APP_KEY` + `VOLC_ACCESS_KEY`）

可选：`TOS_*` 或 `S3_*`（音频 > 50MB 时；否则回退到 uguu.se）

## 工作目录

每一期录音用一个目录：`output/<EP_ID>/`，例如 `output/2026-05-08-ep01/`。下面用 `EP_DIR` 表示。

---

## 阶段 1：转录

### 1.0 准备音频

```bash
python shared/scripts/prepare_audio.py \
  --ep-dir EP_DIR \
  --track1 recordings/host.wav \
  [--track2 recordings/guest.wav]
```

输出：`EP_DIR/input/working_track*.wav`、`EP_DIR/input/audio_meta.json`

### 1.05 双轨对齐（仅双轨需要，单轨跳过）

三种模式，按可用信息选择：

```bash
# 拍掌模式：录音前 30s 内有同步拍掌
python shared/scripts/align_tracks.py --ep-dir EP_DIR --clap

# 时间戳模式：知道每轨的录制开始墙钟时间
python shared/scripts/align_tracks.py --ep-dir EP_DIR --t1 10:00:00 --t2 10:00:03

# 文字推断模式（默认，必须在 ASR 完成后运行）
python shared/scripts/align_tracks.py --ep-dir EP_DIR
```

- **拍掌/时间戳模式**：在 1.2 ASR 之前运行
- **文字推断模式**：在 1.2 ASR 完成后、1.3 合并之前运行

输出：`EP_DIR/input/audio_meta.json` 中新增 `track_offsets_ms`

### 1.2 Volcano ASR（每个 track 一组）

```bash
# Track 1
python shared/scripts/volcano_submit.py --audio-file EP_DIR/input/working_track1.wav --track-num 1 --ep-dir EP_DIR
python shared/scripts/volcano_query.py --track-num 1 --ep-dir EP_DIR

# Track 2（如有）
python shared/scripts/volcano_submit.py --audio-file EP_DIR/input/working_track2.wav --track-num 2 --ep-dir EP_DIR
python shared/scripts/volcano_query.py --track-num 2 --ep-dir EP_DIR
```

输出：`EP_DIR/1_transcribe/task_id_track*.txt`、`EP_DIR/1_transcribe/volcano_raw_track*.json`

注：`volcano_submit.py` 自动上传音频（TOS → S3 → uguu.se 链式回退）。

### 1.3 合并多轨词流

如果是文字推断对齐，**先**运行 1.05 文字推断模式，再运行这一步。

```bash
python shared/scripts/transcribe_merge.py --ep-dir EP_DIR
```

输出：`EP_DIR/1_transcribe/words.json`

### 1.4 分句

```bash
python shared/scripts/make_sentences.py --ep-dir EP_DIR
```

输出：`EP_DIR/1_transcribe/sentences.json`

---

## 阶段 2：分析（**你来做**）

不调用任何脚本。读取以下文件，自己进行分析：

**输入**：
- `EP_DIR/1_transcribe/sentences.json` — 完整句子列表（带词索引、时间戳、说话人）
- `shared/rules/editing/*.md` — 剪辑规则（核心原则等）
- `shared/rules/users/default/preferences.yaml` — 用户偏好（保守度、最大删除比等）

按以下三轮，依次写入三个 JSON 文件：

### 2.1 粗剪（内容级）→ `EP_DIR/2_analysis/rough_cuts.json`

阅读规则和完整文本，找出大段应删除的内容：录前/录后闲聊、与主题完全无关的题外话、明显技术故障（麦克风调试、重录）、超过 3 秒且无实质内容的停顿。

格式：

```json
{
  "deletes": [
    {
      "start_ms": 0,
      "end_ms": 45000,
      "level": "rough",
      "reason": "录前闲聊：测麦克风、寒暄",
      "source": "agent_rough",
      "confidence": 0.95
    }
  ]
}
```

保守原则：宁可少删不要误删（confidence < 0.7 的不放入）。

### 2.2 精剪（词/句级）→ `EP_DIR/2_analysis/fine_cuts.json`

在粗剪标记的区间之外，逐句检查：高频口头禅（"嗯"、"啊"、"对对对"、"然后然后然后"）、30 秒内几乎相同措辞的重复、"怎么说呢"等开头无实质内容的句子。

不删除：情感停顿、自然思考停顿（<1.5s）、短时对话节奏词（"对"/"嗯嗯" <1s）、故意强调的重复。

格式：

```json
{
  "deletes": [
    {
      "start_ms": 12340,
      "end_ms": 12890,
      "level": "fine",
      "reason": "口头禅：句首嗯",
      "source": "agent_fine",
      "confidence": 0.85
    }
  ]
}
```

### 2.3 自审 → `EP_DIR/2_analysis/self_review.json`

回顾 2.1 + 2.2 的建议，检查误删（false positive）和遗漏（false negative）：

```json
{
  "deletes": [
    {
      "start_ms": 180000,
      "end_ms": 182000,
      "level": "fine",
      "reason": "遗漏：纯填充句无实质内容",
      "source": "agent_self_review",
      "confidence": 0.8
    }
  ],
  "flags": [
    {
      "start_ms": 30000,
      "end_ms": 75000,
      "flag": "false_positive",
      "reason": "误判为题外话，实为对主题的铺垫"
    }
  ],
  "summary": "共审查 23 条建议，标记 1 条误删，补充 1 条遗漏"
}
```

---

## 阶段 3：人工审查

### 3.0 生成审查 HTML

```bash
python shared/scripts/generate_review_html.py --ep-dir EP_DIR
```

输出：`EP_DIR/3_review/review_enhanced.html`

### 3.1 启动审查服务器

```bash
python shared/scripts/review_server.py --ep-dir EP_DIR --port 5050
```

告诉用户：在浏览器打开打印出的 review_enhanced.html 路径，审查删除建议（保留 / 编辑 / 拒绝 / 新增），完成后点击 Export。

等待用户告知"审查完毕"，或检查 `EP_DIR/3_review/delete_segments_edited.json` 文件是否已生成。

---

## 阶段 4：剪辑

### 4.0 切割音频

```bash
python shared/scripts/cut_audio.py --ep-dir EP_DIR
```

输出：`EP_DIR/4_cut/cut.wav`（含 25ms 交叉淡入淡出）

### 4.1 修剪头尾静音

```bash
python shared/scripts/trim_silences.py --ep-dir EP_DIR
```

最终输出：`EP_DIR/4_cut/cut.wav`（已修剪头尾）

---

## 续传与幂等

每个脚本输出唯一文件。如需重跑某阶段，先删掉对应输出文件再重新运行。例如：

```bash
# 重跑分析（保留转录结果）
rm -rf EP_DIR/2_analysis EP_DIR/3_review EP_DIR/4_cut

# 重跑切割（保留所有分析）
rm -rf EP_DIR/4_cut
```

中断后续传：直接从未完成的步骤继续运行，前面的脚本不会重做（因为输出已存在，由你判断跳过）。

## 常见错误

| 错误 | 原因 | 处理 |
|------|------|------|
| Volcano `45000001` | API key 无效 | 检查 `.env` 中的 `VOLC_API_KEY` |
| Volcano `45000132` | 音频超 512 MB | 先用 ffmpeg 转为 16kHz mono mp3 |
| uguu.se 上传失败 | 文件过大或网络问题 | 重试，或配置 TOS/S3 |
| `silence trap` | 输出几乎全静音 | 检查输入文件是否包含有效音频 |

## 各阶段详情

- [阶段1 转录](../../docs/剪播客/阶段1-转录.md)
- [阶段2 分析](../../docs/剪播客/阶段2-分析.md)
- [阶段3 审查](../../docs/剪播客/阶段3-审查.md)
- [阶段4 剪辑](../../docs/剪播客/阶段4-剪辑.md)
