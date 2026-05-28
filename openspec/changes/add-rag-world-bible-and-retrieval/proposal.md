## Why

`add-rag-srd-ingest` 已经把 SRD 入 Chroma + SQLite 的链路打通（chunk schema、embedding provider 解耦、CLI search 可演示）。Phase 1 还差两块：

- **1b 世界观文档接入**：用户上传 Markdown → 异步解析切块 → 入库；项目级隔离
- **1c 混合检索 + 调试 UI**：Vector + BM25 + metadata filter 合并加权；`/retrieve` API；前端 Knowledge 页

本 change 把 1b 与 1c 一并交付——它们共用同一套 retriever 抽象，分开做反而会让 retrieve API 在 1b 阶段缺真实的 lore 数据可测。

## What Changes

- 引入世界观文档接入流水线：`POST /projects/{id}/sources` 接收 Markdown 上传 → `BackgroundTasks` 异步触发解析（Docling）→ heading-aware 切块（500–1000 token，无重叠）→ 复用 `add-rag-srd-ingest` 的入库链路写入 Chroma 与 SQLite，metadata 含 `project_id`
- 实现 `Source` 状态机：`uploaded → parsing → chunking → embedding → indexed`，失败入 `failed` + `last_error`；`GET /projects/{id}/sources/{source_id}` 暴露轮询
- 引入混合检索：Vector（Chroma top 20）+ BM25（`rank_bm25` 内存索引，启动期从 SQLite 重建，支持 `add_chunks` / `remove_chunks` 增量）+ metadata 过滤（`source` / `chunk_type` / `cr_range` / `tags` / `project_id`）；按 `config/retrieval.yaml` 的 stage 维度加权合并；reranker 接口预留，默认 no-op
- 新增 `POST /projects/{id}/retrieve` API：请求体 `{query, top_k?, stage?, filters?}`，响应含 chunk 全字段；`project_id` 强制软隔离（lore 仅本项目可见、SRD 全局可见）
- 新增前端 Knowledge 调试页：query 输入 + 过滤控件（source/chunk_type/cr_range/stage）；命中结果列表展示 score、metadata
- 依赖补齐：`docling`、`rank-bm25`、`python-multipart`；后端启动 lifespan 中初始化 BM25 retriever

## Capabilities

### New Capabilities

- `world-bible-ingest`: 接收用户上传的世界观 Markdown，异步解析切块入库，状态机持久化
- `hybrid-retrieval`: 提供 `/retrieve` API，组合向量 + BM25 + metadata 过滤，按 stage 加权产出 top-k

### Modified Capabilities

- `srd-ingest`: 不修改（本 change 仅消费其建立的 chunk schema 与入库链路）

## Impact

- **代码**：
  - `services/rag/parsers/markdown_parser.py`、`services/rag/chunkers/lore_chunker.py`
  - `services/rag/retriever/{vector,bm25,filters,hybrid}.py`、`reranker.py`
  - `apps/api/app/routers/{sources,retrieve}.py`、`apps/api/app/main.py` 注册路由 + lifespan
  - `apps/web/app/knowledge/page.tsx`
  - `services/rag/config.py` 加载 `config/retrieval.yaml`
- **依赖**：`docling`、`rank-bm25`、`python-multipart`
- **配置**：`config/retrieval.yaml` 含 `default` 与 `world_audit` 两个 stage 的 vector/bm25/source 权重
- **存储**：`data/uploads/{project_id}/`、`data/parsed/{project_id}/` 启用；`sources` 表开始写入
- **下游**：Phase 2 `build_context` 节点直接消费 `/retrieve`；Artifact 的 `input_context_ids` 开始写入 chunk id

## TODO

> 此 change 由原 `add-rag-layer-phase1` 拆分而来；细化 tasks 与 spec 待 1a archive 后启动。当前文件仅作 1a archive 时的承接占位。
