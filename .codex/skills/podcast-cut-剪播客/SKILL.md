# podcast-cut-剪播客

将录音转录、AI分析并剪为 cut.wav。

## 用法

```bash
# 第一步（转录 + 分析，约 5–20 分钟）
python shared/scripts/run_pipeline.py \
  --ep-dir output/EP_ID \
  --track1 recordings/host.wav \
  [--track2 recordings/guest.wav]

# 人工在浏览器中审查后：
python shared/scripts/run_pipeline.py --ep-dir output/EP_ID --resume
```

## 前提

- `.env` 已配置 `VOLC_API_KEY` 和 `LLM_API_KEY`
- `pip install -e ".[dev]"` 已执行
- ffmpeg 已安装（`brew install ffmpeg` 或 `apt install ffmpeg`）

## 对齐选项（双轨）

```bash
--align clap                          # 录音前有拍掌声
--align timestamp --t1 10:00:00 --t2 10:00:03   # 知道各轨开始时间
# 不指定：ASR后自动从文字推断（默认）
```

## 输出

`output/EP_ID/4_cut/cut.wav` — 按审查意见剪辑的音频。
