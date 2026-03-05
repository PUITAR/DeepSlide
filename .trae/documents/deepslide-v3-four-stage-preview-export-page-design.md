# DeepSlide v3（桌面优先）页面设计规范：四阶段导航 + 预览阶段 + 导出

## 全局设计（Global Styles）
- Layout：整体 Flexbox + 局部 Grid；8px spacing scale；桌面优先（>=1024 三栏/两栏布局）。
- 色彩 Tokens：bg #F8FAFC、surface #FFFFFF、text #0F172A、secondary #64748B、primary #2563EB、border #E2E8F0、danger #DC2626。
- 字体：系统字体；字号：H1 24/H2 18/body 14/caption 12。
- 组件状态：
  - Primary Button：hover 加深；disabled 40% 透明。
  - 输入框：focus ring-2 primary；error border-danger + hint。
- 动效：仅 150–200ms ease-out（hover、弹层、加载骨架）。

## 全局组件：四阶段 Stepper（所有阶段页顶部固定）
- 结构：左侧项目名；中部 Stepper（1 上传解析 / 2 需求对话 / 3 逻辑链 / 4 预览导出）；右侧“回退/下一步（若适用）”。
- 规则：
  - 只允许点击已完成阶段回退；当前阶段高亮。
  - 回退前若有未保存编辑（逻辑链/编辑模式）：弹窗确认“保存并回退 / 放弃更改 / 取消”。
  - 回退导致阶段四结果可能过期时：在阶段四顶部显示“预览已过期，需重新生成”。

---

## 页面 1：上传与解析页
### Meta
- title：DeepSlide – 上传与解析
- description：上传论文 LaTeX 工程并自动解析结构

### Page Structure
- 居中单列卡片（max-w 560）；解析完成后在同页下方出现摘要区。

### Sections & Components
1) Upload Card
- Dropzone + 文件信息行（文件名/大小/更换）
- 进度条 + 可取消
- Primary CTA：开始解析

2) Analysis Summary（解析完成出现）
- Main TeX / Abstract / Outline 三块信息卡
- CTA：进入需求对话

---

## 页面 2：需求对话页（阶段二：含“无反馈排查”）
### Meta
- title：DeepSlide – 需求对话
- description：通过对话确认受众、时长与重点

### Page Structure
- 上：Stepper
- 中：消息流（可滚动，底部留输入栏高度）
- 下：输入栏（sticky）

### Sections & Components
1) Message List
- assistant 左 / user 右；assistant 支持 Markdown；长回复折叠“展开”。

2) Input Bar
- 左：发送/录音入口（若已有）；中：输入框（Shift+Enter 换行）；右：发送按钮
- 发送中：禁用输入并显示 spinner

3) 生成状态条（用于无反馈/无反应排查）
- 触发：发送/确认后 N 秒无新消息或无状态变化
- 展示：计时、当前动作（发送/确认/生成）、可见阶段（排队/生成中/超时）
- 操作：一键重试、取消、重新连接（拉取 history + status）
- 诊断抽屉：错误码/简述、requestId、projectId、耗时、复制按钮

---

## 页面 3：逻辑链编辑页（阶段三）
### Meta
- title：DeepSlide – 逻辑链编辑
- description：调整讲述顺序与引用关系

### Page Structure
- 左右两栏：左 Timeline 列表（360）；右 Node 详情（自适应）。

### Sections & Components
1) Timeline List
- 节点卡：序号、标题两行省略、时长步进（±1）、更多（编辑/删除）
- Drag handle 仅把手可拖；拖拽态浮起阴影

2) Node Details + References
- 表单：Title/Type/Duration/Summary
- References：from→to 列表、删除、添加；“自动推荐连线”

3) Footer CTA
- Primary：生成预览（进入阶段四）
- Secondary：回退到需求对话

---

## 页面 4：预览与导出页（阶段四工作台，新增预览阶段与导出选项）
### Meta
- title：DeepSlide – 预览与导出
- description：查看初稿预览并导出交付物

### Page Structure
- 默认“预览模式”两栏：左缩略图列表（280）+ 右大预览（自适应）。
- 顶部工具条：导出、重新生成、（可选）切换到编辑模式。

### Sections & Components
1) Preview Status
- generating：骨架 + 进度文案 + 取消/重试
- failed：错误摘要 + 查看日志（折叠面板）+ 回退到阶段三
- ready：显示更新时间与当前版本提示

2) Slides Preview
- 左：缩略图滚动；右：当前页大图/分页

3) Export Panel（弹层/右侧抽屉）
- 选项：导出 PDF / 导出图片包 / 导出工程 zip
- 每项：说明 + 文件大小预估（若可得）+ 导出按钮
- 导出中：进度与取消；完成后提供下载链接

4) Edit Mode（同页可选切换）
- 三栏：文件树（240）/ 编辑器（自适应）/ 预览（420）
- 顶部：保存、编译、返回预览模式
- 编译错误：右侧预览上方错误列表（可复制）
