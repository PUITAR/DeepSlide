## 目标
1. HTML 生成：去掉进度条，仅显示“生成（x/y）”文本。
2. 逻辑链推荐：pipeline 与所有模板风格（hook/bluf/faq/…）都必须优先遵循用户指令与总时长；模板只做参考（叙事节奏不得覆盖时长/节点数约束）。
3. PDF（Beamer）→ 可编辑 PPT：优先使用 PDF 解析重建文本框（参考 pdf2ppt.py）。

## 关键约束（已固定）
- 逻辑节点时长以“整数分钟（min）”为单位。
- 若总时长 ≥ 10min：节点数固定在 4–7 个（不随时长继续增长）。

## 1) HTML 生成 UI：移除进度条
- 前端覆盖层仅保留 spinner + 文案：移除 GlobalBusyOverlay 中 busyProgress 的条形渲染。
- 生成 HTML 的轮询文案保留并本地化为“生成（current/total）…”。
- 可选清理：不再 setBusyProgress（因为 UI 不展示）。

## 2) 逻辑链：所有模板都服从“指令 + 总时长”（分钟单位）
### 2.1 统一解析总时长（输出 total_minutes 整数）
- 新增统一解析函数：支持 `5min/5 分钟/0.5h/00:05:00` → `total_minutes`。
- projects.py 的候选展示与选择落盘、以及生成器内部都复用这一解析，避免不同路径算出不同分钟数。

### 2.2 固定“目标节点数区间”（与你的规则对齐）
定义一个函数 `target_node_range(total_minutes)`，输出 (min_nodes, max_nodes)：
- 1–3min：2–3
- 4–5min：3–5
- 6–9min：4–6
- ≥10min：4–7（你指定的规则）
并做硬夹紧：
- `max_nodes = min(max_nodes, total_minutes)`（分钟制下每节点至少 1min）
- `min_nodes = min(min_nodes, max_nodes)`（避免 total_minutes 太小不可能满足）
最终得到 MUST 的 `max_nodes`。

### 2.3 提示词改造：模板仅“参考骨架”
在 generate_chain_via_tools 的 system rules 顶部写死优先级：
- MUST：满足用户 focus_sections、用户显式指令、总时长、以及 max_nodes。
- SHOULD：尽量采用模板的角色/节奏，但允许合并/省略模板角色以满足 MUST。
- 明确允许将 Hook/BottomLine/Takeaway 合并进同一节点（短时长或节点上限紧时）。

### 2.4 输出校验与自动修复（跨模板通用）
对 LLM 输出 chain JSON 做本地校验：
- nodes 数量是否 > max_nodes
- duration_ratio 是否缺失/非数字/总和为 0
- focus_sections 是否基本缺失（模板角色覆盖了重点章节）
修复策略：
- 轻度：normalize ratio；补齐缺失 ratio（均分）；裁剪并“合并尾部低权重节点”直到 nodes==max_nodes。
- 重度：触发一次 repair（LLM 二次改写）：输入原 chain + max_nodes + focus_sections + 用户指令 + 模板角色清单，要求“合并节点并重分配 ratio”，并再次声明模板可被折叠。

### 2.5 分钟分配：严格守恒（总和==total_minutes，且每节点>=1min）
用“分钟版最大余数法”从 ratio 分配整数分钟：
1) ratio normalize
2) base_i=floor(total_minutes*ratio_i)
3) 先保证每节点至少 1min：若存在 0min，则从分钟较大的节点挪给它；若挪不动则说明节点太多，回到 2.4 继续合并节点
4) 将剩余分钟按小数部分从大到小补齐
输出：每节点 `duration: "{k}min"`（整数），并保证总和严格等于 total_minutes。

### 2.6 应用落点（必须两处同时改）
- 候选展示（chain→UI nodes）：projects.py 内的 _transform_chain
- 候选选中落盘（chain→project nodes）：projects.py 的 select_logic_chain
两处都替换掉当前的 `max(1, int(total*ratio))`，否则展示与落盘会不一致。

### 2.7 验证
- 用同一份需求分别跑 pipeline/hook/bluf/faq：
  - 若 total_minutes≥10：节点数在 4–7
  - 其它时长：节点数不超过对应上限且不超过 total_minutes
  - duration 总和==total_minutes，且每节点 duration 为整数分钟 ≥1

## 3) PDF（Beamer）→ 可编辑 PPTX
- 新增 PDF→PPTX（可编辑文本框）实现：把 pdf2ppt.py 的核心逻辑移植/改造到后端（PyMuPDF 抽取 text blocks + bbox/style → pptx textbox）。
- 调整导出策略顺序：优先 base.pdf→editable pptx；失败再走现有 tex 解析；再失败走图片兜底。
- 可选提供 export 参数：mode=pdf|tex|images，便于对比。

## 交付物（预计改动文件）
- 前端：GlobalBusyOverlay.tsx、SlideEditorView.tsx
- 后端：projects.py（候选展示 + 选择落盘）、chain_ai_generator.py（提示词+修复流程）、新增 duration/allocate 工具函数、editor.py（PDF→PPTX）