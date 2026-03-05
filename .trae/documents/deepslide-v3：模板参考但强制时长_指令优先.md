## 目标
1. HTML 生成：去掉进度条，仅显示“生成（x/y）”文本。
2. 逻辑链推荐：pipeline 与所有模板风格（hook/bluf/faq/…）都必须优先遵循用户指令与总时长；模板只做参考。
3. PDF（Beamer）→ 可编辑 PPT：优先使用 PDF 解析重建文本框（参考 pdf2ppt.py），提升可编辑性。

## 关键约束（按你的最新要求）
- 逻辑节点时长仍然以“分钟”为单位（整数 min）。
- 因此天然存在硬下界：每个节点至少 1min ⇒ 节点数必须 ≤ total_minutes。

## 方案总览：模板软约束 + 时长硬约束（分钟守恒）
- 提示词层：明确优先级：用户指令/总时长/节点数上限 > 模板节奏建议。
- 后处理层：对 LLM 输出做确定性“节点数压缩 + 分钟分配守恒”，保证：
  - 节点数 ≤ total_minutes
  - 各节点 duration(min) 总和 == total_minutes
  - 每节点 duration(min) ≥ 1

## 1) HTML 生成 UI：移除进度条
- 前端覆盖层仅保留 spinner + 文案：移除 GlobalBusyOverlay 中 busyProgress 的条形渲染。
- 生成 HTML 轮询保留并显示“生成（current/total）…”，可本地化成中文。
- 可选清理：不再 setBusyProgress（因为 UI 不展示）。

## 2) 逻辑链：所有模板都服从“指令+总时长”（分钟单位）
### 2.1 统一解析总时长（输出 total_minutes 整数）
- 新增统一解析：支持 `5min/5 分钟/0.5h/00:05:00` → `total_minutes`（四舍五入或向下取整，策略固定）。
- projects.py 的候选展示与选择落盘、以及生成器内部都复用这一个解析，避免各算各的。

### 2.2 从 total_minutes 推导“硬节点上限 max_nodes”
- 计算：`max_nodes = min(total_minutes, max_nodes_by_duration(total_minutes))`
- 示例（可调整）：
  - 1–3min：2–3 节点
  - 4–5min：3–5 节点
  - 6–10min：4–7 节点
  - >10min：按上限线性增长，但永远 ≤ total_minutes
- 这个 max_nodes 是 MUST，模板不得突破。

### 2.3 提示词改造：模板作为“参考骨架”而非“覆盖规则”
- 在 generate_chain_via_tools 的 system rules 顶部写死：
  - “必须优先满足用户 focus_sections + 总时长 + max_nodes；模板仅 best-effort。”
  - “若 total_minutes 很短，允许折叠模板角色（例如把 Hook+BottomLine 合并为一个节点）。”
- 在模板 extra_guidance 里也加一句：模板角色可合并/省略以满足 max_nodes。

### 2.4 后处理：节点数压缩（跨模板通用）
当 LLM 返回 nodes 数 > max_nodes 时：
- 保留高优先级节点（优先：用户 focus_sections 命中的节点、以及模板要求的关键角色如 Hook/BottomLine/Takeaway）。
- 将低优先级节点按顺序合并到相邻节点：
  - 合并 title：用更短标题或保留主标题
  - 合并 description：拼接并去重
  - 合并 duration_ratio：相加
直到 nodes 数 == max_nodes。

### 2.5 分钟分配：严格守恒（不出现“总和超时”）
- 输入：total_minutes、(已压缩后的) duration_ratio
- 算法（最大余数法的“分钟版”）：
  1) ratio normalize（总和不为 1 先归一化）
  2) `base_i = floor(total_minutes * ratio_i)`
  3) 先保证每节点至少 1min：若某些 base_i 为 0，则从高 base 的节点中挪分钟，或触发进一步合并（因为 min=1 是硬约束）
  4) 把剩余分钟按小数部分从大到小分配，保证总和严格等于 total_minutes
- 输出：每节点 `duration: "{min}min"`（整数）。

### 2.6 应用落点（必须两处同时改）
- 候选展示：projects.py 里把 chain→node_duration 的逻辑替换成“压缩+守恒分配”。
- 候选选中落盘：select_logic_chain 同样替换，否则展示/落盘会不一致。

### 2.7 验证
- 用同一份需求（例如 5min）分别跑 pipeline/hook/bluf/faq：
  - 节点数 ≤ 5
  - duration 总和 == 5min
  - 节点时长均为整数分钟且 ≥1

## 3) PDF（Beamer）→ 可编辑 PPTX
- 新增 PDF→PPTX（可编辑文本框）实现：移植/改造 pdf2ppt.py 的核心逻辑到后端。
- 导出策略顺序调整：base.pdf→editable pptx；失败再走 tex 解析；再失败走图片兜底。
- 可选：export 参数 mode=pdf|tex|images 方便对比。

## 交付物（预计改动文件）
- 前端：GlobalBusyOverlay.tsx、SlideEditorView.tsx
- 后端：projects.py（候选展示 + 选择落盘）、chain_ai_generator.py（提示词与输出修复）、新增 duration/allocate 工具函数、editor.py（PDF→PPTX）