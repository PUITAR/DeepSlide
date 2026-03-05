## 现状与根因（结合你给的项目输出）

* 图1的小区域不是“版式模板识别”产物：在该项目的生成 HTML 里，`slide_4.html` 直接写死了 4 个 regions，其中后两块明显更小：

  * [slide\_4.html:L668](file:///home/ym/DeepSlide/deepslide-v3/projects/62d587b4-ea2d-4dc7-aea2-06ec88e79b65/recipe/html_slides/slide_4.html#L668)

  * `[[0.06,0.18,0.42,0.68],[0.52,0.18,0.42,0.68],[0.33,0.28,0.12,0.18],[0.62,0.28,0.12,0.18]]`

* 当前“确定性 HTML 渲染器”仍然吃的是 LLM 生成的自由 ROI：

  * 在 [HtmlSlideRenderer.\_layout\_hero](file:///home/ym/DeepSlide/deepslide-v3/backend/app/services/html_slide_renderer.py#L685-L714) 里：`rois = plan.image.focus_regions`，只要 rois 非空就原样渲染。

  * RenderPlan 的 normalize 只做 clamp，不做最小面积/最小宽高过滤，因此 tiny box 会被保留：[render\_plan\_models.py:L113-L129](file:///home/ym/DeepSlide/deepslide-v3/backend/app/services/render_plan_models.py#L113-L129)

* 你提到的“Image Focus 已抛弃区域识别，转向版式识别（\_FOCUS\_TEMPLATES）”只发生在 `vlm_beautify.get_focus_regions()` 这条链路：它要求 VLM 只选模板，不允许自由矩形：

  * 模板定义：[\_FOCUS\_TEMPLATES](file:///home/ym/DeepSlide/deepslide-v3/backend/app/services/vlm_beautify.py#L408-L434)

  * VLM 仅返回 `template_id`，然后取模板 regions：[get\_focus\_regions](file:///home/ym/DeepSlide/deepslide-v3/backend/app/services/vlm_beautify.py#L458-L516)

  * 但这条函数目前只在编辑器局部预览里调用：[editor.py:L936-L966](file:///home/ym/DeepSlide/deepslide-v3/backend/app/api/api_v1/endpoints/editor.py#L936-L966)

  * 所以“生成到 recipe/html\_slides 的页面”并没有走模板识别，才会出现小区域。

* 图2的丑排版是因为 process\_stack 的 markup 生成了，但 CSS 没写：

  * Markup 生成：[\_layout\_process\_stack](file:///home/ym/DeepSlide/deepslide-v3/backend/app/services/html_slide_renderer.py#L665-L683)

  * 当前 `_css()` 里只有 `.pbox/.pbadge` 的零星通用规则，没有 `.layout--process/.process/.prow/.ptitle/.pdesc` 等关键布局样式，所以页面退化为默认流式排版：[slide\_5.html:layout--process](file:///home/ym/DeepSlide/deepslide-v3/projects/62d587b4-ea2d-4dc7-aea2-06ec88e79b65/recipe/html_slides/slide_5.html#L667)

## 修改目标（严格对齐你的要求）

* Image Focus：彻底不使用“自由 ROI/区域识别”的输出；统一改为“选择一个版式模板（\_FOCUS\_TEMPLATES）→ 输出模板 regions”。

* 排版：process\_stack 必须有现代、规整、可读的步骤卡片布局；不允许出现图2这种无样式退化。

## 逐步修改计划（按最小风险从输出端向上收敛）

### Step 1：在 HTML 渲染器里强制采用模板 regions（直接解决图1）

* 修改点：`HtmlSlideRenderer._layout_hero`（[html\_slide\_renderer.py:L685-L714](file:///home/ym/DeepSlide/deepslide-v3/backend/app/services/html_slide_renderer.py#L685-L714)）

* 策略：当 `Image Focus` 生效且 `image.url` 是允许的 asset URL 时：

  1. 从 `image.url` 解析 `project_id` 与 `path`（url decode）。
  2. 依据现有后端约束将其反解到本地绝对路径（同 `/asset` endpoint 的安全校验）：项目根目录来自 `DEEPSLIDE_V3_PROJECTS_DIR` 的默认逻辑（[project\_analyzer\_service.py](file:///home/ym/DeepSlide/deepslide-v3/backend/app/services/project_analyzer_service.py)）。
  3. 调用 `vlm_beautify.get_focus_regions(local_img, speech_text, max_regions=per_slide_max, prefer_vlm=True)` 得到 regions。

     * `speech_text` 用 `title + subtitle + core_message + bullets` 拼接即可（RenderPlan 没有原始 speech 字段）。
  4. 用这份 regions 覆盖 `plan.image.focus_regions`（或仅在渲染函数内部覆盖 `rois` 变量），确保不会把 LLM tiny boxes 带进来。
  5. 若本地解析失败/文件不存在：降级到模板默认（见 Step 2）或回退到原图（不启用 focus-zoom）。

* 预期效果：该项目的 `slide_4.html` 会只出现模板块（例如 LR\_50\_50 两块），不再出现两块小区域。

### Step 2：完善“无 VLM key 时”的模板选择（避免默认 2x2 导致体验差）

* 修改点：`vlm_beautify._default_focus_template_id()`（[vlm\_beautify.py:L448-L449](file:///home/ym/DeepSlide/deepslide-v3/backend/app/services/vlm_beautify.py#L448-L449)）与/或在 `get_focus_regions()` 内做轻量 fallback。

* 策略：不做区域检测，只做“版式类别”回退：

  * 基于图片宽高比选择：宽图→`LR_50_50`；高图→`TB_50_50`；接近方图→`GRID_2X2`。

  * 可选：增加一组“inset 模板”（同一模板但 y/h 做统一收缩），用于去掉图片上下白边；仍属于模板版式，不是自由 ROI。

### Step 3：加硬约束防止 tiny box 泄漏（双保险）

* 修改点候选（择一或组合）：

  * `RenderPlan.normalize()`（[render\_plan\_models.py:L113-L129](file:///home/ym/DeepSlide/deepslide-v3/backend/app/services/render_plan_models.py#L113-L129)）：对 `focus_regions` 增加最小宽高/最小面积过滤，并强制裁剪到 `per_slide_max_regions`。

  * 或在 `HtmlSlideRenderer._layout_hero` 内对最终 `rois` 做过滤（即便未来别处又塞进了小框，也不会渲染）。

* 过滤建议（可调）：`min(w,h) >= 0.18` 且 `w*h >= 0.05`。

### Step 4：让 LLM 不再输出自由 ROI（彻底与“模板识别”一致）

* 修改点：Prompt/Schema 层

  * [slide\_spec\_agent.py](file:///home/ym/DeepSlide/deepslide-v3/backend/app/services/slide_spec_agent.py) 与 [render\_plan\_agent.py](file:///home/ym/DeepSlide/deepslide-v3/backend/app/services/render_plan_agent.py)

* 策略：

  * 把“必须输出 focus\_regions”改成“不要输出 focus\_regions（留空/\[]），由渲染端基于模板自动生成”。

  * （可选增强）新增字段 `focus_template_id`：LLM 仅输出模板 id；渲染端用 `_FOCUS_TEMPLATES` 展开为 regions。

### Step 5：补齐 process\_stack 的全局 CSS（解决图2）

* 修改点：`HtmlSlideRenderer._css()`（在现有 `/* Process / Timeline / TriCards */` 附近插入缺失规则）

* 目标样式：

  * `.layout--process` 设为 `display:block;width:100%`

  * `.process` 纵向堆叠 + 合理间距

  * `.prow` 设为 flex 行

  * `.pbadge` 统一圆形渐变徽标

  * `.pbox/.ptitle/.pdesc` 设定 padding、字号、层级

* 预期效果：`slide_5.html` 的步骤区会变成规整的「编号徽标 + 卡片」两行堆叠，观感接近产品发布会风格。

## 验证方式（每一步都可量化）

* 验证图1：重新生成该项目 HTML 后检查 `slide_4.html` 的 `data-regions`：

  * 不应再包含 `[0.33,0.28,0.12,0.18]` / `[0.62,0.28,0.12,0.18]` 这种小框。

  * regions 数量应 ≤ `html_meta.json` 的 `per_slide_max_regions=3`。

* 验证图2：重新生成 `slide_5.html` 视觉：

  * `.layout--process` 的两行步骤有对齐、间距、徽标、标题/描述层级；不出现“无样式流式排版”。

## 影响范围与回滚策略

* 影响范围：仅影响 HTML 渲染输出（recipe/html\_slides 与 Web 导出/预览），不影响 PDF/LaTeX 产物。

* 回滚：所有改动集中在 `html_slide_renderer.py` +（可选）`vlm_beautify.py` + prompt 文件；可逐步合入并逐步验证。

