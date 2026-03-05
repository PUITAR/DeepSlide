# DeepSlide v4 模型与环境变量总览

本项目所有模型调用统一通过 `resolve_text_llm_env / resolve_vlm_env / resolve_asr_env` 读取环境变量。
图像生成（非 VLM）统一通过 `resolve_img_env` 读取环境变量（用于生成背景/overlay/mask/关键帧等可控视觉资产）。

## 1) 通用默认配置（对所有 Agent 生效）

**文本 LLM（Text LLM）默认值**
- DEFAULT_MODEL_PLATFORM_TYPE
- DEFAULT_MODEL_TYPE
- DEFAULT_MODEL_API_URL
- DEFAULT_MODEL_API_KEY

**视觉/多模态 VLM 默认值**
- DEFAULT_VLM_PLATFORM_TYPE
- DEFAULT_VLM_TYPE
- DEFAULT_VLM_API_URL
- DEFAULT_VLM_API_KEY

**语音识别 ASR 默认值**
- DEFAULT_ASR_PLATFORM_TYPE
- DEFAULT_ASR_TYPE
- DEFAULT_ASR_API_URL
- DEFAULT_ASR_API_KEY

**图像生成 IMG 默认值（用于视觉资产生成，不用于 VLM 识图）**
- DEFAULT_IMG_PLATFORM_TYPE
- DEFAULT_IMG_TYPE
- DEFAULT_IMG_API_URL
- DEFAULT_IMG_API_KEY

> 说明：
> - 如果未设置 Agent 单独配置，则会使用 DEFAULT_* 作为全局默认。
> - LLM 额外兼容 `LLM_API_KEY` 作为 `DEFAULT_MODEL_API_KEY` 的兜底。

---

## 2) Agent 单独覆盖（按 Agent 名称配置）

**文本 LLM Agent 的覆盖字段**
- AGENT_<AGENT_NAME>_MODEL_PLATFORM_TYPE
- AGENT_<AGENT_NAME>_MODEL_TYPE
- AGENT_<AGENT_NAME>_MODEL_API_URL
- AGENT_<AGENT_NAME>_MODEL_API_KEY

**VLM Agent 的覆盖字段**
- AGENT_<AGENT_NAME>_VLM_PLATFORM_TYPE
- AGENT_<AGENT_NAME>_VLM_TYPE
- AGENT_<AGENT_NAME>_VLM_API_URL
- AGENT_<AGENT_NAME>_VLM_API_KEY

**ASR Agent 的覆盖字段**
- AGENT_<AGENT_NAME>_ASR_PLATFORM_TYPE
- AGENT_<AGENT_NAME>_ASR_TYPE
- AGENT_<AGENT_NAME>_ASR_API_URL
- AGENT_<AGENT_NAME>_ASR_API_KEY

**图像生成 IMG Agent 的覆盖字段**
- AGENT_<AGENT_NAME>_IMG_PLATFORM_TYPE
- AGENT_<AGENT_NAME>_IMG_TYPE
- AGENT_<AGENT_NAME>_IMG_API_URL
- AGENT_<AGENT_NAME>_IMG_API_KEY

> 注意：`<AGENT_NAME>` 会做大写与非字母数字替换为下划线（见 agent_model_env.py）。

---

## 3) 项目中实际使用到的模型 Agent（完整列表）

### A. 文本 LLM（resolve_text_llm_env）

| Agent 名称 | 功能/调用位置 | 需要的 env 字段（可选覆盖） |
|---|---|---|
| REQUIREMENTS | 需求澄清对话（requirements_service.py） | AGENT_REQUIREMENTS_MODEL_* |
| TEMPLATE_RECOMMENDER | 逻辑链模板选择（core/template_recommender.py） | AGENT_TEMPLATE_RECOMMENDER_MODEL_* |
| CHAIN | 逻辑链生成（core/chain_ai_generator.py） | AGENT_CHAIN_MODEL_* |
| COMPRESSOR | 章节压缩/提炼（core/compressor.py） | AGENT_COMPRESSOR_MODEL_* |
| COMPILER | 生成内容/编译辅助（core/compiler.py & core/compiler_service.py） | AGENT_COMPILER_MODEL_* |
| SLIDE_GRAPH | 结构化逻辑图（core/slide_graph_generator.py） | AGENT_SLIDE_GRAPH_MODEL_* |
| DIAGRAM_SPEC | 结构化图（diagram_spec_agent.py） | AGENT_DIAGRAM_SPEC_MODEL_* |
| DRAWIO | drawio 生成（drawio_agent.py） | AGENT_DRAWIO_MODEL_* |
| EDITOR | 编辑器指令规划与执行（editor_service.py / editor_ai_service.py） | AGENT_EDITOR_MODEL_* |
| RENDER_PLAN | Spec-mode HTML RenderPlan 生成（render_plan_agent.py） | AGENT_RENDER_PLAN_MODEL_* |
| HTML_REVIEW | Spec-mode HTML QA（render_review_agent.py） | AGENT_HTML_REVIEW_MODEL_* |
| DECK_STYLE | Deck Style DNA 生成与锁定（deck_style_agent.py） | AGENT_DECK_STYLE_MODEL_* |
| VISUAL_INTENT | 每页内容驱动的视觉意图生成（visual_intent_agent.py） | AGENT_VISUAL_INTENT_MODEL_* |
| PREVIEW_COACH | Stage4 预览：指标分析→演讲建议（preview_insights_service.py） | AGENT_PREVIEW_COACH_MODEL_* |
| AUDIENCE_QA | Stage4 预览：听众可能提问（preview_insights_service.py） | AGENT_AUDIENCE_QA_MODEL_* |

**说明**：以上 Agent 全部使用 `MODEL_PLATFORM_TYPE / MODEL_TYPE / MODEL_API_URL / MODEL_API_KEY`。

---

### B. 多模态 VLM（resolve_vlm_env）

| Agent 名称 | 功能/调用位置 | 需要的 env 字段（可选覆盖） |
|---|---|---|
| VLM_BEAUTIFY | 视觉模型：图像焦点模板/区域识别与布局辅助（vlm_beautify.py） | AGENT_VLM_BEAUTIFY_VLM_* |

**说明**：HTML 生成的图像布局与 ROI 识别依赖 VLM_BEAUTIFY（用于 Image Focus / Focus Template 选择与辅助布局）。

**说明**：VLM 读取 `VLM_PLATFORM_TYPE / VLM_TYPE / VLM_API_URL / VLM_API_KEY`。

---

### C. 图像生成 IMG（resolve_img_env）

| Agent 名称 | 功能/调用位置 | 需要的 env 字段（可选覆盖） |
|---|---|---|
| VFX_IMG | 视觉资产生成：背景/叠层/遮罩/关键帧（image_gen_client.py / visual_asset_service.py） | AGENT_VFX_IMG_IMG_* |

**说明**：IMG 读取 `IMG_PLATFORM_TYPE / IMG_TYPE / IMG_API_URL / IMG_API_KEY`。

---

### C. 语音识别 ASR（resolve_asr_env）

| Agent 名称 | 功能/调用位置 | 需要的 env 字段（可选覆盖） |
|---|---|---|
| ASR | 语音转文字（asr_service.py） | AGENT_ASR_ASR_* |

**说明**：ASR 读取 `ASR_PLATFORM_TYPE / ASR_TYPE / ASR_API_URL / ASR_API_KEY`。

---

## 4) TTS（语音合成）说明

当前 TTS 走本地 `index-tts`（audio.py / audio_service.py），**不使用模型 API**。相关控制参数：
- INDEXTTS_DEVICE 或 DS_TTS_DEVICE（优先使用 INDEXTTS_DEVICE）

如果后续接入云端 TTS，可按 ASR/VLM 的方式添加 `resolve_tts_env` 或自定义配置。

---

## 5) .env 示例（最小必需）

```
# 文本 LLM 默认
DEFAULT_MODEL_PLATFORM_TYPE=deepseek
DEFAULT_MODEL_TYPE=deepseek-chat
DEFAULT_MODEL_API_URL=https://api.deepseek.com
DEFAULT_MODEL_API_KEY=sk-xxxxxxxx

# VLM 默认
DEFAULT_VLM_PLATFORM_TYPE=aliyun
DEFAULT_VLM_TYPE=qwen3-vl-flash
DEFAULT_VLM_API_URL=https://dashscope.aliyuncs.com/api/v1
DEFAULT_VLM_API_KEY=sk-xxxxxxxx

# ASR 默认
DEFAULT_ASR_PLATFORM_TYPE=aliyun
DEFAULT_ASR_TYPE=qwen3-asr-flash
DEFAULT_ASR_API_URL=https://dashscope.aliyuncs.com/api/v1
DEFAULT_ASR_API_KEY=sk-xxxxxxxx

# IMG 默认（视觉资产生成）
DEFAULT_IMG_PLATFORM_TYPE=openai
DEFAULT_IMG_TYPE=gpt-image-1
DEFAULT_IMG_API_URL=https://api.openai.com/v1
DEFAULT_IMG_API_KEY=sk-xxxxxxxx

# 示例：单独覆盖 RENDER_PLAN
AGENT_RENDER_PLAN_MODEL_PLATFORM_TYPE=openai
AGENT_RENDER_PLAN_MODEL_TYPE=gpt-4o
AGENT_RENDER_PLAN_MODEL_API_URL=https://api.openai.com/v1
AGENT_RENDER_PLAN_MODEL_API_KEY=sk-xxxxxxxx

# 示例：单独覆盖 VFX_IMG（视觉资产生成）
AGENT_VFX_IMG_IMG_PLATFORM_TYPE=openai
AGENT_VFX_IMG_IMG_TYPE=gpt-image-1
AGENT_VFX_IMG_IMG_API_URL=https://api.openai.com/v1
AGENT_VFX_IMG_IMG_API_KEY=sk-xxxxxxxx

# 可选：默认自动开启 Visual FX（不传 visual_fx 也会生效）
DS_VISUAL_FX_AUTO=0
```

---

## 6) 相关源码位置索引

- agent_model_env: backend/app/core/agent_model_env.py
- requirements: backend/app/services/requirements_service.py
- template recommender: backend/app/services/core/template_recommender.py
- chain generator: backend/app/services/core/chain_ai_generator.py
- compressor: backend/app/services/core/compressor.py
- compiler: backend/app/services/core/compiler.py, backend/app/services/core/compiler_service.py
- slide graph: backend/app/services/core/slide_graph_generator.py
- diagram spec: backend/app/services/diagram_spec_agent.py
- drawio: backend/app/services/drawio_agent.py
- editor: backend/app/services/editor_service.py, backend/app/services/editor_ai_service.py
- render plan: backend/app/services/render_plan_agent.py
- html review: backend/app/services/render_review_agent.py
- deck style: backend/app/services/deck_style_agent.py
- vlm beautify: backend/app/services/vlm_beautify.py
- visual assets: backend/app/services/visual_asset_service.py
- image gen: backend/app/services/image_gen_client.py
- asr: backend/app/services/asr_service.py
