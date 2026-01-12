# Combine124

目标：仅运行顶层 `combine124/` 包，实现：
1) Streamlit 中用 chatter 多轮对话生成需求 JSON
2) 上传 `.tex` 文章
3) 调用 logicchain 输出 4 条逻辑链

> 注意：仓库中的 `chatter_yangming/`、`logicchain_zhiwei/` 仅作为参考，不参与运行。

## 安装

在 repo 根目录：

```bash
pip install -r combine124/requirements.txt
```

并准备 `.env`（二选一）：
- 方案 A：在 repo 根目录放 `./.env`
- 方案 B：设置环境变量 `COMBINE124_ENV_PATH=/path/to/.env`

`.env` 至少需要：
- `DEFAULT_MODEL_API_KEY`（或 `DEEPSEEK_API_KEY`）
- `DEFAULT_MODEL_API_URL`（可选，默认 https://api.deepseek.com）
- `DEFAULT_MODEL_TYPE`（可选，默认 deepseek-chat）

## 启动网页

```bash
streamlit run combine124/streamlit_app.py
```

网页按 3 步走：
1) 对话收集需求（点“生成/刷新 requirements JSON”）
2) 上传 `.tex`
3) 点击 “Generate Logic Chains”

## 冒烟测试（无 UI）

```bash
python -m combine124.smoke_test
```

## CLI（无 UI）

```bash
python -m combine124.backend path/to/article.tex path/to/requirements.json
```
