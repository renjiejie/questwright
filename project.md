# Questwright — 项目说明

> 配套文档：[设计草案.md](设计草案.md) · [实施方案.md](实施方案.md) · [README.md](README.md)
>
> 当前阶段：**Phase 0（骨架）已完成**。本文档以代码现状为准，描述目前真实存在的目录、技术栈、模块职责、核心业务流与外部依赖；未落地的部分会显式标注 `[计划]`。

---

## 1. 项目定位

**人类把关的 DND 模组逐步生成系统**。不追求 Agent 全自主创作，而是用：

```
确定性工作流 + RAG 检索 + LLM 生成节点 + LLM 审计节点 + 人类确认节点 + Artifact 版本管理
```

把贵模型用在故事生成关键环节，便宜模型用于审计，每一步都可由人确认 / 修改 / 回滚。

---

## 2. 目录结构

```
questwright/
├── apps/
│   ├── api/                       # FastAPI 后端入口（Python）
│   │   ├── app/
│   │   │   ├── main.py            # FastAPI app factory + /healthz
│   │   │   ├── config.py          # Settings（pydantic-settings，从 .env 读取）
│   │   │   ├── db.py              # FastAPI 用的 DB 依赖
│   │   │   └── routers/
│   │   │       └── artifacts.py   # POST/GET /artifacts（fork-based revise）
│   │   └── tests/                 # 占位
│   └── web/                       # Next.js 14 前端（App Router）
│       ├── app/
│       │   ├── layout.tsx
│       │   └── page.tsx           # Phase 0 占位首页
│       └── package.json           # next/react，开发端口 3765
│
├── packages/
│   └── shared-schemas/            # [计划] artifacts/audit JSON Schema 共享层（当前为空）
│
├── services/                      # Python 业务模块（pythonpath = repo 根）
│   ├── db/
│   │   ├── models.py              # SQLAlchemy 表模型（artifacts 等 7 张表）
│   │   ├── repositories.py        # Artifact 仓储（CRUD + version+1 fork）
│   │   ├── session.py             # AsyncEngine / session_scope
│   │   └── migrations/            # Alembic（env.py + versions/*）
│   ├── providers/
│   │   ├── base.py                # LLMProvider ABC + LLMResponse
│   │   ├── openai_provider.py     # GPT-4o / 4.1 系列，故事生成
│   │   ├── deepseek_provider.py   # deepseek-chat / reasoner，审计
│   │   ├── embedding.py           # EmbeddingProvider + OpenAIEmbedding
│   │   └── tests/                 # mock 客户端的单元测试
│   ├── workflows/
│   │   ├── states.py              # ModuleWorkflowState（TypedDict）
│   │   └── module_generation_graph.py  # LangGraph：generate → END（最小图）
│   ├── prompts/                   # 提示词（auditor / fixer / story_generator 子目录已建，文件 [计划]）
│   ├── rag/                       # [计划] parse / chunk / embed / index / retrieve
│   └── agents/                    # [计划] story_generator / world_auditor / story_fixer
│
├── data/                          # 运行时产物（DB / Chroma），git 忽略
├── vendor/                        # 第三方源数据（5e-database 由 make srd-update 拉取）
├── pyproject.toml                 # uv 单一 workspace，Python 3.12
├── package.json + pnpm-workspace.yaml  # pnpm workspace（仅 apps/web、packages/*）
├── Makefile                       # install / migrate / api / web / test / lint / srd-update
├── .env.example                   # 环境变量模板
├── 设计草案.md / 实施方案.md      # 设计与里程碑文档
└── README.md
```

> **注意**：仓库根下有一份重复的 `questwright/` 子目录，内容与 `apps/`、`services/` 大致一致，疑似误提交的嵌套副本，建议清理（不在 `pnpm-workspace.yaml` / `pyproject.toml` 引用范围内）。本说明只描述顶层这套。

---

## 3. 技术栈

### 后端（Python 3.12，uv 管理）

| 关注点       | 选型                                     | 说明 |
| ------------ | ---------------------------------------- | ---- |
| Web 框架     | FastAPI 0.115+ + uvicorn                 | API 服务，端口 8765 |
| 配置         | pydantic-settings 2.6+                   | `.env` 加载，关键 key 校验 |
| ORM          | SQLAlchemy 2.0 (async) + aiosqlite       | 业务库 |
| 迁移         | Alembic 1.13+                            | SQLite 用 `render_as_batch` |
| 工作流       | LangGraph 0.2.50+                        | StateGraph + AsyncSqliteSaver checkpoint |
| LLM SDK      | openai 1.54+（同时给 DeepSeek 复用）     | DeepSeek 走 OpenAI 兼容 base_url |
| HTTP         | httpx 0.27+                              | 备用客户端 |
| 测试         | pytest 8.3+ / pytest-asyncio / pytest-mock | `asyncio_mode = "auto"` |
| Lint         | ruff 0.7+                                | line-length 100，规则集 E/F/I/B/UP |

### 前端（Node 20+，pnpm workspace）

| 关注点 | 选型                          |
| ------ | ----------------------------- |
| 框架   | Next.js 14.2（App Router）    |
| UI     | React 18.3 + TypeScript 5.6   |
| 样式   | `[计划]` Tailwind（设计草案约定，目前未装） |

### 数据层

| 用途                  | 选型                                   |
| --------------------- | -------------------------------------- |
| 业务 DB               | SQLite（MVP）→ PostgreSQL`[计划]`     |
| LangGraph checkpoint  | SQLite（与业务 DB 同库不同表）         |
| 向量库                | Chroma PersistentClient（`./data/chroma`）`[计划]` |
| SRD 数据源            | `vendor/5e-database/src/2014/en/*.json` |

---

## 4. 模块职责

### 4.1 `apps/api`（FastAPI 入口）

- **`app/main.py`**：`create_app()` 工厂；当前暴露 `GET /healthz`（返回 status + APP_ENV）和 `/artifacts` 路由。
- **`app/config.py`**：`Settings` 读取 `.env`；`require_llm_keys()` 在真正调 LLM 前才校验 key 缺失，让单测/迁移可在无 key 环境跑。
- **`app/routers/artifacts.py`**：Phase 0 的 Artifact CRUD，提供 fork-based 版本叠加（version+1，parent_id 串接）。
- **职责边界**：API 只做 HTTP 适配、参数校验、依赖注入；具体存取与工作流逻辑下沉到 `services/`。后续 `projects / sources / workflow / reviews / retrieval` 路由会逐个加入。

### 4.2 `apps/web`（Next.js 前端）

- 当前只是占位首页，证明启动链路通；Phase 2+ 才上人工确认卡片、Artifact 浏览页等。
- 端口 3765（与 API 8765 错开，避免与本机其他项目冲突）。

### 4.3 `services/db`（数据层）

- **`models.py`**：SQLAlchemy 模型，对应草案 §10 的 7 张表（artifacts 当前已建表，其余表按里程碑推进）。
- **`repositories.py`**：仓储层，封装 artifact 的创建 / 取最新版 / fork 等操作，便于路由和工作流共用。
- **`session.py`**：全局缓存 `AsyncEngine` 与 `async_sessionmaker`，提供 `session_scope()` 上下文（commit/rollback 自动）。
- **`migrations/`**：Alembic 配置；`env.py` 把 repo 根和 `apps/api` 注入 `sys.path`，复用 `app.config.get_settings()` 拿 DSN，并把 async 驱动剥离出 sync URL 供 alembic 使用。

### 4.4 `services/providers`（LLM / Embedding 适配层）

- **`base.LLMProvider`**：抽象基类，规定 `generate(model, messages, response_schema, temperature, max_tokens) -> LLMResponse`，统一 token 用量与成本字段。**业务代码只依赖抽象**。
- **`openai_provider.OpenAIProvider`**：用 `AsyncOpenAI` + Chat Completions；带 schema 时强制 `response_format=json_object` 并解析；内置 GPT-4o / 4.1 估价表。
- **`deepseek_provider.DeepSeekProvider`**：复用 `AsyncOpenAI`，只换 `base_url=https://api.deepseek.com`，省去自实现 HTTP 与重试。
- **`embedding.OpenAIEmbedding`**：`text-embedding-3-small`（dim=1536），与 `LLMProvider` 解耦（embedding API 形态不同）。
- 所有 provider 均支持注入 mock client，便于测试与离线运行。

### 4.5 `services/workflows`（工作流引擎）

- **`states.ModuleWorkflowState`**：TypedDict，承载 project_id / run_id / current_stage / artifact ids / human_feedback 等；Stage 与 NextAction 用 `Literal` 锁定枚举，让节点函数 IDE 可识别非法跳转。
- **`module_generation_graph.py`**：Phase 0 的最小 LangGraph：`START → generate → END`；`_generate_node` 当前只产出占位 artifact id 用于打通状态 / checkpoint。
  - `make_checkpointer(db_path)` 返回 `AsyncSqliteSaver` 上下文，由调用方 `async with` 管理生命周期。
  - `build_graph(checkpointer=None)` 支持持久化运行（带 checkpointer）或一次性内存运行（测试）。
- 后续会逐步注册 `human_review / audit / audit_review / revise / commit / advance_stage` 节点，对应草案 §8.4。

### 4.6 `services/prompts`（提示词资产）

- 子目录约定：`story_generator/` `auditor/` `fixer/`。Phase 0 仅占位，文件由 Phase 2 起填充（`campaign_brief.md` 等）。所有 prompt 强约束输出结构化 JSON。

### 4.7 `services/rag` / `services/agents`（待实现）

- `rag/`：Phase 1a/b/c 落地 — SRD JSON 接入、世界观文档接入、Vector + BM25 + metadata filter 的 `/retrieve`。
- `agents/`：Phase 2 起以无类型节点函数形式落到 LangGraph，和 prompts、provider 解耦。

---

## 5. 核心业务流

### 5.1 模组逐层展开

```
Level 1 Campaign Brief  → Level 2 Campaign Outline → Level 3 Act Outline
   → Level 4 Scene/Encounter → Level 5 Final Module
```

每一层都走同一个小循环（Phase 2 起逐层接入）：

```
Generate
  ↓
Human Review
  ├─ approve → Audit
  ├─ request_changes → Revise → Human Review
  └─ reject → Regenerate
Audit
  ↓
Human Review Audit
  ├─ approve → Commit
  ├─ request_changes → Revise With Audit → Human Review
  └─ reject → Regenerate / Return Previous Stage
Commit
  ↓
Next Stage
```

### 5.2 LangGraph 状态机（当前实现 vs 目标）

- **当前**：`START → generate → END`，`generate` 仅写入占位 `current_artifact_id` 与 `next_action="human_review"`，验证 state 路由与 SQLite checkpoint。
- **目标**：节点扩展为 `generate / human_review / audit / audit_review / revise / commit / advance_stage / finish`；通过 `next_action` 做条件跳转；checkpointer 提供 human-in-the-loop 的暂停 / 恢复。

### 5.3 Artifact 版本管理

- 修改不写覆盖：每次 `Request Changes` / `Revise` 走 fork — `version+1`、`parent_artifact_id` 串接，原版本保留以便回滚 / diff。
- 仓储层保证「同 stage 取最新版」「按链路回溯」两种查询路径（`services/db/repositories.py`）。

### 5.4 RAG 检索（Phase 1）

```
SRD JSON ──▶ 字段映射 chunk ──▶ Embedding ──▶ Chroma collection: srd
World Bible (用户上传) ──▶ Docling 解析 ──▶ heading-aware chunk ──▶ Embedding ──▶ collection: lore
                                                          ↘
                                          /retrieve API（Vector + BM25 + metadata filter）
                                                          ↙
                                                生成节点 / 审计节点引用
```

---

## 6. 外部依赖

### 6.1 在线服务

| 服务         | 用途                       | 凭证            | 触发点                         |
| ------------ | -------------------------- | --------------- | ------------------------------ |
| OpenAI API   | 故事生成 + Embedding       | `OPENAI_API_KEY` | `OpenAIProvider` / `OpenAIEmbedding`，`Settings.require_llm_keys()` 守卫 |
| DeepSeek API | 世界观 / 规则审计（便宜模型） | `DEEPSEEK_API_KEY` | `DeepSeekProvider` |

### 6.2 离线 / 本地资源

| 资源           | 路径                          | 获取方式                                |
| -------------- | ----------------------------- | --------------------------------------- |
| SRD 数据       | `vendor/5e-database/src/2014/en/` | `make srd-update`（git clone + pull --depth 1） |
| 业务 DB        | `data/dnd.db`（默认）         | `make migrate`（alembic upgrade head） |
| Chroma 向量库  | `data/chroma`                 | Phase 1a 起按需创建                    |
| LangGraph checkpoint | 与业务 DB 同库              | `AsyncSqliteSaver` 自动建表             |

### 6.3 环境变量（`.env` / `.env.example`）

- `OPENAI_API_KEY` / `DEEPSEEK_API_KEY`
- `DATABASE_URL`（默认 `sqlite+aiosqlite:///./data/dnd.db`）
- `CHROMA_PATH`、`SRD_DATA_PATH`
- `APP_ENV`（dev|staging|prod）、`LOG_LEVEL`

### 6.4 工具链外部依赖

- `uv`（Python venv + 依赖）
- `pnpm`（JS workspace）
- Node 20+ / Python 3.12
- `git`（拉取 5e-database）

---

## 7. 启动与验收

```bash
make install         # uv sync + pnpm install
cp .env.example .env # 填入 OPENAI_API_KEY / DEEPSEEK_API_KEY
make srd-update      # 拉取 SRD JSON（首次）
make migrate         # alembic upgrade head
make api             # uvicorn 8765
make web             # next dev 3765
make test            # pytest
make lint            # ruff
```

Phase 0 验收：

```bash
curl http://localhost:8765/healthz   # → {"status":"ok","env":"dev"}
curl -I http://localhost:3765        # → 200
```

---

## 8. 下一步（Phase 1a 起）

按 `实施方案.md` 顺序推进：**SRD JSON → Chunk → Embed → Chroma**，再做世界观接入、混合检索 API、最小闭环（Campaign Brief 的 Generate / Review / Audit / Commit），逐层展开到 Act / Scene / Final。
