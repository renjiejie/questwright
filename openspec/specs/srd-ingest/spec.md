# srd-ingest Specification

## Purpose
TBD - created by archiving change add-rag-srd-ingest. Update Purpose after archive.
## Requirements
### Requirement: 本地 SRD 数据源管理

系统 SHALL 通过环境变量 `SRD_DATA_PATH` 指定本地 5e-database 的 `src/2014/en/` 目录作为唯一 SRD 数据来源，禁止运行期访问网络或启动 MongoDB / 5e-srd-api 服务。仓库根 SHALL 提供 `make srd-update` 命令，对该目录执行 `git pull --depth 1` 以同步上游。`vendor/5e-database/` 目录 MUST 写入 `.gitignore`，不进主仓库历史。

#### Scenario: SRD 路径未配置时拒绝启动加载

- **WHEN** 运行 `python -m services.rag.cli load-srd --dry-run` 而 `SRD_DATA_PATH` 未设置或目录不存在
- **THEN** CLI 必须以非零退出码失败，并在 stderr 输出明确错误，提示用户先执行 `git clone --depth 1 https://github.com/5e-bits/5e-database.git vendor/5e-database`

#### Scenario: 路径正确时列出文件清单

- **WHEN** `SRD_DATA_PATH` 指向有效目录，运行 `load-srd --dry-run`
- **THEN** CLI 输出 25 个 `5e-SRD-*.json` 文件名以及每个文件的记录条数，且 `5e-SRD-Monsters.json` 的文件大小大于 1MB

### Requirement: SRD 原始记录归一化

系统 SHALL 将 25 份 SRD JSON 文件中的每条记录归一化为 `RawSrdRecord`，包含字段：`source`（取值受限：`monster_manual` / `phb` / `dmg` / `srd_misc`）、`file_name`、`category`、`index`、`name`、`raw_json`、`loaded_at`。文件到 `source` 的映射 MUST 由单一字典 `FILE_TO_SOURCE` 维护，新增文件时只改这一处。

#### Scenario: monster 文件映射到 monster_manual

- **WHEN** 加载 `5e-SRD-Monsters.json`
- **THEN** 每条 `RawSrdRecord.source` 等于 `monster_manual`，`category` 等于 `monsters`，`index` 与 `name` 与 JSON 内字段一致

#### Scenario: rules 类文件映射到 dmg

- **WHEN** 加载 `5e-SRD-Rules.json` 或 `5e-SRD-Rule-Sections.json`
- **THEN** 每条 `RawSrdRecord.source` 等于 `dmg`

#### Scenario: 杂项文件映射到 srd_misc

- **WHEN** 加载 `5e-SRD-Magic-Items.json` / `5e-SRD-Conditions.json` / `5e-SRD-Equipment.json` 等未列入 `monster_manual` / `phb` / `dmg` 的文件
- **THEN** 对应 `RawSrdRecord.source` 等于 `srd_misc`

### Requirement: SRD 分类切块

系统 SHALL 为每个 SRD category 提供独立的 chunker（注册到统一 registry），输出 `RagChunk`，至少包含字段：`id`、`source`、`source_title`、`edition="5e"`、`chunk_type`、`title`、`section_path`、`tags`、`text`、`metadata`、`canon_level="hard"`、`source_ref`。`text` 字段是用于 embedding 的合成自然语言文本，禁止直接塞 JSON。

#### Scenario: monster chunk 文本含关键统计字段

- **WHEN** 对 `young-red-dragon` 这条 monster 记录跑 chunker
- **THEN** 输出 `RagChunk.chunk_type` 为 `monster_statblock`；`text` 同时含有怪物名、CR、AC、HP、动作描述与特殊能力；`metadata` 含 `cr` 和 `hp` 字段；`canon_level` 为 `hard`

#### Scenario: spell chunk 文本含等级与学派

- **WHEN** 对 `fireball` 这条 spell 记录跑 chunker
- **THEN** `chunk_type` 为 `spell_chunk`；`text` 含 spell 名、level、school、range、components、`desc`；`metadata` 含 `spell_level` 与 `school`

#### Scenario: chunk id 全局唯一且可追溯

- **WHEN** 任意两条 SRD 记录跑完 chunker
- **THEN** 它们的 `RagChunk.id` 不同，且 `source_ref` 形如 `5e-SRD-Monsters.json#young-red-dragon`，可定位回源记录

#### Scenario: 25 份文件全量可转换无报错

- **WHEN** 对 `SRD_DATA_PATH` 下全部 25 份 JSON 跑 `RawSrdRecord` → `RagChunk` 流水线
- **THEN** 无未注册 category 异常抛出；总 chunk 数被记录且大于零

### Requirement: SRD chunk 入库

系统 SHALL 将所有 SRD chunk 的 embedding 写入 Chroma collection（名称由 `CHROMA_COLLECTION` 配置，默认 `dnd_rag`），并把可过滤的 metadata 字段（至少 `source` / `chunk_type` / `tags` / `cr` / `spell_level`）作为 Chroma metadata 同步落入；完整的 metadata 与 `text` 落入 SQLite `rag_chunks` 表。Embedding 调用 MUST 批量进行，批大小由 `EMBEDDING_BATCH_SIZE` 配置（默认 10，适配 DashScope 单批上限；切回 OpenAI 官方时可调高）。

#### Scenario: 重复 reindex 保持幂等

- **WHEN** 对同一份 SRD 数据连续运行两次 `python -m services.rag.cli reindex-srd`
- **THEN** Chroma collection count 与 SQLite `rag_chunks` 表行数都保持不变；同一 `chunk_id` 的 embedding 被更新而非新增重复行

#### Scenario: collection 总数与 SQL 表一致

- **WHEN** `reindex-srd` 成功结束
- **THEN** Chroma `dnd_rag` collection 的 count 等于 SQLite `rag_chunks` 中 `source IN ('monster_manual','phb','dmg','srd_misc')` 的行数

### Requirement: Embedding Provider 与 Chat LLM Provider 解耦

系统 SHALL 提供独立于 chat LLM 的 embedding 配置：`EMBEDDING_API_KEY`、`EMBEDDING_BASE_URL`、`EMBEDDING_MODEL`、`EMBEDDING_DIM`。`OpenAIEmbedding` 适配器 MUST 接受 `base_url` / `model` / `dim` / `send_dimensions` 四个参数，可对接任意 OpenAI-compatible embedding 端点。当目标模型默认输出维度与 chroma collection 维度不一致时（例如 DashScope `text-embedding-v4` 默认 1024 而 collection 期望 1536），系统 MUST 通过 `send_dimensions=True` 把 `dimensions` 参数透传给 `embeddings.create`，让服务端按指定维度返回。`EMBEDDING_API_KEY` 缺失时，系统 SHALL 回退使用 `OPENAI_API_KEY`，以保留单一 key 简单部署的兜底。

#### Scenario: 默认配置走 DashScope

- **WHEN** `.env` 仅设置 `EMBEDDING_API_KEY`，其他 `EMBEDDING_*` 取默认值
- **THEN** embedding 客户端的 `base_url` 等于 `https://dashscope.aliyuncs.com/compatible-mode/v1`，`model` 等于 `text-embedding-v4`，`dim` 等于 1536，请求 kwargs 含 `dimensions=1536`

#### Scenario: 切换网关不影响 chat

- **WHEN** `OPENAI_BASE_URL` 指向只支持 `/chat/completions` 的网关，且 `EMBEDDING_BASE_URL` 指向另一个支持 `/embeddings` 的网关
- **THEN** chat 调用走 `OPENAI_BASE_URL`，embedding 调用走 `EMBEDDING_BASE_URL`，互不影响；任一网关的 `/embeddings` 故障不会拖垮 chat 链路

#### Scenario: 网关返回非标响应有清晰错误

- **WHEN** embedding 网关返回顶层 string 或缺 `data` 字段的 JSON
- **THEN** 系统抛 `TypeError`，错误信息明确指出响应 shape 异常并提示检查网关兼容性；不抛出 `'str' object has no attribute 'data'` 这种隐晦错误

### Requirement: SRD 检索 CLI 演示

系统 SHALL 提供 `python -m services.rag.cli search "<query>"` 子命令，向 Chroma 发起向量查询并以可读格式打印 top-k 结果（默认 top 5），用于 Phase 1a 离线验收。

#### Scenario: 火焰巨龙类查询返回相关怪物

- **WHEN** 运行 `search "fire breathing dragon CR 10"`
- **THEN** 返回 5 条结果，且 top-k 中至少一条 `chunk_type` 为 `monster_statblock` 且 `title` 命中 Young Red Dragon 或同等 CR 的火焰系怪物

