---
name: podcast-cut-剪播客
description: |
  将原始播客录音（单轨或双轨）自动转录、LLM分析并裁剪为 cut.wav，供后期使用。
  触发词：剪播客、cut podcast、裁剪录音、处理录音
---

# /podcast-cut-剪播客

将录音转录、AI分析、人工审查后输出 cut.wav。

## 前提条件

已运行 `/podcast-cut-安装`，且 `.env` 已配置：
- `VOLC_API_KEY`（或 `VOLC_APP_KEY` + `VOLC_ACCESS_KEY`）
- `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`

## 用法（两条命令）

**第一步：运行流水线（转录 + 分析，约需 5–20 分钟）**

```bash
python shared/scripts/run_pipeline.py \
  --ep-dir output/2026-05-08-ep01 \
  --track1 recordings/host.wav \
  --track2 recordings/guest.wav
```

流水线自动完成：
- 1.0 音频准备
- 1.05 轨道对齐（双轨自动推断；可用 `--align clap` 或 `--align timestamp --t1 HH:MM:SS --t2 HH:MM:SS`）
- 1.2 Volcano ASR 转录（含上传）
- 1.3 合并 + 1.4 分句
- 2.1 粗剪 + 2.2 精剪 + 2.3 自审
- 3.0 生成审查 HTML

完成后打印审查文件路径和 review_server 启动命令，等待人工审查。

**人工审查**

```bash
python shared/scripts/review_server.py --ep-dir output/2026-05-08-ep01 --port 5050
# 浏览器打开打印出的 review_enhanced.html 路径
# 审查建议删除内容，点击 Export → 自动保存 delete_segments_edited.json
```

**第二步：完成剪辑**

```bash
python shared/scripts/run_pipeline.py --ep-dir output/2026-05-08-ep01 --resume
```

输出：`output/2026-05-08-ep01/4_cut/cut.wav`

## 重新运行与续传

每个阶段检测输出是否已存在，已完成的阶段自动跳过。在任意阶段中断后重新运行两条命令即可续传。

## 常见错误

| 错误 | 原因 | 处理 |
|------|------|------|
| Volcano `45000001` | API key 无效 | 检查 `.env` 中的 Volcano 配置 |
| Volcano `45000132` | 音频超 512 MB | 先用 ffmpeg 转为 16kHz mono mp3 |
| uguu.se 上传失败 | 文件过大或网络问题 | 重试，或配置 TOS/S3 |
| `silence trap` | 输出几乎全静音 | 检查输入文件是否包含有效音频 |
| `delete_segments_edited.json not found` | 审查未完成 | 在浏览器中点击 Export 后再 `--resume` |

## 各阶段详情

- [阶段1 转录](../../docs/剪播客/阶段1-转录.md)
- [阶段2 分析](../../docs/剪播客/阶段2-分析.md)
- [阶段3 审查](../../docs/剪播客/阶段3-审查.md)
- [阶段4 剪辑](../../docs/剪播客/阶段4-剪辑.md)
