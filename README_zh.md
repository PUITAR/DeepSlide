# DeepSlide: From Artifacts to Presentation Delivery

<div align="center">

[![Paper](https://img.shields.io/badge/paper-A42C25?style=for-the-badge&logo=arxiv&logoColor=white)]()    [![Github](https://img.shields.io/badge/DeepSlide-000000?style=for-the-badge&logo=github&logoColor=white)](https://github.com/PUITAR/DeepSlide)

Our detailed technical report will be published soon.

</div>

> DeepSlide 不是“帮你快速做一份 PPT”的工具，而是一个**面向完整演讲交付（delivery-first）**的人机协同系统。  
> 它帮助用户超越“出页”本身，覆盖完整演讲交付流程：**叙事规划、逻辑链编辑、页面生成、讲稿生成、交互增强与演练反馈**。

**🌐 English Version:** [README.md](./README.md)

---

<div align="center">

🎥 Bilibili: https://www.bilibili.com/video/BV1sSPkz9E6P

[![在 B 站观看演示视频](https://i0.hdslb.com/bfs/archive/bcfd3b7943d3c6bb5c58f6c5e205161978de359e.jpg@308w_174h)](https://www.bilibili.com/video/BV1sSPkz9E6P)

▶️ YouTube: https://youtu.be/NGqFLT81uHA

<!-- [![在 YouTube 观看演示视频](https://img.youtube.com/vi/NGqFLT81uHA/hqdefault.jpg)](https://youtu.be/NGqFLT81uHA) -->

</div>

## News
- **[2026.03.10] 我们提供了一个 4 步指南，支持在 OpenClaw 内直接使用 DeepSlide。**  
  如果你已经在使用 OpenClaw，并希望添加一个专用 Agent 来做 **演示文稿生成、叙事组织与演讲交付准备**，可以参考这个教程：  
  [DeepSlide + OpenClaw](https://www.yuque.com/puitar/pug2ub/didlfrgy5ogxzl6p?singleDoc# 《DeepSlide+龙虾直接接入飞书！》)
- **[2026.03.06] DeepSlide 正式开源发布。**  
  我们开源 DeepSlide 作为一个 **human-in-the-loop、delivery-first 的演讲交付系统**。  
  DeepSlide 不止做静态 deck 生成，还覆盖 **需求澄清、叙事提案、逻辑链控制、证据驱动生成、讲稿撰写、交互增强与演练准备**。

## OpenClaw Skill

我们提供一个 AgentSkills 兼容的 OpenClaw skill：`skills/deepslide-openclaw/`：
- 安装与初始化 DeepSlide（服务在宿主机运行）
- 使用 Docker 版 TeX 工具链编译 LaTeX（无需本机安装 TeX）
- 部署与运维（start/stop + 基本健康检查）

如果你的 OpenClaw workspace 不是仓库根目录，可以在 `~/.openclaw/openclaw.json` 里通过 `skills.load.extraDirs` 加入 `skills`。

## 核心观点

一个高质量演讲并不主要取决于静态页面是否“好看”，更取决于信息是否在**受众认知与注意力约束**下被组织与交付——包括叙事连贯性、控时与节奏、注意力引导，以及演练准备程度。换言之，**artifact 质量 ≠ delivery 质量**。

<p align="center">
  <img src="./assets/paper/comp.png" alt="Comparison with Existing Methods" width="95%"/>
  <br/>
  <em><strong>Figure 1.</strong> Comparison with existing methods: DeepSlide targets end-to-end presentation delivery rather than deck authoring only.</em>
</p>

---

## 四阶段端到端流程（delivery-first）

为此，DeepSlide 提出了一个 **四阶段端到端流程**：需求澄清与叙事提案 → 逻辑链编辑与证据驱动生成 → 交互增强与注意力控制 → 演练与评估。将演讲交付从 artifact 质量提升到 delivery 质量。

- **叙事策略可控**：生成多候选、可控时长（time-budgeted）的逻辑链，支持节点级编辑与强调分配  
- **讲稿与页面协同交付**：同时产出 `recipe/content.tex`（slides）与 `recipe/speech.txt`（script）  
- **讲中注意力策略**：基于内容的图像聚焦、表格可视化、文本图示化等可选增强  
- **演讲排练指导**：提供用户声线声音预览，以及模拟观众提问和建议  

---

## 四阶段框架

<p align="center">
  <img src="./assets/paper/overview-v4.jpg" alt="四阶段框架概览图" width="95%"/>
  <br/>
  <em><strong>Figure 2.</strong> 四阶段框架概览：从需求澄清到生成与增强，再到演练与评估的闭环交付流程。</em>
</p>

为了更好提供材料质量和演讲过程的双角度评估，我们开发了一个基于大语言模型的**双榜单评估榜单**，并与现存的一系列方法展开对比：

<p align="center">
  <img src="./assets/paper/main_exp_perf.jpg" alt="20个领域双榜单评测结果" width="95%"/>
  <br/>
  <em><strong>Figure 3.</strong> 20 个领域的双榜单评测结果（Artifact vs. Delivery）。</em>
</p>

<p align="center">
  <img src="./assets/paper/second_exp_perf.jpg" alt="各种角色混合双榜单评测结果" width="95%"/>
  <br/>
  <em><strong>Figure 4.</strong> 各种角色混合场景下的双榜单评测结果（Artifact vs. Delivery）。</em>
</p>

---

## 系统与要点

<p align="center">
  <img src="./assets/paper/ui-preview.jpg" alt="系统与要点概览图" width="95%"/>
  <br/>
  <em><strong>Figure 5.</strong> 系统界面与关键能力概览：逻辑链编辑、证据驱动生成、交互增强与演练闭环。</em>
</p>

---

## 核心理念

论文指出现有“幻灯片代理/生成器”通常只显著降低了 deck authoring 成本，但仍未覆盖完整的演讲准备负担，主要存在三类缺口：

- **缺少可选择、可编辑的叙事策略**：多数系统要么跳过叙事规划，要么只输出单一泛化大纲，弱个性化且不可控时长/强调分配  
- **缺少讲中注意力策略**：主要交付静态 deck，缺少内容感知的注意力引导机制（聚焦、渐进揭示、针对密集图表的表达编码）  
- **缺少演练支持**：止步于出页，缺少与页面对齐的非冗余讲稿、演练反馈、与现场应对（可能提问）准备  

DeepSlide 的方法论是：让演讲者只需锁定高层决策（受众、总时长、目标、风格意图、叙事骨架与强调分配），其余由系统在可控约束下自动落地，并形成可迭代的交付闭环。对应实现为四阶段：

- **Stage 1：需求澄清与叙事提案**：自由对话收集需求，输出多套 time-budgeted 逻辑链候选  
- **Stage 2：逻辑链编辑与证据驱动生成**：节点级编辑（重排/增删/改写/控时/交叉引用），检索材料证据并生成 slides + script  
- **Stage 3：交互增强与注意力控制**：提供内容感知的可选增强（聚焦、表格可视化、文本图示化、自动布局等）  
- **Stage 4：演练与评估**：听众视角演练（可选音频）、给出可执行修改建议，并一键导出交付产物  

---

## 系统架构与代码

核心代码在 `deepslide/`，运行时是三服务并行：

- `deepslide/backend`：FastAPI（材料解析/生成/编译/导出/评估入口）  
- `deepslide/frontend`：Vite + React（交互编辑、预览、对话入口）  
- `next-ai-draw-io`：Next.js（图示与 draw.io 相关能力）  

```text
DeepSlide/
├── deepslide/
│   ├── backend/
│   ├── frontend/
│   ├── env.md               # 模型/Agent 环境变量总览
│   ├── install.sh           # 依赖安装脚本（快捷）
│   ├── start.sh             # 一键启动三服务
│   ├── stop.sh              # 一键停止
│   └── clear.sh             # 清缓存/运行产物（危险：会删项目）
├── experiments/             # 论文评估复现（dual-scoreboard / 消融）
├── DeepSlide-Arxiv/         # 论文工程目录（图表、表格、latex）
├── assets/                  # README 等文档资源目录（从论文同步）
└── README_zh.md
```

---

## 环境要求

- Linux/macOS（推荐）  
- Python 3.10+（建议 3.12）  
- Node.js 18+（建议 20 LTS）  
- npm 9+  
- LaTeX（用于编译 Beamer：`xelatex` + beamer 相关包），强烈推荐本项目提供的 `container/dockerfile` 配置，无需本地安装 tex。

---

## 本地安装与启动（推荐）

### 0) Docker 运行

仓库提供 `container/dockerfile`，包含 TeXLive 与 Python 环境配置，您可以直接使用 docker 配置 tex 编译环境，免除本地安装 tex 的麻烦。用法：

```bash
docker build -t deepslide:latest -f container/dockerfile .

docker run -it --rm \
  -v "$(pwd)":/app \
  -p 5173:5173 -p 8001:8001 -p 6002:6002 \
  deepslide:latest bash
```

进入容器后在 `/app` 内按“本地安装与启动”步骤运行即可（或直接使用 `deepslide/start.sh`）。

### 1) 安装依赖

```bash
cd next-ai-draw-io
npm install
cd ..

cd deepslide/backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cd ../..

cd deepslide/frontend
npm install
cd ../..
```

也可以使用快捷脚本（仍建议先准备好 venv/权限）：`bash deepslide/install.sh`。

### 2) 配置模型与端口

编辑 `deepslide/.env`。模型变量的详细说明见：`deepslide/env.md`。

### 3) 一键启动

```bash
cd deepslide
bash start.sh
```

默认访问地址（端口可在 `.env` 改）：

- Frontend: `http://127.0.0.1:5173`  
- Backend API: `http://127.0.0.1:8001/api/v1`  
- Backend Docs: `http://127.0.0.1:8001/docs`  
- next-ai-draw-io: `http://127.0.0.1:6002`  

一键停止：

```bash
cd deepslide
bash stop.sh
```

---

## 配置：模型与端口

### 最小可运行配置

请将密钥替换为你自己的值，不要提交真实 key。

```bash
# 文本 LLM（默认）
DEFAULT_MODEL_PLATFORM_TYPE=openai
DEFAULT_MODEL_TYPE=gpt-4o-mini
DEFAULT_MODEL_API_URL=https://api.openai.com/v1
DEFAULT_MODEL_API_KEY=YOUR_API_KEY

# Dev Ports
BACKEND_PORT=8001
FRONTEND_PORT=5173
NEXT_AI_DRAWIO_PORT=6002
```

### Agent 级覆盖（推荐用法）

DeepSlide 支持为不同 Agent 配置不同 provider/model/base_url/api_key，以便简单任务用便宜模型、复杂任务用更强模型。完整字段与 Agent 列表见 `deepslide/env.md`。

---

## 运行脚本说明（start/stop/clear/install）

### `deepslide/start.sh`

- 读取 `deepslide/.env`  
- 启动三服务：`next-ai-draw-io`、后端 `uvicorn`、前端 `vite`  
- 写入 PID 到 `deepslide/.pids/`，便于停止与清理  

### `deepslide/stop.sh`

- 优先按 PID 文件停止  
- 兜底按进程特征停止（后端/前端/next-ai-draw-io）  

### `deepslide/clear.sh`（危险）

用于“重置运行态”，会清理缓存与运行产物（包含项目目录、上传内容、ASR/TTS 中间文件）。在你希望保留项目结果时不要运行。

### `deepslide/install.sh`

用于安装后端/前端/next-ai-draw-io 依赖的快捷脚本。

---

## 使用流程：从材料到演讲交付

1. 打开前端并创建项目  
2. 上传材料（论文 PDF / LaTeX zip / 多文档等）  
3. 完成需求澄清（受众、总时长、目标、风格偏好）  
4. 查看多候选叙事逻辑链并选择其一（可编辑控时与强调分配）  
5. 生成 slides + script：产出 `recipe/content.tex` 与 `recipe/speech.txt`  
6. 编译/预览并进行交互增强（聚焦、可视化、图示化、自动布局等）  
7. 进入演练闭环：预览指标、修改建议、可能提问模拟（Stage 4）  
8. 导出交付产物（PDF / PPTX / ZIP）  

---

## 实验与评估复现

论文评测在 `experiments/`，核心思想是 dual-scoreboard：区分静态材料质量（Artifact）与交付质量（Delivery）。

### 评测前置：安装评测依赖

建议单独创建评测 venv：

```bash
python3 -m venv experiments/.venv
source experiments/.venv/bin/activate
pip install --upgrade pip
pip install -r experiments/main/requirements.txt
```

### 评测前置：配置评测环境变量

复制并填写：

- `experiments/main/.env.template` → `experiments/main/.env`

其中包含：

- **LLM Judge**（评测指标打分用）  
- **OCR**（默认通过 VLM 做 OCR；可关闭）  

### 一键复现：主评测（main）

```bash
source experiments/.venv/bin/activate
python experiments/main/run_oneclick.py
```

输出一般位于 `experiments/main/outputs/`（scores / reports 等）。

### 一键复现：角色评测（role）

```bash
source experiments/.venv/bin/activate
python experiments/role/run_oneclick.py
```

### 消融评测（K/L/S）

消融实验评测入口在 `experiments/xr/run_eval.py`：

```bash
source experiments/.venv/bin/activate
python experiments/xr/run_eval.py scan
python experiments/xr/run_eval.py evaluate --judge llm --llm-mode packed
python experiments/xr/run_eval.py report
```

提示：

- 若你暂时不配置 OCR，可在 evaluate 时加 `--require-ocr 0` 或设置 `EVAL_OCR_MODE=off`（会影响包含 OCR 的指标）  
- 若你暂时不配置 LLM judge，可加 `--require-judge 0`（会跳过需要 judge 的指标）  

---

## 依赖组件说明（next-ai-draw-io / index-tts）

### next-ai-draw-io

`deepslide/start.sh` 会启动该服务。首次运行前务必在 `next-ai-draw-io/` 执行 `npm install`。

### index-tts（可选：语音预览/TTS）

后端的 TTS 逻辑会调用仓库内 `index-tts/index-tts-main`（并依赖 `uv` 命令）。若你需要语音预览能力，请先按 `index-tts/index-tts-main/README.md` 完成安装与模型准备，并确保 `uv` 在 PATH 中。

---

## 常见问题

- **前端连不上后端**：检查 `BACKEND_PORT` 与后端是否启动；查看 `deepslide/.pids/` 是否存在 PID 文件  
- **next-ai-draw-io 未启动**：确认 `next-ai-draw-io` 已安装依赖；端口默认 6002  
- **LaTeX 编译失败**：确认本机或容器内安装 `xelatex` 与 beamer 依赖；检查字体缺失问题  
- **评测报错缺少 OCR / Judge**：按 `experiments/main/.env.template` 配置 `EVAL_MODEL_*` 与 `DEFAULT_VLM_*`，或使用 `--require-ocr 0/--require-judge 0` 跳过  

---

## 交流

<table align="center">
  <tr>
    <td align="center">
      <img src="./assets/wechat.png" width="280" />
      <br/>
      <em>WeChat</em>
    </td>
    <td align="center">
      <img src="./assets/qq.png" width="280" />
      <br/>
      <em>QQ</em>
    </td>
  </tr>
</table>

---

## 论文与引用

```


```
