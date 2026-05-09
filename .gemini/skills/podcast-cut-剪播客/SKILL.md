---
name: podcast-cut-剪播客
description: |
  将原始播客录音（单轨或双轨）转录、AI分析、人工审查后裁剪为 cut.wav。
  触发词：剪播客、cut podcast、裁剪录音、处理录音
---

# /podcast-cut-剪播客

按下面顺序逐步执行。每一步运行一个脚本，检查输出文件后再进入下一步。所有路径以仓库根目录为基准。

## 时间轴隔离原则（**重要 — 这条不能违反**）

每条删除条目（delete）都活在它**被提议**时所处的时间轴里。**禁止**跨时间轴翻译再合并：
- **粗剪删除（coarse）**：以原始录音时间轴（words.json）为基准，写入 `3_review/delete_segments_edited.json`。`cut_audio.py` 把它们应用在原始 working_track*.wav 上 → coarse_cut.wav。
- **精修删除（fine）**：以 coarse_cut.wav 时间轴（cut_words.json）为基准，写入 `4_cut/fine_deletes.json`。`cut_audio_fine.py` 把它们直接应用在 coarse_cut.wav 上 → final_cut.wav。

不要把 fine 的接受结果翻译回原始时间轴再追加进 delete_segments_edited.json —— 多轮迭代后 keep_ranges 会变化，旧翻译会指向错位的内容（5–10 s drift）。每一轮的精修都是它那一层 cut.wav 的局部决定。

## 前提

`.env` 配置 `VOLC_API_KEY`（或 `VOLC_APP_KEY` + `VOLC_ACCESS_KEY`）。

## 工作目录

每期一个目录：`output/<EP_ID>/`，下面用 `EP_DIR` 表示。

---

## 阶段 1：转录

```bash
# 1.0 准备音频
python shared/scripts/prepare_audio.py --ep-dir EP_DIR --track1 recordings/host.wav [--track2 recordings/guest.wav]

# 1.05 双轨对齐（仅双轨需要）
# 三种模式：--clap | --t1 HH:MM:SS --t2 HH:MM:SS | （默认 transcript 推断，必须在 1.2 之后运行）
python shared/scripts/align_tracks.py --ep-dir EP_DIR [--clap | --t1 ... --t2 ...]

# 1.2 Volcano ASR（每个 track 一组 submit + query）
python shared/scripts/volcano_submit.py --audio-file EP_DIR/input/working_track1.wav --track-num 1 --ep-dir EP_DIR
python shared/scripts/volcano_query.py --track-num 1 --ep-dir EP_DIR
# track2 同理（双轨）

# 1.3 合并多轨词流
python shared/scripts/transcribe_merge.py --ep-dir EP_DIR

# 1.4 分句
python shared/scripts/make_sentences.py --ep-dir EP_DIR

# 1.6 预混合原始音频（给阶段 3 审查 UI 用）
python shared/scripts/prepare_mixed_orig.py --ep-dir EP_DIR
```

输出：`words.json` `sentences.json` `audio_meta.json` `mixed_orig.wav`。

---

## 阶段 2：粗剪分析

两个并行的步骤——一个机械、一个判断——产出阶段 3 审查 UI 的输入。

### 2.1 机械字符级扫描（脚本，确定性）

```bash
python shared/scripts/propose_char_level.py \
  --input-words EP_DIR/1_transcribe/words.json \
  --output EP_DIR/2_analysis/char_level.json \
  --label coarse
```

扫描 `words.json` 直接产出（每条时间戳来自 word 时间，**不**做 char→time ratio 映射）：
- `stutter` — 同字 3+ 次重复（保留最后一个）
- `filler-run` — 4+ 个连续语气词（嗯啊呃哦哈呀 / 嗯嗯 / 哈哈）
- `marker` — 自纠/打断短语（Sorry我 / 我在说啥 / 稍等我 / 对不起 / 等一下 / 我刚才说 …）
- `habit` — 就是/这个/那个 在 5 s 内出现 3+ 次（span ≤ 2.5 s）

输出：`EP_DIR/2_analysis/char_level.json`，schema：
```json
{"proposals": [
  {"id": "coarse-0001", "start_ms": ..., "end_ms": ...,
   "category": "stutter|filler-run|marker|habit",
   "speaker": "S1|S2", "reason": "...", "confidence": 0.0..1.0,
   "status": "pending"}
]}
```

### 2.2 内容级判断（**你来做**）

读取 `EP_DIR/1_transcribe/sentences.json` + `EP_DIR/1_transcribe/words.json` + `shared/rules/editing/*.md` + `shared/rules/users/default/preferences.yaml`，找：
- **region** — 录前/录后闲聊、设备故障重录段、明显跑题段、嘉宾打断（"耳机掉了"）等
- **editorial** — 同一观点 30 s 内复述两次、三段式重复、举例铺垫过度、即兴起的备选标题列举等

每条 **必须** 用 words.json 的真实词时间戳作为 start_ms / end_ms（找到那段文字在 joined-words 里的字符位置 → 用 word_index_at_char 反查到具体词的时间）。**禁止** 用 sentence.text 的字符比例估时间——sentence.text 在 50 字符截断且与 word_idx_start/end 不匹配，比例映射会跑偏 5–10 s。

写入 `EP_DIR/2_analysis/agent_picks.json`，同 schema：
```json
{"proposals": [
  {"id": "agent-0001", "start_ms": ..., "end_ms": ...,
   "category": "region|editorial",
   "speaker": "S1|S2|both", "reason": "...", "confidence": 0.7..0.99,
   "source": "agent_rough|agent_self_review", "status": "pending"}
]}
```

保守原则：confidence < 0.7 不放入。宁可少删不要误删。

---

## 阶段 3：粗审（人工，第一道关卡）

```bash
python shared/scripts/review_server_v2.py --ep-dir EP_DIR --port 5050
```

打开 `http://127.0.0.1:5050/`。UI 加载 `2_analysis/char_level.json` + `2_analysis/agent_picks.json` 两份候选。每条可以：
- ▶ 试听 ±1.5 s 上下文（音频是 `input/mixed_orig.wav`）
- ✓ 接受 / ✗ 拒绝
- 备注（自动保存）

接受/拒绝实时写回源文件的 `status` 字段，并重建 `EP_DIR/3_review/delete_segments_edited.json`（按当前已接受的全部条目）。审完关闭服务器。

> 重审同一份提议？直接刷新页面，状态已经存在 char_level.json / agent_picks.json 里了。
> 想推翻重来？删掉 `3_review/delete_segments_edited.json` 和把 `status` 全置回 pending，再开服务器。

---

## 阶段 4：粗剪 + 精修（双轨剪辑流）

### 4.0 粗剪音频（应用阶段 3 审查后的删除）

```bash
python shared/scripts/cut_audio.py --ep-dir EP_DIR
python shared/scripts/trim_silences.py --ep-dir EP_DIR
```

输出：`EP_DIR/4_cut/cut.wav`（粗剪版）。双轨会先按 `track_offsets_ms` 混进同一时间轴。

### 4.2 重新转录粗剪后的 cut.wav

```bash
python shared/scripts/re_transcribe_cut.py --ep-dir EP_DIR
```

输出：`EP_DIR/4_cut/cut_words.json` + `cut_sentences.json`（**cut 时间轴**）。

### 4.3 提精修建议（机械 + 判断）

```bash
# 机械字符级：以 cut_words.json 为输入
python shared/scripts/propose_char_level.py \
  --input-words EP_DIR/4_cut/cut_words.json \
  --output EP_DIR/4_cut/fine_proposals.json \
  --label fine
```

然后 **你（agent）** 读 `cut_sentences.json`，把机械扫描漏掉的（节奏问题、重复段落、跑题段、能量低谷）追加到 `EP_DIR/4_cut/fine_proposals.json` 的 `proposals` 数组（`category: "editorial"`）。time 字段用 `cut_words.json` 真实词时间。

### 4.4 精修浏览器审查（第二道关卡）

```bash
python shared/scripts/cut_review.py --ep-dir EP_DIR --port 5070
```

打开 `http://127.0.0.1:5070/`。UI 加载 `4_cut/fine_proposals.json` + `4_cut/cut_sentences.json`，音频是 `4_cut/coarse_cut.wav`（或 legacy 的 `cut.wav`）。每条 `▶ 试听 ±1.5 s`、`✓ 接受` / `✗ 拒绝` / 备注。也可以用 <kbd>S</kbd>/<kbd>E</kbd>/<kbd>Enter</kbd> 自己手动加。

接受/拒绝实时写入 `4_cut/fine_deletes.json`，**保持 cut 时间轴**（cut_start_ms / cut_end_ms）。**不**翻译成原始时间轴。审完关闭。

### 4.5 应用精修删除，输出最终 cut.wav

```bash
python shared/scripts/cut_audio_fine.py --ep-dir EP_DIR
```

读取 `4_cut/coarse_cut.wav` + `4_cut/fine_deletes.json`，直接在 cut 时间轴里删除并拼接 → `4_cut/final_cut.wav`。**不**经过原始时间轴翻译，也**不**重跑 cut_audio.py（那一步会重新从原始录音开始混合）。

> 想再迭代一轮？再跑 4.2 → 4.3 → 4.4 → 4.5。每轮都从更干净的 cut.wav 出发，建议会越来越精细。但每轮都是独立的 cut 时间轴决定，不会污染原始 deletes。

---

## 阶段 5：金句切片

阶段 4 定稿之后、shownotes 之前。**你（agent）** 读 `cut_sentences.json` 给每个说话人各挑 5–10 条传播力强的金句，写成 `EP_DIR/6_clips/picks.json`：

```json
{"picks": [
  {"speaker": "S1", "cut_start_ms": 488000, "cut_end_ms": 504000,
   "label": "生产力通货膨胀的年代", "text": "..."}
]}
```

```bash
python shared/scripts/extract_key_quotes.py --ep-dir EP_DIR
```

输出：`EP_DIR/6_clips/{S1,S2}/NN-{label}.wav` + `manifest.json`。

---

## 阶段 6：节目说明

```bash
# 6.0 把句子重映射到 cut.wav 时间轴
python shared/scripts/cut_transcript.py --ep-dir EP_DIR
```

### 6.1 撰写 shownotes（**你来做**）

读 `EP_DIR/5_shownotes/cut_transcript.json` + `shared/rules/users/default/shownotes_example.md`（用户的样本/模板），按样本的章节顺序与口吻写 `EP_DIR/5_shownotes/shownotes.md`。

要点：
- 时间轴使用 cut 时间轴（不是原始录音时间）
- Highlights 是原话提炼，名词解释只覆盖本期出现的术语
- 摘要段要给出"本期讲了什么"和"为什么值得听"两层意思

---

## 续传

每脚本输出唯一文件。删掉对应输出后重跑即可。

```bash
# 重跑分析（保留转录）
rm -rf EP_DIR/2_analysis EP_DIR/3_review EP_DIR/4_cut

# 重跑切割（保留分析）
rm -rf EP_DIR/4_cut
```

## 常见错误

| 错误 | 原因 | 处理 |
|------|------|------|
| Volcano `45000001` | API key 无效 | 检查 `.env` 中的 `VOLC_API_KEY` |
| Volcano `45000132` | 音频超 512 MB | 先用 ffmpeg 转为 16 kHz mono mp3 |
| uguu.se 上传失败 | 文件过大或网络问题 | 重试，或配置 TOS/S3 |
| `silence trap` | 输出几乎全静音 | 检查输入文件是否包含有效音频 |
| 删除条目落在错误时间 | propose_cuts.py 旧脚本（已废弃，用 propose_char_level.py 代替）；或跨时间轴误翻译（参考时间轴隔离原则） | 用 `propose_char_level.py`；不要把 fine 翻成 orig 再合并 |

## 各阶段详情

- [阶段1 转录](../../docs/剪播客/阶段1-转录.md)
- [阶段2 分析](../../docs/剪播客/阶段2-分析.md)
- [阶段3 审查](../../docs/剪播客/阶段3-审查.md)
- [阶段4 剪辑](../../docs/剪播客/阶段4-剪辑.md)
