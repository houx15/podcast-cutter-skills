---
name: podcast-cut-剪播客
description: |
  将原始播客录音（单轨或双轨）自动转录、AI分析并裁剪为 cut.wav，供后期使用。
  触发词：剪播客、cut podcast、裁剪录音、处理录音
---

# /podcast-cut-剪播客

将录音转录、分析、人工审查后输出 cut.wav。整个流程分三步：
1. 转录（自动）
2. 分析（**你来做**）
3. 剪辑（自动）

## 前提条件

已运行 `/podcast-cut-安装`，且 `.env` 已配置：
- `VOLC_API_KEY`（或 `VOLC_APP_KEY` + `VOLC_ACCESS_KEY`）

## 三步流程

### 第一步：转录

```bash
python shared/scripts/run_pipeline.py \
  --ep-dir output/2026-05-08-ep01 \
  --track1 recordings/host.wav \
  --track2 recordings/guest.wav
```

流水线自动完成：
- 1.0 音频准备
- 1.05 轨道对齐（双轨时自动从 ASR 结果推断；可用 `--align clap` 或 `--align timestamp --t1 HH:MM:SS --t2 HH:MM:SS`）
- 1.2 Volcano ASR 转录
- 1.3 合并 + 1.4 分句
- 2.0 生成分析上下文（`analysis_context.md`）

结束时打印：**"Agent analysis required"**，并列出 `analysis_context.md` 路径。

---

### 第二步：你做分析（三轮）

流水线结束后，读取打印出的 `analysis_context.md`，按以下三轮完成分析。

#### 2.1 粗剪（内容级）

阅读 `analysis_context.md` 中的**剪辑规则**和**完整文本**，找出大段应删除的内容：
- 录前/录后闲聊（主题开始前的内容）
- 与主题完全无关的题外话（外卖、手机铃声、旁白）
- 明显技术故障（麦克风调试、重录片段）
- 时长超过3秒且无实质内容的停顿段

将结果写入 `output/EP_DIR/2_analysis/rough_cuts.json`：

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

规则优先级：保守原则优先，宁可少删不要误删（`confidence` < 0.7 的不放入）。

#### 2.2 精剪（词/句级）

在粗剪标记的区间之外，逐句检查仍需删除的细节：
- 高频口头禅（"嗯"、"啊"、"对对对"、"然后然后然后"）
- 同一观点30秒内用几乎相同措辞重复，删去重复
- "怎么说呢"、"就是那种"等开头无实质内容的句子

将结果写入 `output/EP_DIR/2_analysis/fine_cuts.json`：

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

**不删除**：情感停顿、自然思考停顿（<1.5s）、短时对话节奏词（"对"/"嗯嗯" <1s）、故意强调的重复。

#### 2.3 自审

回顾粗剪和精剪建议，检查：
- 有无误删（false positive）——不该删的被删了？
- 有无遗漏（false negative）——应该删的没删？

将结果写入 `output/EP_DIR/2_analysis/self_review.json`：

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
  "summary": "共审查23条建议，标记1条误删（30-75s），补充1条遗漏（180-182s）"
}
```

三个文件写完后，运行第三步。

---

### 第三步：生成审查界面 + 剪辑

```bash
python shared/scripts/run_pipeline.py --ep-dir output/2026-05-08-ep01 --resume
```

流水线自动：
- 生成 `review_enhanced.html`（含所有删除建议）
- 打印：启动审查服务器的命令，等待人工审查

人工审查：

```bash
python shared/scripts/review_server.py --ep-dir output/2026-05-08-ep01 --port 5050
# 浏览器打开打印出的 review_enhanced.html 路径
# 审查建议删除内容，点击 Export → 自动保存 delete_segments_edited.json
```

审查完成后再次运行：

```bash
python shared/scripts/run_pipeline.py --ep-dir output/2026-05-08-ep01 --resume
```

输出：`output/2026-05-08-ep01/4_cut/cut.wav`

## 重新运行与续传

每个阶段检测输出是否已存在，已完成的阶段自动跳过。在任意阶段中断后重新运行即可续传。

若需重跑分析，删除 `2_analysis/` 目录后重新运行流水线：

```bash
rm -rf output/EP_DIR/2_analysis
python shared/scripts/run_pipeline.py --ep-dir output/EP_DIR
```

## 常见错误

| 错误 | 原因 | 处理 |
|------|------|------|
| Volcano `45000001` | API key 无效 | 检查 `.env` 中的 Volcano 配置 |
| Volcano `45000132` | 音频超 512 MB | 先用 ffmpeg 转为 16kHz mono mp3 |
| uguu.se 上传失败 | 文件过大或网络问题 | 重试，或配置 TOS/S3 |
| `silence trap` | 输出几乎全静音 | 检查输入文件是否包含有效音频 |
| `Agent analysis not complete` | 三个分析 JSON 尚未写入 | 按第二步写完三个文件后再 `--resume` |
| `delete_segments_edited.json not found` | 审查未完成 | 在浏览器中点击 Export 后再 `--resume` |

## 各阶段详情

- [阶段1 转录](../../docs/剪播客/阶段1-转录.md)
- [阶段2 分析](../../docs/剪播客/阶段2-分析.md)
- [阶段3 审查](../../docs/剪播客/阶段3-审查.md)
- [阶段4 剪辑](../../docs/剪播客/阶段4-剪辑.md)
