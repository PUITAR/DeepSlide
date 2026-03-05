## 需求理解
- 目标：在第 4 阶段（Stage 4 / Preview & Export）左下角新增两个“悬浮按钮”，交互与现有右下角 Download 按钮同一风格。
  - 左按钮：打开“数据面板”
    - 上半部分：用若干条形指标条展示“易于计算、无需大模型”的指标分数；指标名不显示缩写，用精简中文描述其含义。
    - 下半部分：根据这些指标做分析，给出演讲建议（由新增 agent 生成）。
  - 右按钮：打开“听众可能会问的问题”，输出 3 个问题（同样需要 agent，或与建议 agent 复用/拆分）。
- 约束：指标计算要尽量复用 `experiments/evaluation` 的计算思想/公式，但要适配 deepslide-v4 的数据来源与依赖（v4 后端依赖较轻，没有 sklearn 等）。
- 配置要求：新增 agent 需要在 `/home/ym/DeepSlide/deepslide-v4/.env` 与 `/home/ym/DeepSlide/deepslide-v4/env.md` 增加相应字段说明与示例。

## 1) 先选“真正轻量、无需 LLM”的指标（从 evaluation 里落地到 Stage4）
结合 `experiments/evaluation/deepslide_eval/metrics/*`，以及 v4 可直接拿到的数据（`recipe/speech.txt`、`recipe/content.tex`、`recipe/base.pdf`、`recipe/html_meta.json`、`recipe/alignment_dsid.json`），最适合做 Stage4 的“轻量实时指标”是：
- **可读性（L / Legibility）**：低成本、直接影响现场可讲性。
  - evaluation 原始输入：min_font_pt / word_count / num_shapes（见 `compute_legibility`）。
  - v4 可用输入：
    - `base.pdf` 用 PyMuPDF spans 得到每页最小字号/字号分布（v4 已依赖 `pymupdf`）。
    - `content.tex` 解析每页文本得到 word_count（v4 已有 frame 解析逻辑）。
    - num_shapes 在 LaTeX->PDF 场景不存在“shape”，用“文本块数 + 图片引用数 + 表格块数”做近似。
- **时间节奏（TDQ / Time Distribution Quality）**：不用 LLM。
  - evaluation 原始输入：duration_seconds + notes 字数估时 + 转场词命中（TRN 可规则化）。
  - v4 可用输入：requirements 里的总时长（若存在）+ `speech.txt` 每页字数。
  - Stage4 展示建议：当前页“预计口播时长”、与“建议时长”对比（deck 级也可给出超时/欠时风险）。
- **转场连贯（NDC proxy / Narrative Discontinuity）**：可无 LLM，但需要“相邻页语义相似度”。
  - evaluation 用 Embedder（tfidf/st）。v4 不引入新依赖的前提下：实现纯 Python 的轻量 TF/IDF + cosine（或退化为 token Jaccard / BM25-lite）。
  - Stage4 展示建议：与前一页/后一页连贯性（低=跳跃，高=冗余）。
- **稿件互补（SSC / Slide–Script Complementarity）**：可无 LLM。
  - evaluation 用 embedding 相似度；v4 可用“slide_text vs speech_text”的 token 覆盖率 + 余弦相似度。
  - Stage4 展示建议：
    - 过高：像在照读 slide（建议减 slide 字、保留锚点词）。
    - 过低：讲了很多但 slide 没锚点（建议加关键词/结构标题）。
- **目标匹配（RSat 规则版）**：可无 LLM。
  - evaluation 规则版仅用“时长→页数”一致性；v4 可扩展为：
    - 总页数 vs 总时长是否合理（每页期望 20–60s 区间）。
    - 是否存在“开场/动机/方法/结果/结论/Takeaway”等（用 `alignment_dsid.json` 的 page_type 或 `content.tex` 关键词规则近似）。
- **视觉聚焦就绪度（FR / Focus Readiness）**：这是你 plan 里提出的 +1，且在 v4 很适配且无需 LLM。
  - 不触碰 Image Focus 实现本身，仅复用现成产物：`html_meta.json`（effects/focus_pages）+ 每页是否有图片/表格/公式引用。
  - Stage4 展示建议：该页是否有清晰视觉锚点、是否具备可执行强调、强调是否过密/过稀（可先做“存在性/强度”版本）。

> 不建议 Stage4 MVP 放入：`F_text/F_vis` 这类“需要 source 文档对齐/图片哈希比对”的指标，除非 v4 已稳定保存 source 抽取物；否则会显著增加工程复杂度与 IO。

## 2) 指标到“面板文案”的映射（不用缩写）
面板中指标条显示“简短含义名”，不显示 TDQ/NDC/SSC 等缩写：
- L → **可读性**
- TDQ → **时间节奏**
- NDC → **转场连贯**
- SSC → **稿件互补**
- RSat → **目标匹配**
- FR → **视觉聚焦**

颜色/阈值（MVP）：先用可解释的硬阈值；后续可接你 evaluation 的分位数阈值。
- 例：可读性基于最小字号/文本密度；时间节奏基于估时 vs 预算；转场连贯基于相似度区间。

## 3) v4 的数据来源与抽取策略（不依赖新库）
在 v4 后端，Stage4 指标的输入尽量只依赖项目目录下已存在的渲染产物：
- `recipe/speech.txt`：每页讲稿（按 `<next>` 切分）。
- `recipe/content.tex`：每页结构化文本（title/bullets/plain/tables/images），复用现有 frame 解析逻辑（目前在 `editor.py` 的 `_extract_frame_struct`）。
- `recipe/base.pdf`：用 PyMuPDF 读取每页 text spans，统计字号/块数量。
- `recipe/html_meta.json`：获取每页 effects/focus_pages，做 FR。
- `recipe/alignment_dsid.json`：页类型/内容页映射（可做 RSat/过滤）。

产出统一 schema（供前端直接渲染）：
- `deck_summary`：总时长目标、估计总时长、总体风险 flags、总体分数（可选）。
- `per_slide[]`：对每个 page_index 给出：各指标分数（0~1）、关键原因（短字符串数组）、建议动作（短字符串数组），以及“预计口播秒数/文字密度/最小字号”等可解释字段。

## 4) 后端实现步骤（Stage4 专用，复刻 evaluation 的核心计算）
1. **新增一个 Stage4 指标服务模块**
   - 位置建议：`backend/app/services/preview_metrics/`（或同级 services 下一个 `preview_metrics_service.py`）。
   - 主要职责：读取项目 recipe 产物 → 抽取特征 → 计算指标 → 返回 JSON。
2. **实现轻量文本相似度（替代 evaluation 的 tfidf/st embedder）**
   - 纯 Python：tokenize（中英都做简单切分/去停用）→ 统计 TF 或 TF-IDF（手写 IDF）→ cosine。
   - 同一套向量器供 NDC 与 SSC 共用（避免重复计算）。
3. **逐项实现指标（按“可解释字段”优先）**
   - 可读性：min_font_pt、word_count、block_count（近似 shapes）；输出 0~1 分数 + 触发原因（如“最小字号过小”）。
   - 时间节奏：每页估时（字数/语速）+ deck 预算（总时长/页数或按页类型分配）；输出当前页超时/欠时。
   - 转场连贯：sim(prev,cur)、sim(cur,next)；低→跳跃，高→冗余。
   - 稿件互补：slide_text 与 speech_text overlap / cosine；输出“读稿风险/缺锚点风险”。
   - 目标匹配：页数 vs 时长 + 结构页存在性（规则）。
   - 视觉聚焦：是否存在锚点（images/tables/formulas）、是否有 focus/effects、节奏（全 deck 分布）。
4. **缓存与增量更新**
   - 生成 `recipe/preview_metrics.json`（带输入文件 mtime hash），若 `base.pdf/content.tex/speech.txt/html_meta.json` 未变则直接复用。
   - 这样 Stage4 打开面板不会反复扫 PDF。
5. **新增后端 API（供前端拉取）**
   - `GET /api/v1/projects/{project_id}/preview/metrics`：返回上述 schema。
   - 如果 recipe 产物缺失，返回可诊断的错误码与缺失项列表（前端显示“请先 Compile/Generate HTML”等）。

## 5) 演讲建议与听众提问：新增两个 Agent（LLM 只用于生成文本）
面板下半部分“建议”和右侧“3 个问题”使用 LLM，但输入严格受控（只传当前页必要信息 + 指标摘要），避免成本与泄露。
- **Agent A：PREVIEW_COACH**（演讲建议）
  - 输入：当前页 per_slide 指标、可解释字段（最小字号/估时/相邻相似度/图片锚点等）、当前页 slide_text 与 speech_text（长度截断）。
  - 输出：3–6 条可执行建议（短句），按影响度排序。
- **Agent B：AUDIENCE_QA**（听众提问）
  - 输入：当前页 slide_text（标题+要点+图表描述占位）+ 指标摘要（提醒“哪里可能被质疑”）。
  - 输出：3 个问题（面向听众角度，尽量具体）。

### 5.1 需要更新的 env 字段
按 v4 既有约定（`AGENT_<NAME>_MODEL_*`），新增：
- `AGENT_PREVIEW_COACH_MODEL_PLATFORM_TYPE`
- `AGENT_PREVIEW_COACH_MODEL_TYPE`
- `AGENT_PREVIEW_COACH_MODEL_API_URL`
- `AGENT_PREVIEW_COACH_MODEL_API_KEY`
- `AGENT_AUDIENCE_QA_MODEL_PLATFORM_TYPE`
- `AGENT_AUDIENCE_QA_MODEL_TYPE`
- `AGENT_AUDIENCE_QA_MODEL_API_URL`
- `AGENT_AUDIENCE_QA_MODEL_API_KEY`
并在 `env.md` 的“项目实际使用到的模型 Agent（完整列表）”表格里补两行说明。

## 6) 前端实现步骤（Stage4 UI：左下角两个按钮 + 两个面板）
1. **在 `PreviewView` 中新增两个 fixed 悬浮按钮**（`left-6 bottom-6`），视觉与右下角 Download 按钮对齐：
   - 左按钮（数据面板）：图标建议 `BarChart3`。
   - 右按钮（听众提问）：图标建议 `MessageCircleQuestion`/`HelpCircle`。
2. **新增两个面板组件（建议抽到独立组件）**
   - `PreviewMetricsPanel`：
     - 顶部：若干指标条（带颜色/数值/一句解释）。
     - 下方：`CoachAdvice` 文本区（支持“重新生成/刷新”按钮）。
   - `AudienceQuestionsPanel`：
     - 3 个问题列表（支持“重新生成”）。
   - 交互：点击按钮打开/关闭；ESC 关闭；点击遮罩关闭；面板采用玻璃卡片风格与现有 speech hover 卡片一致。
3. **前端数据流**
   - 在 `frontend/src/api/projects.ts` 增加 `getPreviewMetrics(projectId)`、`getPreviewCoachAdvice(projectId, pageIndex)`、`getAudienceQuestions(projectId, pageIndex)`。
   - 在 `useProjectStore` 增加 metrics 缓存字段（按 project_id 缓存），并在进入 Preview（`loadEditorFiles`）后懒加载 metrics（或首次打开面板再加载）。

## 7) 验证与回归（实现阶段的验收点）
- 计算正确性：选一个现有项目（`projects/<uuid>/recipe`）跑 metrics，检查：
  - per-slide 估时与讲稿字数一致；
  - min_font_pt 能从 base.pdf 提取到；
  - NDC/SSC 在相邻页相似/不相似时有合理变化；
  - FR 能从 html_meta/effects 与图片引用变化。
- UI/交互：
  - 左下角按钮不遮挡现有翻页/播放条与右下角 Download；
  - 面板滚动/关闭/加载态正常；
  - 无模型配置时：建议/问题区域显示“未配置模型”提示，但指标条仍可用。

## 代码落点索引（便于你核对我理解）
- Stage4 页面与 Download 按钮：PreviewView（`frontend/src/components/phases/PreviewView.tsx`）
- v4 可复用的 frame 结构解析：`backend/app/api/api_v1/endpoints/editor.py` 里的 `_extract_frame_struct`
- v4 可复用的 PDF span 字体读取范式：`backend/app/api/api_v1/endpoints/editor_pptx.py`
- evaluation 指标原实现：`experiments/evaluation/deepslide_eval/metrics/artifact.py` 与 `delivery.py`

如果你认可以上方向，下一步我会在不引入新重依赖的前提下（纯 Python + PyMuPDF）把“指标计算 + API + Stage4 两个面板 + 两个 Agent 配置”完整实现并自测。