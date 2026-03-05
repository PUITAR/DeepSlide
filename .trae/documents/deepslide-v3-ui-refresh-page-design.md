# DeepSlide v3（桌面优先）页面设计规范：UI 精简现代化 + 语音输入一期

## 全局设计（Global Styles）
- Layout 方法：整体采用 Flexbox + 局部 CSS Grid；卡片与面板使用 8px spacing scale。
- 颜色（Design Tokens）
  - bg: #F8FAFC（slate-50）
  - surface: #FFFFFF
  - text: #0F172A（slate-900） / secondary: #64748B（slate-500）
  - primary: #2563EB（blue-600） / primary-hover: #1D4ED8（blue-700）
  - border: #E2E8F0（slate-200）
  - success: #16A34A（green-600） / danger: #DC2626（red-600）
- 字体：系统字体优先（Inter 可选）；字号：H1 24、H2 18、正文 14、辅助 12。
- 按钮：默认 10px 圆角；primary 实心、secondary 描边；hover 提升阴影 + 轻微变暗；disabled 40% 透明。
- 输入框：高度 40（单行）；聚焦 ring-2 primary；错误态 border-danger + error hint。
- 动效：仅保留必要的 150–200ms ease-out（hover、弹窗出现、加载态）；避免重度动效。

## 页面 1：上传页（UploadView）
### Meta Information
- title: DeepSlide – 上传论文工程
- description: 上传 LaTeX 工程压缩包并自动解析

### Page Structure
- 居中单列卡片（max-w: 520）；顶部品牌/标题，主体上传卡片，底部辅助说明。

### Sections & Components
1) Header
- 左：DeepSlide 标识（文字即可）；右：可选“帮助/示例压缩包格式”。

2) Upload Card（精简）
- Dropzone（可点击/拖拽）
  - 主文案：拖拽或点击上传
  - 次文案：支持 .zip / .tar / .tar.gz
  - 上传后展示：文件名 + 大小 + “更换文件”
- Primary CTA：开始解析（disabled：无文件/上传中）
- Secondary CTA：取消上传（仅上传中显示）

3) Analysis Summary（解析完成后同页展示，减少跳转）
- 3 个信息块（cards）：
  - Main TeX：路径/文件名
  - Abstract：前 200 字 + 展开
  - Outline：章节数量/关键章节列表（滚动容器）
- Primary CTA：进入需求对话

### Responsive
- <768：卡片全宽；摘要/大纲折叠为 accordion。

## 页面 2：需求对话页（RequirementsView）
### Meta Information
- title: DeepSlide – 需求对话
- description: 与助手确认受众/时长/重点/风格

### Page Structure
- 三段式：顶部轻量 header（步骤/项目名）+ 中间消息流 + 底部输入栏（sticky）。

### Sections & Components
1) Header（高度 56）
- 左：项目名（可从上传文件名派生）
- 右：Step 1/3、返回上传（可选）

2) Message List
- 视觉：气泡式，assistant 左、user 右；Markdown 渲染仅用于 assistant。
- 行为：新消息自动滚动；长回复支持代码/公式渲染但默认收敛（超过阈值折叠“展开”）。

3) Input Bar（语音一期重点）
- Layout：Grid 12 列
  - 左 1 列：语音按钮（Mic / Stop）
  - 中 10 列：输入框（单行为主，Shift+Enter 扩展为多行）
  - 右 1 列：发送按钮
- 语音交互（第一阶段 ASR）
  - 点击 Mic：开始录音（状态点 + 计时）
  - 点击 Stop：结束录音→显示“转写中…”→转写结果填入输入框
  - 转写失败：toast 提示 + 保留录音可重试；不阻塞手动输入
- 状态：isChatting 时禁用发送并显示小 loading。

## 页面 3：逻辑链编辑页（LogicChainView 精简改造建议）
### Meta Information
- title: DeepSlide – 逻辑链编辑
- description: 调整讲述顺序与引用关系

### Page Structure（从“横向大画布+SVG”收敛为“列表+详情”）
- 左右两栏（Desktop）
  - 左：Timeline List（可拖拽排序）
  - 右：Node Details + Links

### Sections & Components
1) Header
- 左：标题 + Step 2/3
- 右：节点数、总时长、Primary CTA「确认并生成」

2) Timeline List（左栏）
- 列表项卡片：序号、标题（两行省略）、时长步进（±1）、更多（编辑/删除）
- 拖拽：仅把手区域可拖，避免误触；拖拽时卡片轻微放大。
- Empty：引导添加节点。

3) Node Details（右栏）
- 表单：Title、Type、Duration(min)、Summary
- 保存/取消

4) Reference Links（右栏下半）
- 列表：from→to + reason + 删除
- 添加：选择目标节点 + reason（可空）
- Auto Connect：按钮触发（沿用现有能力/简单兜底）

## 页面 4：工作台页（Workspace）
### Meta Information
- title: DeepSlide – 工作台
- description: 编辑 LaTeX、编译预览并用 AI 迭代

### Page Structure
- 三栏：左文件树（240）/ 中编辑器（自适应）/ 右预览（420）。

### Sections & Components
1) Left：FileTree
- 搜索（可选）；点击加载文件；当前文件高亮。

2) Center：Editor
- 顶部：文件名 + 保存状态；按钮：保存、编译
- 内容：代码编辑区（现状基础上保持）

3) Right：Preview Panel
- 预览图列表或分页；编译错误以 panel 显示（可复制）。

4) Bottom：AI Command Input
- 单行输入 + 发送；loading 时展示“Thinking…”；结果通过刷新预览体现。

---
该设计以“少层级、少动效、强信息密度、明确主 CTA”为准则，优先保证上传→对话→逻辑链→工作台的连续体验。
