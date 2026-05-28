## ADDED Requirements

### Requirement: 项目级文档源上传

系统 SHALL 提供 `POST /projects/{project_id}/sources` 接收 multipart 上传，将原始文件落到 `data/uploads/{project_id}/<source_id>__<原文件名>`，并在 SQLite 新增 `sources` 行，包含 `id` / `project_id` / `kind="world_bible"` / `original_filename` / `mime_type` / `byte_size` / `status="uploaded"` / `created_at`。MVP 阶段 SHALL 仅接受 Markdown（`.md` / `text/markdown`），其他类型必须以 415 拒绝；上传体积 MUST 受 `MAX_UPLOAD_BYTES`（默认 20MB）限制，超出以 413 拒绝。

#### Scenario: 成功上传 Markdown

- **WHEN** 客户端 `POST /projects/p1/sources` 上传一份 1KB 的 `.md` 文件
- **THEN** 响应 201，body 含 `source_id`、`status="uploaded"`；磁盘上对应文件存在；`sources` 表多一行

#### Scenario: 拒绝非 Markdown 类型

- **WHEN** 客户端上传 `.docx` 文件
- **THEN** 响应 415，错误信息明确指出 MVP 仅支持 Markdown；不写盘、不入库

#### Scenario: 拒绝超限文件

- **WHEN** 客户端上传一个 21MB 的 Markdown 文件
- **THEN** 响应 413；不写盘、不入库

### Requirement: 异步 ingest 触发

系统 SHALL 提供 `POST /projects/{project_id}/sources/{source_id}/ingest` 触发解析与入库，立即返回 `task_id` 与 `status="pending"`，并在后台异步执行解析→切块→embedding→入 Chroma 流程。`sources.status` 状态机 MUST 是 `uploaded` → `parsing` → `chunking` → `embedding` → `indexed`，失败时进入 `failed` 并写 `last_error`。

#### Scenario: 触发后状态可轮询

- **WHEN** 客户端 `POST /projects/p1/sources/s1/ingest`
- **THEN** 立即返回 202 与 `task_id`；后续 `GET /projects/p1/sources/s1` 能看到 `status` 字段从 `parsing` / `chunking` / `embedding` 走到 `indexed`

#### Scenario: 解析失败可见

- **WHEN** 上传内容损坏导致解析失败
- **THEN** `sources.status="failed"`，`last_error` 含失败原因；Chroma 中没有新增 chunk

### Requirement: 世界观文档解析

系统 SHALL 使用 Docling 把 Markdown 文档解析为带 heading 结构的中间表示，并把规整后的 Markdown 落到 `data/parsed/{project_id}/{source_id}.md`。解析阶段 MUST 保留 heading 层级（`#` / `##` / `###`）。PDF 解析 SHALL 不在 MVP 范围内，但解析器接口 MUST 预留 `kind` 分发以便后续接入。

#### Scenario: Markdown 解析后落盘

- **WHEN** ingest 任务进入 `parsing` 阶段并成功
- **THEN** `data/parsed/{project_id}/{source_id}.md` 存在；其内容保留原文档的 heading 结构

### Requirement: 世界观 heading-aware 切块

系统 SHALL 对解析后的 Markdown 按 heading 切块，单个 chunk 目标 500–1000 token；每个 chunk 输出 `RagChunk`，其 `chunk_type="lore_chunk"`、`source` 取 `world_bible`、`section_path` 含从根 heading 到当前段的标题数组、`canon_level` 默认 `soft`、`tags` 默认空数组、`source_ref` 形如 `{source_id}#<section-slug>`。MVP 阶段 chunk 间 SHALL 不做重叠。

#### Scenario: 多级 heading 保留路径

- **WHEN** 文档结构为 `# 大陆 / ## 王国 / ### 城邦`，城邦段被切到一个 chunk
- **THEN** 该 chunk 的 `section_path` 等于 `["大陆", "王国", "城邦"]`

#### Scenario: chunk 大小落在目标区间

- **WHEN** 对一份 ~5000 token 的世界观 Markdown 切块
- **THEN** 至少 90% 的 chunk token 数在 500–1000 之间；超长段落被进一步拆分以遵守上限

#### Scenario: canon_level 默认 soft 且可改

- **WHEN** chunker 输出新 chunk
- **THEN** `canon_level="soft"`；该字段被写入 SQLite `rag_chunks`，便于后续人工 UI 改为 `hard` 或 `advisory`

### Requirement: 世界观 chunk 入库与项目隔离

系统 SHALL 把世界观 chunk 的 embedding 写入与 SRD 共用的 Chroma collection，但 metadata 必须含 `project_id` 字段；SQLite `rag_chunks` 表 MUST 记录 `project_id` 列以支持按项目过滤。Embedding 调用 MUST 复用 SRD 同一批批量与限速逻辑（`add-rag-srd-ingest` 已交付的 `embed_texts`）。

#### Scenario: 不同项目的世界观互不可见

- **WHEN** 项目 A 与项目 B 各上传一份世界观并 ingest 完成
- **THEN** 任何 retrieve 请求只允许命中其 `project_id` 对应的 lore chunk；SRD chunk（`project_id` 为空 / 全局）对所有项目可见

#### Scenario: 重新 ingest 同一 source 幂等

- **WHEN** 对同一 `source_id` 第二次触发 ingest（例如修复内容后重传）
- **THEN** 旧 source 的 chunk 在 Chroma 与 SQLite 中被覆盖更新；不会出现孤儿 chunk
