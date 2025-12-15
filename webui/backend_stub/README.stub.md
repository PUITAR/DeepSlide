前后端本地开发环境配置（一步一步）

1. 准备 Python 环境
- 建议使用 conda 环境，例如名称为 `deepslide`
- 安装后端依赖（任选其一）
  - conda：`conda install -n deepslide -c conda-forge fastapi uvicorn`
  - pip：`pip install fastapi uvicorn`
- 激活环境：`conda activate deepslide`

2. 安装 Node.js（用于前端）
- 需要 Node.js ≥ 18，npm ≥ 9
- 使用 conda 安装（推荐）：`conda install -n deepslide -c conda-forge nodejs=18`
- 验证版本：
  - `node -v` 显示 `v18.x`
  - `npm -v` 显示 `9.x/10.x`

3. 启动后端占位服务（Stub）
- 位置：`webui/backend_stub/server.py`
- 启动：`python -m uvicorn webui.backend_stub.server:app --host 0.0.0.0 --port 8001`
- 访问：`http://localhost:8001/`
- 已提供接口：
  - `POST /api/chat` 接收表单与文件，返回 `session_id` 与上传文件 URL
  - `POST /api/cancel/{session_id}` 取消当前会话
  - `GET /api/status/{session_id}` 返回阶段进度（`rag/summary/plan/generate`）
  - `GET /api/result/{session_id}` 在约 6 秒后返回结果，含 `ppt_url` 或 `poster_url`（占位图片）与 `slides` 数组
  - 静态目录：`/uploads`、`/outputs`

4. 安装并启动前端
- 进入目录：`cd /home/ym/DeepSlide/webui/frontend`
- 安装依赖：`npm install`
- 启动开发服务器：`npm run dev`
- 访问：`http://localhost:5173/`

5. 代理配置说明
- 文件：`webui/frontend/vite.config.js`
- 代理到后端：`/api`、`/uploads`、`/outputs` → `http://localhost:8001`
- 若后端端口变化，请在该文件中同步修改 `target`

6. 端到端操作流程
- 步骤：
  - 先启动后端占位服务（端口 `8001`）
  - 再启动前端（端口 `5173`）
  - 在页面上传 PDF 或文档，点击生成
  - 前端会轮询 `/api/status/{session_id}`，约 6 秒后从 `/api/result/{session_id}` 拉取结果
  - 可看到占位的下载链接（图片 URL 充当 `ppt_url` 或 `poster_url`），以及 slides 预览

7. 常见问题与排查
- Node 版本过低：若看到 `SyntaxError: Unexpected token {`，通常是 Node < 12/14 的问题，升级到 Node 18（见第 2 步）
- 端口占用：
  - 后端默认 `8001`，请关闭占用端口的程序或改用其他端口
  - 前端默认 `5173`，若被占用，Vite 会自动使用下一个可用端口
- 跨域与代理：请确保通过前端代理访问后端（使用相对路径 `/api/...`）
- 会话冲突（真实后端）：当返回 `409` 表示有其他会话正在运行，等待完成或取消当前会话
- 结果未就绪：`/api/result/{session_id}` 返回 `202` 表示仍在处理中，前端会继续轮询

8. 切换到真实后端（可选）
- 位置：`Paper2Slides/api/server.py`
- 直接启动：`python Paper2Slides/api/server.py 8001`
- 或使用脚本：`Paper2Slides/scripts/start.sh`（同时启动后端与前端，注意端口日志）
- 前端代理依旧指向 `http://localhost:8001`

