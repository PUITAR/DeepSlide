# DeepSlide Evaluation

此目录是一个独立的评测模块，用于对不同 PPT agent 的生成结果进行离线指标评测与排行榜汇总。

## 目录约定

- 输入（原始数据）默认来自：`dataset/.cache/`
- 输出（各系统生成产物）默认来自：`experiments/.cache/main/`
- 本模块输出默认写入：`experiments/evaluation/outputs/`

## 快速开始

1) 安装依赖（仅对该评测模块）

```bash
pip install -r experiments/evaluation/requirements.txt
```

2) 生成 manifests

```bash
python experiments/evaluation/run_eval.py scan
```

3) 运行评测

```bash
python experiments/evaluation/run_eval.py evaluate
```

## 一键运行（推荐：Qwen3-VL-Flash 做 OCR）

1) 在 `deepslide-v4/.env` 配置 VLM（示例）

- `DEFAULT_VLM_PLATFORM_TYPE=aliyun`
- `DEFAULT_VLM_API_URL=https://dashscope.aliyuncs.com/api/v1`
- `DEFAULT_VLM_API_KEY=...`
- `DEFAULT_VLM_TYPE=qwen3-vl-flash`

2) 在 `experiments/evaluation/.env` 配置 OCR

- `EVAL_OCR_PROVIDER=aliyun_vlm`
- `EVAL_OCR_MODE=auto`

3) 一键跑完整评测（scan → evaluate → report）

```bash
python experiments/evaluation/run_oneclick.py
```

API 与环境变量字段说明见：`experiments/evaluation/API_CONFIG.md`

## 可选：DeepSeek-OCR-2 本地服务

如果你有 NVIDIA GPU 并希望用本地 OCR 模型：

```bash
pip install -r experiments/evaluation/ocr_server/requirements_deepseek_ocr2.txt
```

并在 `experiments/evaluation/.env` 里设置：

- `EVAL_OCR_PROVIDER=deepseek_ocr2`
- `EVAL_OCR_URL=http://127.0.0.1:8001/v1/ocr`

然后还是同样一键：

```bash
python experiments/evaluation/run_oneclick.py
```

如需启用基于大模型的自动主观评测（推荐），先在 `experiments/evaluation/.env` 中配置 `OPENAI_API_KEY`（可由 `.env.template` 拷贝），再运行：

```bash
python experiments/evaluation/run_eval.py evaluate --judge llm
```

说明：
- 若未配置 `OPENAI_API_KEY`（或 `EVAL_MODEL_API_KEY`），评测会自动降级为纯规则/统计评测（`judge_enabled=false`）。
- LLM 评测结果会缓存到 `experiments/evaluation/outputs/caches/judgements/`，重复运行会非常快。

4) 生成排行榜报告

```bash
python experiments/evaluation/run_eval.py report
```

## 产物

- `outputs/manifests/dataset.jsonl`
- `outputs/manifests/outputs.jsonl`
- `outputs/scores/scores.csv`
- `outputs/reports/leaderboard.md`
