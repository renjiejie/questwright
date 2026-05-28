## 1. 依赖与基础配置

- [x] 1.1 在 `pyproject.toml` 新增依赖：`chromadb`、`pyyaml`，运行 `uv sync` 锁定（其余 `rank-bm25` / `docling` / `python-multipart` 等 1b/1c 再加）
- [x] 1.2 扩展 `.env.example`：`CHROMA_COLLECTION=dnd_rag`、`EMBEDDING_BATCH_SIZE=10`（适配 DashScope 单批上限）、`SRD_DATA_PATH`、`UPLOAD_DIR`、`PARSED_DIR`，并新增 embedding 解耦项 `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` / `EMBEDDING_DIM`；在 `apps/api/app/config.py` 的 `Settings` 中加对应字段
- [x] 1.3 在仓库根 `Makefile` 加 `srd-update` target：`git -C vendor/5e-database pull --depth 1`；同时把 `vendor/` 加进 `.gitignore`

## 2. 数据库迁移

- [x] 2.1 在 `services/db/models.py` 新增 `Source` 模型：`id` / `project_id` / `kind` / `original_filename` / `mime_type` / `byte_size` / `status` / `last_error` / `created_at` / `updated_at`
- [x] 2.2 扩展 `RagChunk` 模型，新增列：`project_id`（NULL=全局）、`source_id` 外键到 `sources`、`source_ref`、`canon_level`、`metadata` JSON、`chunk_text`；补 `ix_rag_chunks_project` 索引
- [x] 2.3 用 `alembic revision --autogenerate -m "add sources and extend rag_chunks"` 生成迁移；手工核对 SQLite 兼容性（避免使用 PG 专属类型）
- [x] 2.4 `alembic upgrade head` 在已 Phase 0 跑过的本地 SQLite 上无损执行；写一个回归用 fixture 覆盖

## 3. SRD 加载与归一化（capability: srd-ingest）

- [x] 3.1 实现 `services/rag/srd_loader.py`：`FILE_TO_SOURCE` 字典 + `iter_records(srd_path) -> Iterator[RawSrdRecord]`，逐文件 `json.load` 后 yield
- [x] 3.2 定义 Pydantic 模型 `RawSrdRecord`（字段见 spec）；`SRD_DATA_PATH` 缺失或非目录时抛清晰错误
- [x] 3.3 单元测试：mock `SRD_DATA_PATH` 为 fixture 目录，覆盖 monsters/spells/rules/misc 4 类映射
- [x] 3.4 CLI 入口 `services/rag/cli.py` + `__main__.py`：实现 `load-srd --dry-run`，输出每个文件的记录数

## 4. SRD 分类切块（capability: srd-ingest）

- [x] 4.1 在 `services/rag/chunkers/__init__.py` 写 chunker registry：装饰器 `@register("monsters")` 或 `CATEGORY_CHUNKERS` 字典；公共基类 `BaseChunker.chunk(record) -> RagChunk`
- [x] 4.2 实现 `monster_chunker.py`：合成模板含 name/CR/size/type/AC/HP/actions/special；`metadata` 含 `cr` `hp` `ac`；`chunk_type=monster_statblock`
- [x] 4.3 实现 `spell_chunker.py`：模板含 name/level/school/range/components/desc/higher_level；`metadata` 含 `spell_level` `school`；`chunk_type=spell_chunk`
- [x] 4.4 实现 `class_race_feature_chunker.py`（含 classes/subclasses/races/subraces/features/traits/feats/backgrounds/levels/ability-scores/skills/proficiencies/languages）：展开 `desc[]`
- [x] 4.5 实现 `rule_chunker.py`（rules + rule-sections）与 `misc_chunker.py`（其余 srd_misc 类）
- [x] 4.6 每个 chunker 至少 3 个 fixture 单测：典型记录、字段缺失、空 desc
- [x] 4.7 `RagChunk` Pydantic 模型补 `id`、`source`、`source_title`、`edition`、`chunk_type`、`title`、`section_path`、`tags`、`text`、`metadata`、`canon_level`、`source_ref` 等字段（spec 1）
- [x] 4.8 集成测试：对 `SRD_DATA_PATH` 全量 25 文件跑 `load → chunk` 链路，断言无未注册 category 异常、总 chunk 数 > 0

## 5. Embedding 与 Chroma 入库（capability: srd-ingest）

- [x] 5.1 实现 `services/rag/embed.py`：`async def embed_texts(texts, batch_size)`，调 `OpenAIEmbedding`，含失败重试（最多 3 次，指数退避）
- [x] 5.2 实现 `services/rag/index.py`：`ChromaIndex` 包装 `chromadb.PersistentClient`；`upsert_chunks(chunks, embeddings)` 把可过滤 metadata（`source` `chunk_type` `tags` `cr` `spell_level` `project_id`）写入 Chroma；`tags` 序列化采用 `;` 分隔字符串
- [x] 5.3 同步把完整 `metadata` + `chunk_text` 写入 SQLite `rag_chunks`；同 `chunk_id` 走 upsert 保证幂等
- [x] 5.4 CLI `reindex-srd`：扫 SRD → chunk → embed（batch）→ upsert；进度条/日志显示已处理数；失败可恢复（按 `chunk_id` 跳过 SQLite 已存在）
- [x] 5.5 集成测试：跑两次 `reindex-srd`，断言 Chroma collection count 与 SQLite 行数都不变；同一 `chunk_id` embedding 被覆盖

## 6. SRD 检索 CLI 与 1a 验收（capability: srd-ingest）

- [x] 6.1 CLI `search "<query>" --top-k 5`：调 vector retriever，按可读格式打印 `title` / `source` / `score` / `text` 摘要
- [x] 6.2 验收：`search "fire breathing dragon CR 10"` 返回结果中包含 Young Red Dragon（CR 10），实测 top-1 为 Red Dragon Wyrmling、CR 10 火龙在 top-5 内；记录到本 change archive 笔记

## 7. Embedding Provider 解耦（capability: srd-ingest）

- [x] 7.1 `services/providers/embedding.py` 的 `OpenAIEmbedding` 加 `base_url` / `model` / `dim` / `send_dimensions` 参数；`dim` 改为实例属性；`send_dimensions=True` 时透传 `dimensions` 给 `embeddings.create`
- [x] 7.2 `services/rag/embed.py` 增加 `_default_provider()`：从 settings 构建 embedding provider，优先用 `EMBEDDING_API_KEY`，缺失时回退 `OPENAI_API_KEY`；`base_url` 取 `EMBEDDING_BASE_URL`；`model` / `dim` 从 settings 读
- [x] 7.3 单测覆盖：embedding 客户端构造时传入正确的 base_url；`send_dimensions=True` 时请求 kwargs 含 `dimensions`；`send_dimensions=False`（默认）时不带
- [x] 7.4 `.env.example` 注释里写明默认值是 DashScope `text-embedding-v4` + dim 1536，并说明若切回 OpenAI 官方需要把 `EMBEDDING_BATCH_SIZE` 调回 64

## 8. 归档前清单

- [x] 8.1 跑 `uv run pytest services/providers/tests services/rag/tests services/db/tests` 全部通过
- [ ] 8.2 提交 PR：标题 `add-rag-srd-ingest: SRD 入库 + CLI 检索 (Phase 1a)`，描述附 `cli search` 输出
- [ ] 8.3 用 OpenSpec archive 流程归档本 change；spec 文件 promote 到 `openspec/specs/srd-ingest/`
- [ ] 8.4 起新 change `add-rag-world-bible-and-retrieval` 承接原 phase1 §7–§13 任务
