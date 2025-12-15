数据集爬取说明

- 入口脚本：`scripts/arxiv_dataset.py`
- 默认抓取：`cv=3`、`nlp=3`、`optimization=4`
- 类别映射：`cv -> cs.CV`、`nlp -> cs.CL`、`optimization -> math.OC`
- 输出结构：
  - `data/<category>/<arxiv_id>/` 解压后的LaTeX源码
  - `data/<category>/<arxiv_id>.tar.gz` 源码包
  - `data/metadata.json` 抓取元数据列表

使用示例

- 运行默认配置：`python3 scripts/arxiv_dataset.py`
- 自定义数量：`python3 scripts/arxiv_dataset.py --cv 3 --nlp 3 --optimization 4`
- 调整抓取节奏：`python3 scripts/arxiv_dataset.py --delay 1.0`
- 不跳过已存在样本：`python3 scripts/arxiv_dataset.py --no-skip`

 容器环境（Docker）

 - 配置位置：所有容器相关文件位于 `container/` 目录。
 - 环境模板：复制 `container/.env.template` 为 `container/.env` 并填写变量（见下）。
- Python 依赖：见 `requirements.txt`，包含 `openai`。
- LaTeX 工具：镜像安装 `xelatex` 相关包，支持 `beamer` 编译。

DeepSlideBase 使用


- 构造参数：`DeepSlideBase(project_name, reference_path, template_path, workspace_root, llm_api_key)`
- 传入 `llm_api_key` 或通过环境变量 `OPENAI_API_KEY`，在 `plan(prompt)` 时调用大模型生成章节内容并覆盖 `recipe/content.tex`；`run()` 编译为 `project_name.pdf`。

模型与提供商配置

 - 通用环境变量：`LLM_PROVIDER`、`LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`
 - DeepSeek 示例：在 `container/.env` 设置 `LLM_PROVIDER=deepseek`、`LLM_API_KEY=你的key`、`LLM_BASE_URL=https://api.deepseek.com`、`LLM_MODEL=deepseek-chat`
 - OpenAI 示例：在 `container/.env` 设置 `LLM_PROVIDER=`（留空）、`LLM_API_KEY=你的key`、`LLM_MODEL=gpt-4o-mini`
 - 也可在 `DeepSlideBase.plan(prompt, llm_model, llm_base_url)` 运行时指定模型与地址。

 环境变量说明（container/.env）

- `PLATFORM`: 运行平台（如 `linux/amd64`）
- `CMD`: 容器启动命令（默认运行 `scripts/test_deepslide_base.py`）
- `LLM_PROVIDER`: 选择 `deepseek` 或留空使用 OpenAI
- `LLM_BASE_URL`: 自定义 LLM API 地址（DeepSeek 默认 `https://api.deepseek.com`）
- `LLM_MODEL`: 模型名称（示例：`deepseek-chat`、`gpt-4o-mini`）
 - `LLM_API_KEY`: 通用密钥（兼容不同提供商）
- `WORKSPACE_ROOT`、`REFERENCE_PATH`、`TEMPLATE_PATH`: 项目内路径（容器内 `/app`）

Docker 镜像构建

#!/bin/bash
查看容器(包括已停止的)
```bash
docker container ls -a
```

# 构建镜像
```bash
docker build -t deepslide:latest -f container/dockerfile .
```

# 停止并清理已存在的容器
```bash
docker stop deepslide-container
docker rm deepslide-container
```

# 创建并启动容器
```bash
docker run -d --name deepslide-container \
  --runtime=runc --env-file container/.env -v "$(pwd)":/app deepslide:latest tail -f /dev/null
```

# 执行测试
```bash
docker exec deepslide-container bash -lc \
"python3 -m venv /opt/venv &&\
 source /opt/venv/bin/activate &&\
 python3 scripts/test_deepslide_base.py"
```

# 关闭容器（可选）
```bash
docker stop deepslide-container
```