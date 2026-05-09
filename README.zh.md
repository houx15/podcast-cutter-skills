# podcast-cutter-skills

**语言: [English](README.md) | 中文**

一套中文播客剪辑工具，让你的 AI 编程助手（Claude Code / Codex CLI / Gemini CLI）从原始录音直接产出干净、采样级精度的 `cut.wav`。流水线包括 ASR 转录、Agent 驱动的剪辑分析、浏览器人工复核、以及精确的 ffmpeg 拼接。

> 📖 想让 Agent 直接驱动这个仓库？看 **[AGENTS.md](AGENTS.md)** —— 那是 Agent 读的契约文件。

---

## 用户快速上手

### 1. 克隆仓库

```bash
git clone https://github.com/houx15/podcast-cutter-skills.git
cd podcast-cutter-skills
```

### 2. 安装系统依赖

```bash
# macOS
brew install ffmpeg python@3.12

# Ubuntu / Debian
sudo apt install ffmpeg python3.10
```

验证：`ffmpeg -version` 和 `python3 --version`（Python 需 3.10+）。

### 3. 安装 Python 包

```bash
pip install -e ".[dev]"
```

### 4. 注册火山引擎（Volcano Engine）API Key

我们用[火山引擎语音技术](https://www.volcengine.com/product/speech-tech)做中文 ASR —— 这是目前我们试过中文准确率最高、有词级时间戳、免费额度也够用的服务。

1. 在 [console.volcengine.com](https://console.volcengine.com/) 注册账号（国内用户需要实名认证）。
2. 进入 **语音技术 → 应用管理**，创建一个应用，记下 **APP ID**。
3. 进入 **API 访问密钥**，创建一个 Key，记下 **API Key**。
4. 在 **大模型录音文件识别** 产品页，点击**开通**资源 `volc.bigasr.auc`（即 `volc.seedasr.auc`）。
5.（可选，处理超过 ~50 MB 的录音时需要）创建一个 **TOS bucket** 用于音频上传，并配一个对该 bucket 有读写权限的 **AccessKey / SecretKey**。

复制模板并填写：

```bash
cp .env.example .env
# 编辑 .env —— 至少要设置 VOLC_API_KEY 和 VOLC_RESOURCE_ID=volc.bigasr.auc
```

完整的环境变量说明在 [docs/configuration.md](docs/configuration.md)。

### 5. 让你的 Agent 上手这个仓库

在 **Claude Code**、**Codex CLI** 或 **Gemini CLI** 里打开仓库 —— 它们会自动读取 `AGENTS.md`/`CLAUDE.md`/`GEMINI.md`，并发现 `.claude/skills/`、`.codex/skills/`、`.gemini/skills/` 下捆绑的 skills。

把你的录音放到 `recordings/` 下，然后用大白话告诉 Agent：

> 剪播客 —— 录音在 `recordings/ep01.wav`，episode id 是 `2026-05-08-ep01`。

Agent 会读取 `.claude/skills/podcast-cut-剪播客/SKILL.md`，端到端跑完所有阶段，在阶段 3 暂停等你浏览器复核，最后产出 `output/<ep-id>/4_cut/cut.wav` 和 `output/<ep-id>/5_shownotes/shownotes.md`。

如果你想自己手动跑脚本（不带 Agent），看 **[AGENTS.md](AGENTS.md)** —— 里面列了每个脚本的输入和输出。

---

## 流水线工作原理

```
recording.wav  ─┐
                │  阶段 1 —— 转录
                │   ffmpeg 归一化 → 火山 ASR → 词级 + 句级 JSON
                ▼
         sentences.json
                │  阶段 2 —— 分析（你的 Agent 干活）
                │   读编辑规则和用户偏好，给出删除提案
                ▼
   rough_cuts.json + fine_cuts.json + self_review.json
                │  阶段 3 —— 人工复核
                │   浏览器时间轴，逐条接受/驳回删除
                ▼
   delete_segments_edited.json
                │  阶段 4 —— 剪辑
                │   ffmpeg 采样级拼接，25 ms 交叉淡化
                ▼
            cut.wav
                │  阶段 5 —— 节目笔记（可选）
                │   Agent 根据剪后逐字稿起草 shownotes.md
                ▼
          shownotes.md
```

每个阶段的产物是独立文件，存在 `output/<ep-id>/` 下。重跑某一阶段只覆盖该阶段的输出，上游文件不动 —— 所以可以低成本反复迭代。

---

## 目前还不够好的地方

诚实列一下当前的短板，欢迎贡献：

- **口癖（嗯/呃/那个/就是…）剪除还很粗糙。** 规则 pass 能干掉一部分明显的，但残留不少；fine-cut Agent pass 偶尔会把有意义的停顿也剪掉。复核时多半还是要花时间在这上面。
- **没有配乐 / 编曲。** 流水线产出一段干净的人声 `cut.wav` 就停了 —— 没有片头片尾音效、没有 ducking、没有分段 BGM。这些目前还需要你自己进 DAW 手动处理。
- **单轨录音的说话人分离（diarization）不稳。** 火山 ASR 在单轨混音上经常返回 `speaker=null`。强烈建议双轨录音（一人一麦），可以完全规避这个问题。
- **节目笔记是模板化的，不是真正适配的。** 阶段 5 能给出一份能用的初稿（按我们自己播客的语气），但开头一段和 Highlights 通常你还是会想自己重写。

---

## 给贡献者

### 仓库结构

```
podcast-cutter-skills/
├── shared/
│   ├── scripts/              # 每个流水线阶段一个脚本
│   │   ├── lib/              # 共享库模块
│   │   │   ├── config.py         # 环境变量 + LLM 配置加载
│   │   │   ├── ffmpeg_wrap.py    # 唯一 ffmpeg 入口（带静音陷阱保护）
│   │   │   ├── volcano_client.py # 火山 ASR HTTP 客户端
│   │   │   ├── upload.py         # TOS → S3 → uguu.se 上传链
│   │   │   ├── json_io.py        # 原子 JSON 读写
│   │   │   └── audio_constants.py# 采样率、位深、交叉淡化等常量
│   │   └── install/          # 依赖检查 + 资源拉取脚本
│   ├── rules/
│   │   ├── editing/          # 编辑规则（中文 Markdown，作 Agent 的系统提示词）
│   │   └── users/default/    # 默认用户偏好（preferences.yaml、hotwords.txt）
│   └── test_fixtures/        # 测试用的音频固件
├── tests/                    # pytest 测试套件
│   ├── lib/                  # lib/ 模块测试
│   ├── scripts/              # 各流水线脚本测试
│   └── install/              # 安装脚本测试
├── docs/
│   ├── 剪播客/               # 各阶段文档（1–4）+ 快速上手
│   ├── configuration.md      # 所有 .env 变量说明
│   ├── volcano_asr.md        # 火山 ASR API 参考
│   └── volcano_tos_sdk.md    # 火山 TOS SDK / 签名参考
├── .claude/                  # Claude Code skills、agents、rules
├── .codex/                   # Codex CLI skills + prompts
├── .gemini/                  # Gemini CLI skills + commands
├── output/                   # 单期工作目录（已 gitignore）
├── recordings/               # 原始录音（已 gitignore）
├── .env.example
├── AGENTS.md                 # 面向 Agent 的项目说明
├── pyproject.toml
└── CHANGELOG.md
```

### 开发

```bash
pytest                                      # 完整测试套件
pytest --cov=shared/scripts --cov-report=term-missing
pytest tests/lib/test_ffmpeg_wrap.py -v     # 单个模块
```

所有新功能必须 TDD —— 先写失败的测试，再写实现。`ffmpeg-invariants-reviewer` 子代理会强制要求所有 ffmpeg 调用走 `lib/ffmpeg_wrap.run_ffmpeg`。

### 阶段文档

- [阶段 1 — 转录](docs/剪播客/阶段1-转录.md)
- [阶段 2 — 分析](docs/剪播客/阶段2-分析.md)
- [阶段 3 — 审查](docs/剪播客/阶段3-审查.md)
- [阶段 4 — 剪辑](docs/剪播客/阶段4-剪辑.md)
- [配置参考](docs/configuration.md)
- [快速上手](docs/剪播客/快速上手.md)

---

## 致谢

这个项目从下面这些开源项目借鉴了思路、模式和编辑规则的灵感。非常感谢作者们：

- [kennyzheng-builds/ai-podcast-editor](https://github.com/kennyzheng-builds/ai-podcast-editor) —— 受 Descript 启发的转录驱动编辑器，启发了我们对文本↔音频映射和口癖检测的思考。
- [JasonYpro/autocut-skills](https://github.com/JasonYpro/autocut-skills) —— AI 驱动的口播视频自动剪辑，使用火山 ASR + 浏览器复核的流程，影响了我们的 review UI 设计。
- [luoyuweidu1/podcastcut-skills](https://github.com/luoyuweidu1/podcastcut-skills) —— 用 Claude Code Skills 做播客剪辑的方案，影响了我们的 skill / 阶段划分。
- [avaleenlhs-gif/zh-podcast-filler-cut](https://github.com/avaleenlhs-gif/zh-podcast-filler-cut) —— Whisper + ffmpeg 的口癖剪除工具，其启发式词表为我们的规则 pass 提供了参考。

在这个领域做事的人，这几个仓库都很值得一读。
