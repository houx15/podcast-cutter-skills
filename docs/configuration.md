# Configuration Reference

All configuration is supplied through environment variables. Copy `.env.example` to `.env` and fill in the values before running any pipeline script.

```bash
cp .env.example .env
```

Variables are loaded automatically via `python-dotenv` when any script starts.

---

## Volcano Engine ASR

The ASR stage (1.2) authenticates with Volcano Engine's OpenSpeech API. Two authentication schemes exist; use whichever matches your console generation.

### New console (recommended)

| Variable | Required | Description |
|----------|----------|-------------|
| `VOLC_API_KEY` | Yes (new console) | Single API key obtained from the [Volcano Engine Speech console](https://console.volcengine.com/speech/new/setting/apikeys). When set, `VOLC_APP_KEY` and `VOLC_ACCESS_KEY` are ignored. |

### Old console (legacy)

| Variable | Required | Description |
|----------|----------|-------------|
| `VOLC_APP_KEY` | Yes (old console) | Application ID from the old Volcano Engine console. |
| `VOLC_ACCESS_KEY` | Yes (old console) | Access token paired with `VOLC_APP_KEY`. |

### Common to both

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `VOLC_RESOURCE_ID` | Yes | `volc.seedasr.auc` | ASR resource identifier. `volc.seedasr.auc` is the v3 large-model resource that supports Chinese, word-level timestamps, and two-speaker diarization. Do not change this unless you have been issued a different resource. |

For more details on the Volcano Engine ASR API, see [docs/volcano_asr.md](volcano_asr.md).

---

## Audio Upload

Before ASR can process a file it must be accessible via a public URL. The upload module tries backends in priority order: Volcano TOS → S3-compatible → uguu.se. Leave all upload variables empty only for quick local testing; uguu.se has a file-size limit and a 24-hour retention window.

### Volcano TOS (recommended)

Same vendor as ASR, so no cross-provider latency. Create a bucket in the [Volcano Engine TOS console](https://console.volcengine.com/tos).

| Variable | Required | Description |
|----------|----------|-------------|
| `TOS_ACCESS_KEY` | Yes (if using TOS) | Access key for your TOS account. |
| `TOS_SECRET_KEY` | Yes (if using TOS) | Secret key for your TOS account. |
| `TOS_BUCKET` | Yes (if using TOS) | Bucket name. |
| `TOS_ENDPOINT` | Yes (if using TOS) | Endpoint URL, e.g. `https://tos-cn-beijing.volces.com`. |

### S3-compatible (Cloudflare R2, AWS S3, Aliyun OSS)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `S3_ENDPOINT` | Yes (if using S3) | — | Full endpoint URL, e.g. `https://<account>.r2.cloudflarestorage.com`. |
| `S3_BUCKET` | Yes (if using S3) | — | Bucket name. |
| `S3_ACCESS_KEY` | Yes (if using S3) | — | Access key ID. |
| `S3_SECRET_KEY` | Yes (if using S3) | — | Secret access key. |
| `S3_REGION` | No | `auto` | Region string. `auto` works for Cloudflare R2; set to `us-east-1` or similar for AWS. |

### uguu.se fallback

No configuration required. The upload module falls through to uguu.se automatically when no TOS or S3 credentials are present, and prints a privacy warning. Files are public and deleted after 24 hours.

---

## LLM — ByteDance Ark (doubao)

Stages 2.1, 2.2, and 2.3 call an OpenAI-compatible LLM endpoint.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LLM_API_KEY` | Yes | — | API key for the ByteDance Ark platform. Obtain from the [Ark console](https://console.volcengine.com/ark). |
| `LLM_BASE_URL` | No | `https://ark.cn-beijing.volces.com/api/v3` | Base URL for the Ark API. Override if you use a different region or a self-hosted OpenAI-compatible endpoint. |
| `LLM_MODEL` | No | `doubao-seed-2-0-code-preview-260215` | Model endpoint ID. Must be an endpoint you have activated in the Ark console; the model name alone is not sufficient. |

---

## Optional — Gemini (AI listening review)

Used by `qc_ai_listen.py` and the `listening-spot-check-reviewer` subagent, which are planned for a later phase. Not required to run the stages 1–4 pipeline.

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | No | API key from [Google AI Studio](https://aistudio.google.com/app/apikey). |

---

## Minimal .env for stages 1–4

```dotenv
# New-console Volcano ASR key
VOLC_API_KEY=your_key_here

# LLM
LLM_API_KEY=your_ark_key_here
LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
LLM_MODEL=doubao-seed-2-0-code-preview-260215

# At least one upload backend (or leave empty to use uguu.se)
TOS_ACCESS_KEY=
TOS_SECRET_KEY=
TOS_BUCKET=
TOS_ENDPOINT=
```
