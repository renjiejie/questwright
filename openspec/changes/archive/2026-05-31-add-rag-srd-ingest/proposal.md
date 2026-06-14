## Why

Phase 0 骨架已落地（FastAPI、SQLite、Provider 抽象、LangGraph 最小图、Artifact CRUD），但工作流目前没有可检索的世界观与规则上下文。Phase 1 把"知识层"分三段做：

- **1a (本 change)**：SRD 知识接入 + CLI 检索演示，建立 chunker / embedding / Chroma + SQLite 双写的基础流水线
- **1b (后续 change)**：用户上传世界观文档的异步 ingest，复用 1a 的入库链路
- **1c (后续 change)**：混合检索 API（vector + BM25 + metadata 过滤）+ 前端 Knowledge 调试页

本 change 只覆盖 1a：让 25 份 5e-database JSON 一键 reindex 入 Chroma，并通过 CLI `search` 子命令可演示检索质量。

> 注：本 change 由原 `add-rag-layer-phase1` 重命名收窄而来；原 change 试图一次覆盖 §1–§13 全部 phase1 任务，但实施过程中（cursor 做到 §6 后中断）已出现 embedding provider 解耦等设计调整，且 1b/1c 未启动。沿用一锤子 change 会让 spec 与实现长期失真，故拆开归档：1a 单独收尾、archive，1b/1c 各自独立 change。

## What Changes

- 引入 SRD 知识接入流水线：从 `vendor/5e-database/src/2014/en/*.json` 读取 25 份分类 JSON，按 category 归一化为 `RawSrdRecord` → `RagChunk` → embedding → Chroma `dnd_rag` collection；同步写 SQLite `rag_chunks` 表
- 新增 CLI 工具 `python -m services.rag.cli`：`load-srd --dry-run`、`reindex-srd`、`search "<query>"` 三个子命令，支撑 Phase 1a 的离线验收
- 新增数据库表 `sources`（项目级文档源元信息，给 1b 用）以及对 `rag_chunks` 表的列扩展（`project_id`、`canon_level`、`source_ref`、`metadata` JSON、`chunk_text`），通过 Alembic 增量迁移；本 change 只写入 SRD 数据，`project_id` 留空表示全局 SRD
- Embedding Provider 与 Chat LLM 解耦：新增 `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` / `EMBEDDING_DIM` 四个独立配置；`OpenAIEmbedding` 适配 OpenAI-compatible 网关（如阿里百炼 DashScope `text-embedding-v4`）并通过 `dimensions` 参数对齐 chroma collection 维度
- 扩展 `.env.example`：补齐 embedding 独立配置项与 SRD 入库相关参数（`CHROMA_COLLECTION`、`EMBEDDING_BATCH_SIZE` 等）

## Capabilities

### New Capabilities

- `srd-ingest`: 从本地 5e-database JSON 文件读取 SRD 内容，归一化、分块、生成 embedding，并写入 Chroma 与 SQLite

### Modified Capabilities

<!-- Phase 0 仅落了骨架（artifact CRUD、healthz、provider 抽象），尚未冻结成 spec，故无既有能力需要 delta；本次变更全部走"新增能力"路径 -->

## Impact

- **代码**：
  - 新增 `services/rag/` 下 `srd_loader.py`、`chunkers/` 包（按 category 一文件一 chunker + registry）、`embed.py`、`index.py`、`cli.py`、`schemas.py`、`config.py`
  - `services/db/models.py` 扩展 `RagChunk`，新增 `Source` 模型；新增 Alembic 迁移
  - `services/providers/embedding.py` 参数化 `OpenAIEmbedding`（`base_url` / `model` / `dim` / `send_dimensions`）
  - `apps/api/app/config.py` 加 `EMBEDDING_*` 字段
- **依赖**：`pyproject.toml` 新增 `chromadb`、`pyyaml`（其余 `rank-bm25` / `docling` / `python-multipart` 等留到 1b/1c）
- **外部资源**：约定 `vendor/5e-database` 通过 `make srd-update`（git clone --depth 1）维护，进 `.gitignore`，路径由 `SRD_DATA_PATH` 指定（开发者可指向仓库外的位置）
- **存储**：本地 `./data/chroma/` 出现 `dnd_rag` collection；`rag_chunks` 表写入 ~2300 行 SRD chunk
- **下游**：1b world-bible ingest 复用 §5 的 chunk 入库逻辑；1c retrieve API 复用 chroma collection 与 metadata schema
- **不变项**：Artifact 永不原地改的不变量、LangGraph checkpoint 与业务 DB 隔离的约定保持不变
