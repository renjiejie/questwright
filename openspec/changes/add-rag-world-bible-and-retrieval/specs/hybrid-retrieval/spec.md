## ADDED Requirements

### Requirement: 向量检索基础

系统 SHALL 提供向量检索器，对外接收 `query`、`top_k`、可选的 metadata 过滤；内部对 query 调 `EmbeddingProvider.embed`，再向 Chroma `dnd_rag` collection 发起 ANN 查询，默认返回 top 20 候选，每条候选 MUST 含 `chunk_id`、`score`、`metadata`、`text`。

#### Scenario: 命中 SRD 怪物

- **WHEN** 调用向量检索 `query="ancient red dragon"`，无过滤
- **THEN** 返回 20 条候选，且至少有一条 `metadata.chunk_type="monster_statblock"` 且 `title` 含 "Red Dragon"

### Requirement: BM25 检索

系统 SHALL 提供 BM25 检索器，使用 `rank_bm25` 库，索引 MUST 在进程启动时从 SQLite `rag_chunks.chunk_text` 列加载到内存构建。当任一 chunk 增删时，索引 MUST 增量重建（删除：从内存倒排移除；新增：追加并重建评分缓存）。BM25 SHALL 以同样的 `(chunk_id, score, metadata, text)` 形态返回候选。

#### Scenario: 关键词命中

- **WHEN** BM25 检索 `query="grappled condition"`
- **THEN** 返回的 top 5 候选中至少一条 `chunk_id` 指向 SRD condition `grappled` 对应的 chunk

#### Scenario: 索引启动构建

- **WHEN** API 进程启动
- **THEN** BM25 retriever 完成索引构建并就绪；后续请求不再触发全量重建

#### Scenario: 增量更新

- **WHEN** 新 chunk 被写入 `rag_chunks`，调用 retriever 的 `add_chunks([...])`
- **THEN** 之后的 BM25 查询能命中这些新 chunk，无需重启进程

### Requirement: Metadata 过滤

系统 SHALL 在向量与 BM25 两路均支持 metadata 过滤：`source`（多选）、`chunk_type`（多选）、`cr_range`（`[min, max]` 闭区间）、`tags`（任一命中）、`project_id`（精确匹配，留空表示仅查全局 SRD）。多个过滤条件之间为 AND 关系。

#### Scenario: 复合过滤生效

- **WHEN** 检索请求过滤 `source=["monster_manual"]` 且 `cr_range=[5, 10]`
- **THEN** 所有返回 chunk 的 `metadata.source` 等于 `monster_manual` 且 `metadata.cr` 落在 `[5, 10]`

#### Scenario: 项目隔离过滤

- **WHEN** 检索带 `project_id="p1"`
- **THEN** 返回结果仅包含 `metadata.project_id="p1"` 的 lore chunk 与 `project_id` 为空的 SRD chunk；不会泄露 `p2` 的 lore

### Requirement: 混合合并与加权

系统 SHALL 把向量与 BM25 两路候选按 `chunk_id` 去重合并，按可配置加权评分排序后取 top-k（默认 8，由 `RETRIEVAL_TOP_K` 配置）。权重 MUST 由 `config/retrieval.yaml` 提供，支持按 stage（如 `campaign_brief` / `world_audit`）切换 source 维度的权重。Reranker 接口 MUST 预留（默认 no-op），便于后续接入。

#### Scenario: 默认权重稳定

- **WHEN** 未指定 stage，发起一次 retrieve
- **THEN** 使用 `config/retrieval.yaml` 中的 `default` 权重；同一 query 的 top-k 顺序在两次调用之间稳定

#### Scenario: stage 切换权重

- **WHEN** 同一 query 分别以 `stage=campaign_brief` 和 `stage=world_audit` 发起 retrieve
- **THEN** 两次返回的 top-k 排序可不同；审计 stage 下 `world_bible` 来源的 chunk 排名 MUST 不低于故事 stage（具体阈值由配置决定）

#### Scenario: reranker 接口可替换

- **WHEN** 注入一个自定义 `Reranker` 实现
- **THEN** 候选合并后会被该 reranker 重排再截 top-k；默认实现保持 no-op，不影响排序

### Requirement: Retrieve API

系统 SHALL 提供 `POST /projects/{project_id}/retrieve`，请求体含 `query`（必填）、`top_k`（可选）、`stage`（可选）、`filters`（可选，复用上文 metadata 过滤）。响应体 MUST 是 chunk 数组，每项包含 `chunk_id`、`score`、`source`、`source_title`、`chunk_type`、`title`、`section_path`、`tags`、`text`、`metadata`、`canon_level`、`source_ref`，与 SQLite `rag_chunks` + chunk 文本一致。

#### Scenario: 成功调用返回结构化结果

- **WHEN** `POST /projects/p1/retrieve`，body 为 `{"query": "young red dragon", "top_k": 5}`
- **THEN** 响应 200；返回数组长度 ≤ 5；每项字段齐全；`score` 单调非增

#### Scenario: 缺 query 时拒绝

- **WHEN** body 中没有 `query` 或 `query` 为空字符串
- **THEN** 响应 422，错误信息明确指出 `query` 必填非空

#### Scenario: 非法 project_id 格式被拒绝

- **WHEN** `project_id` 不满足约定格式（例如长度超过 64、含非法字符）
- **THEN** 响应 422；不调用 embedding，不查 Chroma。`project_id` 不做存在性校验——它是软隔离键，由 retriever 在 filter 中强制注入以保证项目隔离

### Requirement: Knowledge 调试页

前端 SHALL 提供 "Knowledge Page"，含一个 query 输入框、一组过滤控件（`source`、`chunk_type`、`cr_range`、`stage`），命中结果以列表形式展示，每项 SHALL 显示 `title`、`source`、`section_path`、`score`、`canon_level`、可展开查看 `text` 与原始 `metadata`。该页用于 Phase 1c 的可视验收与后续检索 debug。

#### Scenario: 用户能看到 metadata 与得分

- **WHEN** 在 Knowledge Page 输入 query 并提交
- **THEN** 列表展示返回 chunk；点击任一项展开 metadata，可看到 `cr` / `spell_level` / `tags` 等字段

#### Scenario: 过滤项联动检索

- **WHEN** 在控件中勾选 `source=monster_manual` 后再次提交
- **THEN** 调用的请求体含对应 filter；返回结果全部为 monster_manual 的 chunk
