# 评测所用 API 与 .env 配置

本评测只依赖两类外部 API：

1) **LLM Judge API**：用于 `RSat/SSC/TDQ` 等需要模型判断的指标
2) **OCR API（Qwen3-VL-Flash）**：用于 PPTX/PDF 无法直接抽取文本时，从渲染图片里识别文字

评测启动时会按如下顺序加载 dotenv（后者覆盖前者同名变量）：

1) `deepslide-v4/.env`
2) `experiments/evaluation/.env`

## 一、LLM Judge API

最少需要填一套：

- `EVAL_MODEL_PLATFORM_TYPE`
- `EVAL_MODEL_TYPE`
- `EVAL_MODEL_API_URL`（如平台需要）
- `EVAL_MODEL_API_KEY`（如为空会回退到 `LLM_API_KEY` 或 `OPENAI_API_KEY`）

如果你希望只覆盖“Judge 用的模型”（而不影响其它潜在调用），填这一套：

- `EVAL_JUDGE_MODEL_PLATFORM_TYPE`
- `EVAL_JUDGE_MODEL_TYPE`
- `EVAL_JUDGE_MODEL_API_URL`
- `EVAL_JUDGE_MODEL_API_KEY`

兜底 Key：

- `LLM_API_KEY`
- `OPENAI_API_KEY`

## 二、OCR API（统一用 qwen3-vl-flash）

必填：

- `EVAL_OCR_PROVIDER=aliyun_vlm`
- `DEFAULT_VLM_PLATFORM_TYPE=aliyun`
- `DEFAULT_VLM_TYPE=qwen3-vl-flash`
- `DEFAULT_VLM_API_URL=https://dashscope.aliyuncs.com/api/v1`
- `DEFAULT_VLM_API_KEY=...`

可选（一般保持默认即可）：

- `EVAL_OCR_MODE=auto|on|off`
- `EVAL_OCR_TIMEOUT_SECONDS=60`
- `EVAL_RENDER_DPI=200`
- `EVAL_OCR_TEXT_MIN_CHARS=40`
- `EVAL_OCR_PROMPT=...`

## 三、可选：BERTScore

默认关闭（避免下载模型/占显存）；关闭时会用 embedding proxy 代替。

- `EVAL_BERTSCORE_ENABLED=0|1`
- `EVAL_BERTSCORE_MODEL=roberta-base`

