---
name: "deepslide-openclaw"
description: "Installs and deploys DeepSlide, and enables Docker-based TeX compilation. Invoke when setting up DeepSlide, starting/stopping services, or compiling LaTeX without local TeX."
---

# DeepSlide (OpenClaw) Skill

本 Skill 提供两类能力：
- 安装/初始化 DeepSlide（代码在宿主机运行），同时准备 **Docker 版 TeX 编译环境**（不依赖本机 TeX）。
- 部署/运行 DeepSlide（启动、健康检查、停止），便于在 OpenClaw 工作区中一键拉起服务。

## 触发场景（何时调用）

- 用户说“安装/初始化/跑起来 DeepSlide”
- 用户说“部署/启动/停止 DeepSlide 服务”
- 用户说“本机没装 TeX / xelatex，仍希望编译 PDF”
- CI/服务器环境需要“代码本机跑，但 TeX 编译走 Docker”

## 前置约束

- 不要在输出里打印或回显任何 API Key；密钥只通过环境变量或 `.env` 提供。
- 不要自动运行 `deepslide/clear.sh`。
- 默认假设当前工作目录是仓库根目录（包含 `deepslide/`、`container/`）。

## 能力 1：安装/初始化（含 TeX Docker）

### 1) 构建 TeX 编译镜像（仅用于 LaTeX 编译）

```bash
docker build -t deepslide:latest -f container/dockerfile .
```

如果你希望使用其它镜像名，设置环境变量：

```bash
export DEEPSLIDE_TEX_DOCKER_IMAGE="deepslide:latest"
```

### 2) 安装前端与 Next 服务依赖

```bash
cd next-ai-draw-io && npm install
cd ../deepslide/frontend && npm install
cd ../..
```

### 3) 安装后端依赖（推荐 venv）

```bash
cd deepslide/backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cd ../..
```

### 4) 配置模型与端口

编辑 `deepslide/.env`，变量说明见 `deepslide/env.md`。

## 能力 2：部署/运行（OpenClaw 友好）

### 启动

```bash
cd deepslide
bash start.sh
```

默认端口（可在 `.env` 覆盖）：
- Frontend: `http://127.0.0.1:5173`
- Backend API: `http://127.0.0.1:8001/api/v1`
- Backend Docs: `http://127.0.0.1:8001/docs`
- next-ai-draw-io: `http://127.0.0.1:6002`

### 健康检查（建议）

```bash
curl -fsS "http://127.0.0.1:8001/docs" >/dev/null
curl -fsS "http://127.0.0.1:5173" >/dev/null
curl -fsS "http://127.0.0.1:6002" >/dev/null
```

### 停止

```bash
cd deepslide
bash stop.sh
```

## Docker TeX 编译说明（关键能力）

DeepSlide 后端会通过 `run_in_docker.sh` 在 Docker 中执行 `xelatex/bibtex`，并将宿主机 `deepslide/` 目录挂载到容器的 `/app`，从而做到：
- 代码与服务仍在宿主机运行
- LaTeX 编译链路（TeXLive/字体/依赖包）全部在 Docker 里完成

当你遇到 “xelatex not found / LaTeX 编译失败但本机未安装 TeX” 时：
- 确认镜像已构建：`docker image ls | grep deepslide`
- 确认当前用户可直接运行 docker（无需 sudo）
- 必要时设置：`DEEPSLIDE_TEX_DOCKER_IMAGE`

## OpenClaw 加载提示

OpenClaw 默认会加载 `<workspace>/skills`。如果你的 OpenClaw 工作区不是仓库根目录，可将本 Skill 所在目录加入 `skills.load.extraDirs`，指向：
- `skills`
