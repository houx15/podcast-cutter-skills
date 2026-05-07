---
name: podcast-cut-安装
description: |
  播客剪辑环境一次性准备：依赖检查、.env 模板、Volcano 凭据自验、bundled 资产准备。
  触发词：安装播客剪辑、初始化播客环境、podcast cut install
---

# 播客剪辑 · 安装

> 首次使用前的环境准备。运行一次即可。

## 快速使用

```
用户: 安装播客剪辑环境
用户: podcast cut install
```

## 步骤

### 1. 依赖检查

```bash
bash shared/scripts/install/check_deps.sh
```

需要：
- `node` ≥ 18
- `ffmpeg` ≥ 6（含 `ffprobe`，含 `arnndn` 滤镜）
- `python3` ≥ 3.10

如缺，脚本会打印对应的 `brew install` / `apt install` 命令。

### 2. Python 依赖

```bash
pip install -e ".[dev]"
```

### 3. 配置 `.env`

```bash
cp .env.example .env
$EDITOR .env
```

最少需要的字段（新版控制台）：
- `VOLC_API_KEY`：Volcano 引擎控制台获取
- `VOLC_RESOURCE_ID=volc.seedasr.auc`（默认）

可选：`TOS_*` 或 `S3_*`（音频上传后端，未配置则回退到 uguu.se 公网临时托管，会有提示）

### 4. 资产准备（stub，Plan 4 实现）

```bash
bash shared/scripts/install/fetch_assets.sh
```

当前只确认目录结构。Plan 4 后会下载 RNNoise 模型 + 默认 royalty-free 片头/片尾音乐。

### 5. Volcano 凭据自验

```bash
python -m shared.scripts.install.verify_volcano --no-network
```

`--no-network` 是 Plan 1 的默认选项；Plan 2 提供 `volcano_submit.py` 后会做完整的 ping 测试。

### 6. 测试套件

```bash
python -m pytest
```

全部通过即环境就绪。

## 输出

无文件输出，只是环境验证。

## 与其他 skill 的关系

```
/podcast-cut-安装   ← 本 skill（一次性）
/podcast-cut-剪播客 ← 主流程（Plan 2、3）
/podcast-cut-后期   ← 后期处理（Plan 4）
/podcast-cut-质检   ← 质检（Plan 5）
```

## 常见问题

**Q: `ffmpeg arnndn` 滤镜找不到？**
ffmpeg 必须 ≥ 4.4 且编译时启用 `--enable-libavfilter`。Homebrew 的版本默认满足。

**Q: 不想用 uguu.se 上传？**
在 `.env` 里配置 `TOS_*` 或 `S3_*` 任一组。优先级：TOS → S3 → uguu。
