# deepslide-stage3 页面设计说明（Desktop-first）

## 全局设计（适用于全部页面）

### Layout

* 桌面优先：最小宽度建议 1200px；在 1024px 以下进入紧凑模式（侧栏可折叠、日志/AI 面板改为抽屉）。

* 主要采用 CSS Grid + Flexbox：外层 Grid 负责“侧栏/主内容/辅助面板”分区；内部模块用 Flex 做对齐与自适应。

### Meta Information

* 默认 Title 模式：`DeepSlide Stage3 - {页面名}`

* 默认 Description：`在本地项目上进行编辑、预览与 AI 调试。`

* Open Graph：

  * og:title 同 Title

  * og:description 同 Description

  * og:type = website

### Global Styles（Design Tokens）

* 颜色：

  * background: #0B1020（深色工作台背景）

  * surface: #111A33（卡片/面板）

  * border: rgba(255,255,255,0.08)

  * textPrimary: rgba(255,255,255,0.92)

  * textSecondary: rgba(255,255,255,0.65)

  * accent: #6EA8FF（主按钮/高亮）

  * danger: #FF5C7A（错误提示）

* 字体：

  * UI：系统字体栈；代码：`ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas`

  * 字号：12/14/16/20（日志与代码 12-13；正文 14；标题 16-20）

* 按钮：

  * Primary：accent 背景，hover 提亮 6%，disabled 降低不透明度

  * Secondary：surface 背景 + border

* 链接：accent 色；hover 下划线

* 动效：面板抽屉/折叠使用 160–220ms ease-out

***

## 页面 1：项目选择页（/）

### Layout

* 12 列 Grid：左 3 列为“源目录与过滤”，右 9 列为“项目列表”。

* 顶部固定 Header：产品名 + 当前源目录状态 + 设置入口。

### Page Structure

1. Header
2. 左侧栏（源目录与操作）
3. 主区（项目列表/最近项目）
4. 底部状态栏（扫描中/错误）

### Sections & Components

* Header

  * Logo/Title：DeepSlide Stage3

  * 右侧按钮：`设置`、`刷新扫描`

* 左侧栏：

  * 「项目源目录」卡片

    * 文本：显示 `DEEPSLIDE_PROJECTS_DIR` 当前值（过长截断，悬浮显示完整）

    * 按钮：`选择磁盘目录打开`（打开目录选择器）

  * 「过滤与搜索」

    * 输入框：按项目名/路径关键字过滤

    * 排序：最近修改 / 名称

* 主区：

  * 「最近项目」横向列表（最多 6 个）：卡片点击进入工作台

  * 「全部项目」表格/列表：

    * 列：项目名、路径（可折叠显示）、最后修改时间、操作（打开）

    * 空状态：提示检查目录权限或在设置中修改源目录

* 状态与错误：

  * 扫描中：显示进度条/旋转指示

  * 扫描失败：错误摘要 + 重试按钮

***

## 页面 2：工作台页（/workspace/:projectId）

### Layout

* 三栏布局（Grid）：

  * 左侧栏：文件树（可折叠，默认宽 280px）

  * 中间主栏：编辑器 + 预览（上下分屏，可拖拽分割条）

  * 右侧辅助栏：AI 调试 / 日志（Tab 切换，默认宽 360px，可折叠为抽屉）

* 顶部工具栏固定：保存、预览控制、快速搜索、设置入口。

### Page Structure

1. Top Toolbar
2. Body（左文件树 + 中编辑/预览 + 右AI/日志）
3. Bottom Status Bar（当前文件、保存状态、预览状态）

### Sections & Components

* Top Toolbar

  * 面包屑：项目名 / 当前文件

  * 按钮：`保存`、`全部保存`、`撤销/重做`

  * 预览控制：`启动/重启`、`打开预览`（新窗口）

  * 搜索：文件内搜索（Ctrl+F）/全局搜索（Ctrl+P 可选）

  * 入口：`设置`

* 左侧栏：文件树

  * 目录折叠、文件图标（按扩展名）

  * 搜索框：过滤文件名

  * 右键菜单（最小必要）：复制相对路径、在系统中打开（可选）

* 中间主栏：

  * 编辑器（Monaco）：

    * Tab：多文件标签

    * 保存提示：未保存时 Tab 显示圆点

    * 冲突提示：etag 不一致时提示“文件已变更，选择覆盖/重新加载”

  * 预览面板：

    * iframe/webview 区域展示预览

    * 顶部状态条：Running / Error

    * Error 时展示“错误摘要 + 查看日志”快捷按钮

* 右侧辅助栏（Tabs）

  * Tab1「AI 调试」

    * 上下结构：对话历史（可滚动） + 输入区

    * 输入区：多行输入、发送按钮、上下文选择（当前文件/选中文本/最近日志）

    * 输出卡片：原因分析、建议、补丁列表

    * 补丁操作：`预览变更`（diff 视图）、`应用`、`撤销`

  * Tab2「日志」

    * 工具条：复制、清空、过滤（info/warn/error）

    * 日志列表：等宽字体、按时间追加；错误行高亮 danger

* Bottom Status Bar

  * 左：当前文件路径

  * 中：保存状态（已保存/未保存/保存失败）

  * 右：预览 URL / 端口、预览状态

***

## 页面 3：设置页（/settings）

### Layout

* 单列居中（最大宽 920px），多卡片分组；右上角提供返回工作台/首页。

### Page Structure

1. Header（标题 + 返回）
2. 卡片区：项目源配置、AI 配置、预览/调试偏好

### Sections & Components

* 项目源配置卡片

  * 字段：Projects Directory（默认读取 `DEEPSLIDE_PROJECTS_DIR` 展示）

  * 操作：选择目录、保存、重新扫描

  * 校验：不可读/不存在时给出明确提示

* AI 配置卡片

  * 字段：Base URL、Model、API Key（密码框，仅显示是否已配置）

  * 操作：保存、连接测试（显示成功/失败原因）

  * 隐私提示：发送前确认开关（默认开启）

* 预览/调试偏好卡片

  * 预览：端口（自动/固定）、自动刷新开关

  * 调试：最大上下文大小（字符数/文件数上限）

* 危险操作区（如需）

  * 清除最近项目、重置设置

