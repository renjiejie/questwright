## Context

`add-rag-srd-ingest` 已交付 SRD 入库链路（chunk schema、embedding provider 解耦、Chroma + SQLite 双写、CLI search）。本 change 在此基础上补 Phase 1b（用户上传文档 ingest）与 Phase 1c（混合检索 API + 调试 UI），合并交付的理由是：1c 需要真实的 lore 数据才能完整测试跨项目隔离与 stage 切换，分开做会让 1b 阶段的 retrieve API 缺乏可验证场景。

约束沿用 1a：

- 不引入 docker / 外部服务，全部本地化。
- LangGraph checkpoint 与业务 DB 隔离的约定保留。
- Embedding 走 `add-rag-srd-ingest` 已建立的 provider 抽象，不新增 vendor 适配。
- Artifact 永不原地改的不变量沿用 Phase 0。

## Goals / Non-Goals

**Goals:**

- Markdown 文档可上传 → 异步 ingest → 状态可轮询 → retrieve 能召回。
- Vector + BM25 + metadata 过滤 + 加权合并的 `/retrieve` API 可用，stage 切换影响排序。
- 项目级软隔离：lore 仅本项目可见、SRD 全局可见；retriever 在 filter 入口强制注入 `project_id`。
- 前端 Knowledge 调试页支持 query + 过滤控件 + 结果详情展开，覆盖手动验收。

**Non-Goals:**

- PDF 解析（Docling 支持但调试成本高，留补丁；接口预留 `kind` 分发）。
- chunk 重叠（MVP 0 重叠；召回不足再加 100 token 重叠）。
- Reranker 实现（仅留接口）。
- 真队列异步任务（Phase 4 引入 LLM cost 控制时再切；本 change 用 FastAPI BackgroundTasks）。
- 结构化 canon facts 抽取（Phase 5 决策）。
- LangGraph 节点接入（Phase 2）。

## Decisions

### 决策 1：BM25 用 `rank_bm25` 内存索引，从 SQLite 重建

**为什么**：

- 规模 < 10k chunk 时内存够用；启动时一次构建，后续查询零 IO。
- 不引入 Elasticsearch / Tantivy / OpenSearch，避免运维复杂度。
- chunk 增删时支持 `add_chunks` / `remove_chunks` 增量重建，不需要在每次 ingest 后重启进程。

**风险**：进程重启需要重建索引；规模 > 50k 后内存会膨胀。Phase 4 之前不会触及这个量级。

### 决策 2：异步 ingest 用 FastAPI BackgroundTasks（MVP）

**为什么**：

- MVP 不引入 Celery/RQ。`POST /sources/{id}/ingest` 立即返回 `task_id`，后台跑解析 → 入库；状态写在 `sources.status`，前端轮询 `GET /sources/{id}` 即可。
- BackgroundTasks 与进程绑定的风险通过 `sources.status` 持久化中间态 + 幂等覆盖兜底。

**升级路径**：Phase 4 引入 LLM cost 控制时切到带队列的 worker。

### 决策 3：retrieval 权重外置到 `config/retrieval.yaml`

**为什么**：

- 不同 stage（故事生成 vs 审计）对来源偏好不同：故事侧偏 lore + monster；审计侧偏 lore + rules。
- 权重是调参手段，应可在不改代码的前提下迭代。
- 配置文件由后端启动时加载并缓存；retrieve 请求传 `stage` 拉对应权重。

**初始权重建议**：`default = {vector: 0.6, bm25: 0.4}`，`world_audit` 在此基础上把 `world_bible` 与 `dmg` 来源加权 1.5x；Phase 2 接入 brief 流程后再细化。

### 决策 4：单 collection + filter 实现项目隔离

继承 1a 决策：所有 chunk（SRD + lore）共用 `dnd_rag` collection；lore 必带 `project_id`，SRD 留空。

**为什么**：

- 单 collection 让混合检索逻辑简单；filter on metadata 在 Chroma 中开销低。
- 跨项目共享 SRD（`project_id IS NULL OR project_id = :pid`）只需一个过滤条件，无需 collection 级 union。

**风险**：写代码漏过滤会跨项目泄漏。→ Mitigation：retriever 层在请求入口强制注入 `project_id` 过滤；单测覆盖跨项目隔离。

### 决策 5：Metadata 过滤白名单扩展

继承 1a 白名单（`source` / `chunk_type` / `tags` / `cr` / `spell_level` / `project_id`），新增 `cr_range`（`[min, max]` 闭区间，运行期翻译为 Chroma `$gte` / `$lte` 组合）。

**为什么**：CR 是数值字段，单值匹配能力不够；范围匹配是 monster 检索的常见诉求。

### 决策 6：reranker 接口预留

定义 `Reranker.rerank(query, candidates) -> candidates`，默认 `NoOpReranker`。

**为什么**：未来引入 cross-encoder reranker 时不需要重构调用方；本 change 不实装具体 reranker（Cohere / bge-reranker 等需要额外依赖与成本评估）。

## Risks / Trade-offs

- **[Risk] BM25 索引启动时间**：50k chunk 量级冷启动需要数秒。→ Mitigation：日志记录构建耗时；超过 5s 时打 warning，留作 Phase 4 切外部索引的触发条件。
- **[Risk] Docling 大文档解析慢**：MVP 仅 Markdown 时解析快；接口预留 PDF 后会引入数十秒延迟。→ Mitigation：异步任务模型已支撑这种延迟；PDF 留补丁。
- **[Risk] retrieval 权重调参困难**：合并加权在没有 ground truth 时难以验证。→ Mitigation：Knowledge 调试页可视化 score / source；配置文件可热改重载；记录 retrieve 请求与命中 chunk 便于事后分析。
- **[Trade-off] BackgroundTasks vs 真队列**：BackgroundTasks 与进程绑定，进程崩溃任务丢。→ Mitigation：`sources.status` 持久化中间态；崩溃后用户可重新触发 ingest 接口（幂等覆盖）。
- **[Trade-off] project 存在性不强校验**：仓库尚无 `projects` 表/CRUD。本 change 沿用 1a 约定：`project_id` 仅做格式校验，不查存在性，不返回 404。项目隔离由 retriever 在 filter 入口处强制注入。`projects` 表/CRUD 由独立 `add-project-management` change 在需要项目元数据时再补，不搭车进 Phase 1。

## Migration Plan

1. **依赖安装**：`uv sync` 引入 `docling` / `rank-bm25` / `python-multipart`。
2. **配置文件**：新增 `config/retrieval.yaml`，含 `default` 与 `world_audit` 两个 stage 的权重。
3. **路由注册**：`apps/api/app/main.py` 注册 `sources` 与 `retrieve` 路由；FastAPI lifespan 中初始化 BM25 retriever。
4. **数据无新增迁移**：`sources` 表与 `rag_chunks` 列扩展已在 1a 完成；本 change 只是开始往 `sources` 写入。
5. **回滚**：删除新增路由模块、删除 `data/uploads/` 与 `data/parsed/`、清空 `sources` 表与 `rag_chunks` 中 `source = 'world_bible'` 的行；恢复到 1a 状态无残留。

## Open Questions

- **`config/retrieval.yaml` 默认权重精确值**：`vector:0.6, bm25:0.4` 是初稿；Phase 2 接入 brief 流程后用真实查询样本回归调参。
- **大文件流式上传**：MVP 用 multipart 一次性上传 ≤ 20MB 是否够？若用户拿超大世界观（50MB+）再考虑分片。
- **`tags` 过滤匹配语义**：白名单已含 `tags`（任一命中），但 Chroma 对 `;` 分隔字符串只能做 `$contains`，无法精确"任一命中"。是否要把 `tags` 过滤改为 BM25 后置过滤、放弃 Chroma 端 `tags` filter？1c 实施时实测决定。
