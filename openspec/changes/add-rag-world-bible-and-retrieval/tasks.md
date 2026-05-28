## 1. 占位说明

> 本 change 在 `add-rag-srd-ingest` archive 后才正式启动。tasks 直接复刻原 `add-rag-layer-phase1` 的 §7–§13，待 1a archive 后再做细粒度切割与依据现状校准。

## 7. 上传与 Source 状态机（capability: world-bible-ingest）

- [ ] 7.1 `apps/api/app/routers/sources.py` 实现 `POST /projects/{project_id}/sources`：仅接受 `text/markdown` 或 `.md`；超 `MAX_UPLOAD_BYTES` 返回 413；非 Markdown 返回 415；落盘到 `data/uploads/{project_id}/<source_id>__<filename>`
- [ ] 7.2 `SourceRepository`：`create` / `get` / `update_status` / `set_error`
- [ ] 7.3 `apps/api/app/main.py` 注册 sources router
- [ ] 7.4 `GET /projects/{project_id}/sources/{source_id}` 状态轮询接口
- [ ] 7.5 集成测试：成功上传、415、413（`project_id` 不做存在性校验）

## 8. 解析与切块（capability: world-bible-ingest）

- [ ] 8.1 `services/rag/parsers/markdown_parser.py`：Docling 解析 Markdown 为带 heading 的中间结构，规整 Markdown 落到 `PARSED_DIR/{project_id}/{source_id}.md`；`Parser` 接口按 `kind` 分发（PDF NotImplemented）
- [ ] 8.2 `services/rag/chunkers/lore_chunker.py`：按 heading 切块，目标 500–1000 token，超长递归拆分，无重叠；`RagChunk(chunk_type="lore_chunk", source="world_bible", canon_level="soft", section_path=[...])`
- [ ] 8.3 单测：3 级 heading 文档断言 `section_path` 正确；token 数 ≥90% 落 500–1000

## 9. 异步 ingest 流水线（capability: world-bible-ingest）

- [ ] 9.1 `POST /projects/{project_id}/sources/{source_id}/ingest`：FastAPI `BackgroundTasks` 异步调度；立即返回 202 + `task_id`
- [ ] 9.2 `ingest_source(source_id)`：状态依次 `parsing → chunking → embedding → indexed`；失败置 `failed` + `last_error`
- [ ] 9.3 入库逻辑复用 `add-rag-srd-ingest` §5：写 Chroma + SQLite，metadata 含 `project_id`；同 `source_id` 重 ingest 时按 `source_id` 删旧再写新
- [ ] 9.4 集成测试：上传 → ingest → 轮询到 `indexed` → retrieve 召回；损坏内容覆盖 `failed` 路径

## 10. 检索器实现（capability: hybrid-retrieval）

- [ ] 10.1 `services/rag/retriever/vector.py`：`VectorRetriever.retrieve(query, top_k=20, filters)`，query embed 后查 Chroma
- [ ] 10.2 `services/rag/retriever/bm25.py`：启动期从 SQLite 加载 `chunk_text` 构建 `rank_bm25.BM25Okapi`；支持 `add_chunks` / `remove_chunks`
- [ ] 10.3 FastAPI lifespan 初始化 BM25 retriever（构建 > 5s 打 warning）；ingest 完成后调 `add_chunks`
- [ ] 10.4 `services/rag/retriever/filters.py`：请求 filter 翻译为 Chroma `where` 与 BM25 后置过滤；`project_id` 强制 `OR project_id IS NULL`
- [ ] 10.5 `services/rag/retriever/hybrid.py`：合并 vector + BM25 候选；按 `chunk_id` 去重；`final_score = w_vector * vec + w_bm25 * bm25`
- [ ] 10.6 `Reranker` 接口（`async def rerank(query, candidates) -> candidates`）；默认 `NoOpReranker`
- [ ] 10.7 单测：metadata 复合过滤、跨项目隔离、stage 切换权重影响排序、reranker 注入有效

## 11. Retrieve API（capability: hybrid-retrieval）

- [ ] 11.1 `apps/api/app/routers/retrieve.py`：`POST /projects/{project_id}/retrieve`，`{query, top_k?, stage?, filters?}`；空 query 422；非法 `project_id` 格式 422
- [ ] 11.2 `main.py` 注册 retrieve router
- [ ] 11.3 响应 schema 含每 chunk 的 `chunk_id` / `score` / `source` / `source_title` / `chunk_type` / `title` / `section_path` / `tags` / `text` / `metadata` / `canon_level` / `source_ref`
- [ ] 11.4 集成测试：成功、422（空 query / 非法 project_id）、stage 切换、`top_k` 截断

## 12. 前端 Knowledge 页（capability: hybrid-retrieval）

- [ ] 12.1 `apps/web/app/knowledge/page.tsx`：query 输入框 + 过滤控件（`source` checkbox、`chunk_type` 多选、`cr_range` 双滑块、`stage` 单选）
- [ ] 12.2 调用 `/projects/{id}/retrieve`，结果 Card 列表展示 `title` / `source` / `section_path` / `score` / `canon_level`；点击展开看完整 `text` 与 `metadata` JSON
- [ ] 12.3 导航或首页加入口链接

## 13. 端到端验收

- [ ] 13.1 通过 API 上传一份示例世界观 Markdown → 触发 ingest → 状态走到 `indexed`（Phase 1b 验收）
- [ ] 13.2 Knowledge 页输入跨域 query，能同时看到 SRD 与世界观命中；切换 stage 排序变化（Phase 1c 验收）
- [ ] 13.3 跨项目隔离手测：项目 A、B 各上传一份 lore，A 的 retrieve 看不到 B 的 lore，但都能看到 SRD
- [ ] 13.4 PR 描述附 retrieve API curl 示例与 Knowledge 页截图
