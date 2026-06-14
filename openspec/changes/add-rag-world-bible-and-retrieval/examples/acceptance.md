# Phase 1b/1c 验收与 PR 说明

本文件为 `add-rag-world-bible-and-retrieval` 的端到端验收脚本与 PR 描述素材。

## 前置

```bash
# 1. 安装依赖（docling / rank-bm25 / python-multipart 已在 pyproject 中）
uv sync

# 2. 跑数据库迁移
alembic upgrade head

# 3. 索引 SRD（提供全局可见的 SRD chunk）
python3 -m services.rag.cli reindex-srd

# 4. 启动 API（lifespan 会构建 BM25 内存索引）
uvicorn app.main:app --app-dir apps/api --port 8765

# 5. 启动前端
pnpm --filter web dev   # http://localhost:3765/knowledge
```

## 13.1 上传 → ingest → indexed

```bash
# 上传示例世界观（examples/world_bible_sample.md）
curl -s -X POST http://localhost:8765/projects/p1/sources \
  -F "file=@openspec/changes/add-rag-world-bible-and-retrieval/examples/world_bible_sample.md;type=text/markdown"
# => {"source_id":"source_xxxx","status":"uploaded",...}

# 触发异步 ingest
curl -s -X POST http://localhost:8765/projects/p1/sources/source_xxxx/ingest
# => 202 {"task_id":"ingest_xxxx","source_id":"source_xxxx","status":"pending"}

# 轮询状态，直到 indexed
curl -s http://localhost:8765/projects/p1/sources/source_xxxx
# => {"status":"parsing"} -> "chunking" -> "embedding" -> "indexed"
```

## 13.2 跨域检索 + stage 切换

```bash
# default stage：同时召回 SRD 与世界观
curl -s -X POST http://localhost:8765/projects/p1/retrieve \
  -H 'Content-Type: application/json' \
  -d '{"query":"火山 议长 dragon","top_k":8,"stage":"default"}'

# world_audit stage：world_bible 来源被加权，排序变化
curl -s -X POST http://localhost:8765/projects/p1/retrieve \
  -H 'Content-Type: application/json' \
  -d '{"query":"火山 议长 dragon","top_k":8,"stage":"world_audit"}'
```

Knowledge 页（`/knowledge`）：输入同一 query，切换 stage 下拉，观察结果卡片
排序与 score 变化；点击「展开 text / metadata」查看完整文本与 metadata JSON。

## 13.3 跨项目隔离

```bash
# 项目 A、B 各上传一份 lore
curl -s -X POST http://localhost:8765/projects/pA/sources -F "file=@a.md;type=text/markdown"
curl -s -X POST http://localhost:8765/projects/pB/sources -F "file=@b.md;type=text/markdown"
# ...分别 ingest...

# A 的 retrieve 看不到 B 的 lore，但都能看到 SRD
curl -s -X POST http://localhost:8765/projects/pA/retrieve \
  -H 'Content-Type: application/json' -d '{"query":"lore","top_k":20}'
```

隔离由 `RetrievalFilters` 在 filter 入口强制注入 `project_id`，并在
`passes_post_filter` 中应用「`project_id` 为空（全局 SRD）OR 等于本项目」规则。
自动化覆盖见 `apps/api/tests/test_ingest_retrieve.py::test_cross_project_isolation`
与 `services/rag/tests/test_retriever.py::test_bm25_add_remove_and_isolation`。

## 13.4 PR 描述素材

**Summary**：交付 Phase 1b（世界观 Markdown 上传 → 异步 ingest → 入库）与
Phase 1c（vector + BM25 + metadata 混合检索 API + Knowledge 调试页）。

**Tested**：
- `pytest`（58+ 通过）：sources 路由 415/413/422、lore 切块 section_path 与
  token 区间、检索器复合过滤/跨项目隔离/stage 权重/reranker 注入、
  upload→ingest→retrieve 全链路与 failed 路径。
- 前端 `next build` 通过，`/` 与 `/knowledge` 两个路由。

**截图**：在此粘贴 Knowledge 页检索结果截图（含展开的 metadata JSON）。

**Blocked / Non-Goals**：PDF 解析、chunk 重叠、具体 reranker 实现、真队列
异步均按 design.md 留待后续 phase。
