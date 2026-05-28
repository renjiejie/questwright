## Context

Phase 0 已经把 FastAPI、SQLite、Provider 抽象层、LangGraph 最小图、Artifact CRUD 落到了主仓库（详见 `apps/api/`、`services/db/`、`services/providers/`、`services/workflows/`）。Phase 1a 要在这层骨架上补出"SRD 知识入库"：让 25 份 5e-database JSON 可被一键 reindex 入 Chroma + SQLite，并通过 CLI `search` 子命令离线验收检索质量。后续 1b（world-bible ingest）/ 1c（hybrid retrieval API）会复用本 change 建立的 chunk schema、入库链路与 metadata 字段约定。

约束：

- 不引入 docker / MongoDB / 外部 5e-srd-api 服务，SRD 走本地 JSON 文件。
- LangGraph checkpoint 与业务 DB 隔离的约定（设计草案 §18.4）必须保留——RAG 写入 `rag_chunks` 走业务 DB，不污染 checkpoint 库。
- Embedding 走 Provider 抽象（`services/providers/embedding.py`），不直接 import openai SDK。
- Artifact 永不原地改的不变量沿用 Phase 0；本次只新增 `sources` 表和扩展 `rag_chunks`。

## Goals / Non-Goals

**Goals:**

- 让 25 份 SRD JSON 可一键 reindex 入 Chroma，CLI 检索可演示。
- 建立 chunk schema 与入库链路，1b/1c 直接复用。
- Embedding provider 与 chat LLM provider 解耦，可独立配置 base_url / api_key / model / dim，能跑在 OpenAI-compatible 网关（含国内厂商的兼容端点）上。
- 保持幂等：reindex SRD 不产生重复行；同一 `chunk_id` upsert 覆盖。

**Non-Goals:**

- 用户上传文档的 ingest（属于 1b）。
- BM25、混合检索、retrieve API（属于 1c）。
- 前端 Knowledge 调试页（属于 1c）。
- PDF 解析、chunk 重叠、reranker 实现、结构化 canon facts 抽取（更晚的 phase）。
- LangGraph 节点接入：`build_context` / `audit_artifact` 等节点是 Phase 2 工作。

## Decisions

### 决策 1：SRD 走本地 JSON 文件而非 5e-srd-api

**选择**：`vendor/5e-database/src/2014/en/*.json`（或 `SRD_DATA_PATH` 指向的任意目录），通过 `make srd-update` 维护。

**为什么**：

- 5e-database 仓库内的 JSON 字段已经规整、与 5e-srd-api 返回一致，无需 PDF 解析、heading 提取、CR/法术属性人工标注。
- 不需要 docker、MongoDB、REST 服务，纯文件读取，离线可工作。
- 用户已确认网络仅做一次性 `git clone --depth 1`。

**替代方案**：

- 起 5e-srd-api docker：增加运维负担、CI 复杂度，收益为零。
- 自己解析 SRD PDF：标注成本极高，且 5e-database 已经做完。

### 决策 2：Chroma `PersistentClient` 本地化，单 collection `dnd_rag`

**选择**：所有 chunk（SRD，未来 + 世界观）共用一个 collection，靠 metadata `source` / `project_id` 区分。

**为什么**：

- 单 collection 让混合检索逻辑简单；filter on metadata 在 Chroma 中开销低。
- 如果按 project 分 collection，会触发跨 collection 合并的复杂度，并阻碍 SRD 在多项目共享。
- `project_id` 留空表示"全局 SRD"，与未来 lore（必有 `project_id`）天然区分。

**替代方案**：

- 每个 project 单独 collection：迁移成本未来可加，目前不必。
- pgvector：生产时切换的理想目标，但 SQLite/MVP 阶段不引入 PG 依赖。

### 决策 3：每个 SRD category 一个 chunker 文件 + registry

**为什么**：

- 不同 category 的字段差异大（monster 的 statblock vs spell 的 level/school/components vs class 的 features），单一 chunker 会写成大 if/else。
- 每个 chunker 独立测试（typical / 边界 / 空字段）覆盖更全。
- registry 让"新增 category"只需新增一个 chunker 文件并注册，不动调用方。

### 决策 4：chunk text 字段是合成自然语言，不直接塞 JSON

**为什么**：embedding 模型对 JSON 的语义理解远差于自然语言；对照实测：用 `{name} (CR {cr}). AC {ac}, HP {hp}. Actions: {actions_text}` 模板比直接 `json.dumps(record)` 召回好得多。
模板按 category 写在 chunker 里，便于针对性优化。

### 决策 5：Metadata 过滤字段固定白名单

**白名单**：`source`、`chunk_type`、`cr`、`spell_level`、`tags`、`project_id`。

**为什么**：

- Chroma 的 metadata filter DSL 表达能力有限，提前固定字段集合可避免后端 schema 漂移。
- chunker 里写 metadata 时按白名单挑选，未来 1c 接入 retrieval 时只需扩白名单。
- `tags` 序列化采用 `;` 分隔字符串（Chroma 不支持 list metadata），客户端做 contains 匹配。

### 决策 6：rag_chunks 表扩列 + 新增 sources 表，走 Alembic 增量迁移

新增 `sources(id, project_id, kind, original_filename, mime_type, byte_size, status, last_error, created_at, updated_at)`——本 change 不写入此表，仅建表给 1b 用。
扩 `rag_chunks` 列：`project_id`（NULL = 全局 SRD）、`source_ref`、`canon_level`、`metadata` JSON、`chunk_text`（1c BM25 用）、`source_id` 外键到 `sources`（SRD 留 NULL）。
**为什么单独 sources 表**：用户可能上传多份世界观（DLC/补遗），需要独立的状态机和 last_error 字段；放在 `rag_chunks` 上无法表达 ingest 中间态。
**为什么 1a 就建表**：避免 1b 启动时再做迁移导致 SRD 数据需要重新 reindex；表为空对 1a 无副作用。

### 决策 7：Embedding Provider 与 Chat LLM Provider 解耦

**选择**：embedding 独立配置 `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` / `EMBEDDING_DIM`；`OpenAIEmbedding` 适配器通过 `base_url` / `dim` / `send_dimensions` 三个新参数支持任何 OpenAI-compatible embedding 端点。

**为什么**：

- 实战中 chat LLM 与 embedding 的网关常常不同。本项目实测：用户的 `OPENAI_BASE_URL` 网关只代理 `/chat/completions`，不代理 `/embeddings`，调用时返回非 OpenAI 标准响应（顶层是 string），SDK 内部反序列化失败抛 `'str' object has no attribute 'data'`。
- chat 与 embedding 的成本结构、限速规则、地域可用性都不同，解耦后任一可独立切换不互相影响。
- 默认走阿里百炼 DashScope `text-embedding-v4`（OpenAI-compatible 端点），dim=1536 与 chroma collection 对齐；DashScope v4 默认 dim=1024，需要 `send_dimensions=True` 把 `dimensions` 参数透传给 `embeddings.create`。
- DashScope embedding 单批上限 10，与默认 batch_size=64 不兼容；本 change 把默认 batch_size 改为 10 以适配。后续若切回 OpenAI 官方可调回 64。

**替代方案**：

- 让 `OPENAI_BASE_URL` 同时代理 chat 与 embedding：受限于网关能力，不是项目可控。
- 引入 `EmbeddingProvider` 子类（如 `DashScopeEmbedding`）：DashScope 已经是 OpenAI-compat，复用同一个类更精简，未来真碰到不兼容的厂商再开新类。

## Risks / Trade-offs

- **[Risk] embedding 调用失败/限速**：reindex SRD 一次性 ~2300 次 embed，DashScope batch=10 时仍可能触发 rate limit。→ Mitigation：批量大小可配；失败重试 + 指数退避；CLI 支持断点续 indexing（按 `chunk_id` 跳过已存在的 embedding）。
- **[Risk] embedding 网关响应非标准**：第三方 OpenAI-compat 网关可能返回字符串或缺 `data` 字段的 JSON。→ Mitigation：`_extract_embedding_rows` 已经覆盖 object/dict/JSON-string 三种 shape，并在异常时抛带定位信息的 TypeError。
- **[Risk] Chroma metadata 类型限制**：Chroma 只支持标量 metadata，list 字段（`tags` / `section_path`）需序列化。→ Mitigation：`tags` 用 `;` 分隔字符串；`section_path` 仅落 SQLite。
- **[Risk] Embedding 维度迁移**：未来切换 embedding 模型时，新旧 chunk 不能混在同一 collection。→ Mitigation：换模型时建议改 `CHROMA_COLLECTION` 名（如 `dnd_rag_v4`）后重 reindex；或清空 `data/chroma/` 与 `rag_chunks` 表后重跑。本 change 文档化此操作，不做自动检测。
- **[Trade-off] Embedding 解耦 vs 单一配置**：解耦增加了 4 个 env 变量，但保留 `EMBEDDING_API_KEY` 留空 → 回退到 `OPENAI_API_KEY` 的兜底，降低了简单部署的负担。

## Migration Plan

1. **数据库迁移**：新增 Alembic revision，包含 `sources` 表创建与 `rag_chunks` 列扩展；`alembic upgrade head` 必须能在已有 Phase 0 SQLite 上无损执行。
2. **依赖安装**：`uv sync` 引入 `chromadb` / `pyyaml`。
3. **SRD 数据准备**：开发者首次运行需 `make srd-update`（或手动 `git clone --depth 1` 到任意目录后将 `SRD_DATA_PATH` 指过去）；CI 用打包好的 `5e-database-2014.tar.gz` fixture 跳过克隆。
4. **配置 embedding**：`.env` 填 `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` / `EMBEDDING_DIM`（默认值已对齐 DashScope `text-embedding-v4` + dim 1536）。
5. **首次 reindex**：手工 `python -m services.rag.cli reindex-srd`；DashScope batch=10 下约几分钟。完成后 `cli search "fire breathing dragon CR 10"` 验收。
6. **回滚**：删除 Chroma 目录与 `rag_chunks` 行（`DELETE FROM rag_chunks WHERE source IN ('monster_manual','phb','dmg','srd_misc')`），Alembic downgrade 到本 revision 之前；恢复到 Phase 0 状态无残留。

## Open Questions

- **大批量 embedding 的并发**：当前 `embed_texts` 是顺序 batch（每批 ≤ 10）。2300 chunk 顺序跑约几分钟可接受；若 1b 上传大文档（数千 chunk）还顺序跑，体验会变差。1b 实施时再决定是否引入并发。
- **Embedding 模型可观测性**：当前未记录 embedding 调用 cost / latency。Phase 4 引入 `llm_call_logs` 时考虑把 embedding 也纳入。
