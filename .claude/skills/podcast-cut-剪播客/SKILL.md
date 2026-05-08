# /podcast-cut-剪播客

将原始录音转录、LLM分析并剪成 cut.wav，供后期处理使用。

## 用法

提供1个（单轨）或2个（双轨，推荐）音频文件和剧集ID：

```bash
python shared/scripts/prepare_audio.py --track1 recordings/track1.wav [--track2 recordings/track2.wav] --ep-dir output/2026-05-08-ep01
```

随后按阶段顺序运行各脚本（详见下方流程表）。

## 前提条件

- 已运行 `/podcast-cut-安装`（ffmpeg、Python 依赖已就绪）
- `.env` 已配置 `VOLC_API_KEY`（或 `VOLC_APP_KEY`+`VOLC_ACCESS_KEY`）和 `LLM_API_KEY`/`LLM_BASE_URL`/`LLM_MODEL`

## 阶段流程（stages 1–4）

| 阶段 | 脚本 | 输入 | 输出 |
|------|------|------|------|
| 1.0 准备 | `prepare_audio.py` | 录音文件 | `input/working_track*.wav`, `audio_meta.json` |
| 1.1 上传 | `lib/upload.py` (内嵌) | working WAV | 音频URL |
| 1.2 ASR | `volcano_submit.py` + `volcano_query.py` | 音频URL | `volcano_raw_track*.json` |
| 1.3 合并 | `transcribe_merge.py` | volcano_raw × n | `words.json` |
| 1.4 分句 | `make_sentences.py` | words.json | `sentences.json` |
| 2.1 粗剪 | `analyze_rough.py` | sentences.json + 规则 | `rough_cuts.json` |
| 2.2 精剪 | `analyze_fine.py` | sentences.json + words.json + rough | `fine_cuts.json` |
| 2.3 自审 | `self_review.py` | rough + fine + sentences | `self_review.json` |
| 3.0 审查 | `generate_review_html.py` + `review_server.py` | 分析结果 | `review_enhanced.html` |
| 3.1 导出 | （手动，浏览器操作） | — | `delete_segments_edited.json` |
| 4.0 剪切 | `cut_audio.py` | working WAV + delete_segments_edited | `cut.wav` |
| 4.1 裁边 | `trim_silences.py` | cut.wav | cut.wav（覆盖，首尾静音裁剪） |

## 各阶段详情

- [阶段1 转录](../../docs/剪播客/阶段1-转录.md)
- [阶段2 分析](../../docs/剪播客/阶段2-分析.md)
- [阶段3 审查](../../docs/剪播客/阶段3-审查.md)
- [阶段4 剪辑](../../docs/剪播客/阶段4-剪辑.md)

## 常见错误

| 错误 | 原因 | 处理 |
|------|------|------|
| Volcano `45000001` | 参数无效（key/格式错误） | 检查 `.env` 中的 Volcano key |
| Volcano `45000132` | 音频超 512 MB | 先用 ffmpeg 转码为 16kHz mono mp3 |
| uguu.se 上传失败 | 网络或文件太大 | 重试；或配置 TOS/S3 |
| FFmpegError "silence trap" | 输出音量 ≤ -10 dB | 检查输入音频是否包含有效音频 |
