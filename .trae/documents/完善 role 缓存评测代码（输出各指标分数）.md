## 目标
- 在不改动/不影响现有 `experiments/main` 评测代码与产出的前提下，新增一套 role 评测代码：读取 `experiments/.cache/role`，输出各指标分数（scores.csv / metrics_long.csv / details.jsonl / systems.csv）。

## 约束
- main 的代码与路径行为保持完全不变。
- deepslide 结果常为 `deepslide.zip`：需解压并使用 `recipe/base.pdf` 作为 slide；`recipe/speech.txt` 作为 notes（注入到评测用的 deck notes）。

## 实施步骤

## Step 1：新增独立目录 `experiments/role/`
- 复制 `experiments/main` 的评测框架到 `experiments/role`（避免改动 main）：
  - `experiments/role/run_eval.py`
  - `experiments/role/run_oneclick.py`
  - `experiments/role/deepslide_eval/`（作为独立包，不复用 main 版本）
- 将 `experiments/role/deepslide_eval/paths.py` 修改为：
  - `outputs_cache_root = repo_root/experiments/.cache/role`
  - `outputs_root = repo_root/experiments/role/outputs`
  - 其它保持与 main 一致（dataset_cache_root 仍指向 `dataset/.cache`）

## Step 2：实现 role 专用 manifest（扫描 `.cache/role`）
- 在 `experiments/role/deepslide_eval/manifest.py` 中实现 `scan_outputs_cache()` 的 role 版逻辑：
  - 第一层目录视为 `domain=role_name`
  - role/crolee 下收集 `*.pptx/*.pdf` 作为各系统输出（system=文件名 stem）
  - deepslide：
    - 若存在 `crolee/deepslide/recipe/base.pdf` 直接用
    - 否则若存在 `crolee/deepslide.zip`：解压到 `experiments/role/outputs/caches/role_unzipped/<hash>/`，并在解压目录内定位 `**/recipe/base.pdf`
  - 输出 `OutputArtifact` 的 `instance_id` 统一构造为 `f"{role_name}/{paper_id}"`

## Step 3：让 scan 阶段显式指定 source paper（避免 role 路径不含 paper_id）
- 在 `experiments/role/run_eval.py scan` 增加参数二选一：
  - `--source-pdf /abs/path/to/paper.pdf`（推荐）
  - 或 `--paper-id 2602.02475v1`（自动从 `dataset/.cache` 定位对应 paper.pdf）
- scan 时生成 `manifests/dataset.jsonl`：为每个 role 生成一条 `DatasetInstance`，都指向同一个 `paper_pdf_path`。

## Step 4：复用现有 pipeline 计算与输出格式
- `experiments/role/deepslide_eval/pipeline.py` 基本保持与 main 一致，确保输出：
  - `scores.csv`（每实例每系统各指标）
  - `metrics_long.csv`（长表）
  - `details.jsonl`（细节）
  - `systems.csv`（系统级聚合，含 S_Artifact/S_Delivery）
- deepslide notes 注入：复用 `_inject_deepslide_speech_notes`（读取 base.pdf 同目录 speech.txt）。

## Step 5：验证
- 先对单个 role + 单个系统跑通：`evaluate --limit 1 --systems deepslide`（或任一系统）
- 再全量跑 role 全部输出，确认 `systems.csv` 中每个系统均有聚合值。

## 产物位置
- 输出写入：`experiments/role/outputs/`（不与 main 混用）。

如果你认可以上方案，我将按这个步骤开始落地实现并跑通一次最小验证。