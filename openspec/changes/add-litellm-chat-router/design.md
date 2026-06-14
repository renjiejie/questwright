## Context

Phase 0/1a 已建立 chat LLM provider 抽象（`BaseProvider`），但具体 provider 适配（OpenAI / DeepSeek）是手写的。当前迫切需求是把"故事生成"切到 Gemini（用户 Gemini 额度宽松），长期需求是让部署者用 env 切任意主流 AI provider。

Embedding 路径已在 1a 解耦（独立 `EMBEDDING_*` env 段，DashScope OpenAI 兼容端点），本 change 仅处理 chat LLM 路由，embedding 不动。

## Goals / Non-Goals

**Goals:**

- chat LLM 调用走统一接口，部署者只需配 env 即可切换 provider/model。
- 默认覆盖 OpenAI / Gemini / DeepSeek / 阿里 Qwen / Kimi / Anthropic / OpenRouter / 任意 OpenAI 兼容端点。
- 故事生成与世界观审计独立配置，互不影响。
- Cost tracking 入口预留（不强制实现日志/指标，只要 response 能拿到 cost）。
- 业务层（Phase 2 接入 LangGraph 时）完全无感于具体 provider，只看 `BaseProvider` 接口。

**Non-Goals:**

- 终端用户 BYOK（per-user key/model；属于范畴 B，独立 change）。
- LiteLLM Proxy server 部署（多用户 key 集中管控；Phase 4+ 评估）。
- Cost 配额、限速、用量上报、审计日志（Phase 4 cost 控制时统一做）。
- Embedding 改走 LiteLLM（1a 已落地原生 OpenAI SDK，没有切换收益）。
- function calling / structured output / streaming / vision 跨 provider 一致性测试（Phase 2 接入 LangGraph 时各自验证）。
- Phase 2 之前不动代码（本 change 仅锁方向）。

## Decisions

### 决策 1：底层用 LiteLLM 而不是自写 OpenAI 兼容路由

**为什么**：

- 自写 router 长期会越来越像 LiteLLM 的删减版（model registry、auth 风格、可选参数透传、cost 表）。
- LiteLLM 已覆盖 100+ provider，包含所有用户提到的主流。OpenAI 兼容路由覆盖不到 Anthropic 原生（claude.ai/anthropic 端点），LiteLLM 直通。
- LiteLLM 自带 cost tracking（`response._hidden_params["response_cost"]`），自维护单价表的成本被消除。
- Phase 4 要做的 fallback / retry / load balance LiteLLM 的 `Router` 类零代码支持。

**风险**：

- 抽象漏出：Gemini thinking blocks、Anthropic `cache_control`、各家 JSON mode 细节差异。→ Mitigation：业务层只用最小公共子集（`messages` + `temperature` + `max_tokens` + 可选 `response_format`）；provider 特异参数走 `extra_body` 透传；Phase 2 接 LangGraph 时具体场景再 case-by-case。
- 依赖体量：LiteLLM 拉一堆传递依赖。→ Mitigation：`uv add` 时审视 lockfile diff；如果太重再评估。
- 升级节奏快：1.x 小版本偶尔改默认行为。→ Mitigation：`pyproject.toml` 锁次版本（如 `>=1.86,<1.90`），升级时跑回归。

### 决策 2：保留 `BaseProvider` 抽象，`LiteLLMProvider` 作为后端

**为什么**：

- 业务层不应直接依赖 LiteLLM。万一未来 LiteLLM 不合适改回原生 SDK，只动 `LiteLLMProvider` 一个文件。
- `BaseProvider` 接口（`async generate(messages, **kwargs) -> GenerationResult`）已在 1a 验证，保持稳定。
- `OpenAIProvider` / `DeepSeekProvider` 在 Phase 2 完成迁移后删除，避免双轨维护。

**接口约定**：

```python
class LiteLLMProvider(BaseProvider):
    def __init__(
        self,
        model: str,                    # LiteLLM model string, e.g. "gemini/gemini-2.0-flash"
        api_key: str,
        base_url: str | None = None,   # for OpenAI-compatible custom endpoints
        default_kwargs: dict | None = None,  # provider-wide defaults (temperature etc.)
    ) -> None: ...

    async def generate(
        self,
        messages: list[Message],
        **kwargs: Any,                 # per-call overrides; passed through to litellm.acompletion
    ) -> GenerationResult: ...
```

`GenerationResult` 在 1a 基础上补 `cost_usd: float | None`（从 `_hidden_params["response_cost"]` 读，None 表示 LiteLLM 没有该 model 的单价）。

### 决策 3：env 命名沿用 1a embedding 解耦风格，按用途分段

**为什么**：

- 1a 已经把 embedding 解耦成 `EMBEDDING_*`，故事 / 审计 chat LLM 也按用途分段，命名一致，易读。
- "用途分段"而非"provider 分段"：业务关心"故事生成用什么"而不是"OpenAI 用什么"，前者是后者的上层。
- 部署者切 provider 改一个 env 段即可，不用改业务代码。

**配置项**（新增到 `Settings`）：

| Env | 含义 | 默认 |
|---|---|---|
| `STORY_LLM_MODEL` | LiteLLM model string | `gemini/gemini-2.0-flash` |
| `STORY_LLM_API_KEY` | 故事生成 API key | （空，必填） |
| `STORY_LLM_BASE_URL` | OpenAI 兼容自定义端点（可选） | （空） |
| `STORY_LLM_TEMPERATURE` | 默认温度 | `0.7` |
| `STORY_LLM_MAX_TOKENS` | 默认 max output tokens | `2048` |
| `AUDIT_LLM_MODEL` | LiteLLM model string | `deepseek/deepseek-chat` |
| `AUDIT_LLM_API_KEY` | 审计 API key | （空，必填） |
| `AUDIT_LLM_BASE_URL` | OpenAI 兼容自定义端点（可选） | （空） |
| `AUDIT_LLM_TEMPERATURE` | 默认温度 | `0.2` |
| `AUDIT_LLM_MAX_TOKENS` | 默认 max output tokens | `4096` |

`.env.example` 补几组样例（Gemini / OpenAI / DeepSeek / Qwen / 自定义 OpenAI 兼容），让用户复制粘贴即用。

### 决策 4：默认故事生成切到 Gemini，审计保留 DeepSeek

**为什么**：

- 用户 Gemini 额度宽松，是当前直接动机。
- 审计是独立信号源，跟故事生成换 provider 是好事（避免同一家服务波动同时影响两端）。DeepSeek 1a 测试链路稳定，无切换动机。
- 默认值仅是 `.env.example` 推荐，部署者按 env 任意切。

### 决策 5：旧 provider 模块标记 deprecated，Phase 2 完成迁移后删除

**为什么**：

- 双轨维护成本高且容易漂移。Phase 2 接 LangGraph 时直接走 `LiteLLMProvider`，老的 `OpenAIProvider` / `DeepSeekProvider` 就没业务用了。
- 1a 阶段它们只在测试里被用，删除影响面极小（mock 改成 mock LiteLLM 即可）。
- 删除时机：Phase 2 任务完成、所有 chat 调用走 `LiteLLMProvider`、回归通过后。本 change 不删（仅 Phase 2 任务 list 含此项）。

### 决策 6：不引入 LiteLLM Router / fallback（留作 Phase 4）

**为什么**：

- MVP 单 provider 已经够用，Router 是 fallback / load balance 场景才有意义。
- Phase 4 真要做 cost 控制时再统一引入（限速、配额、主备路由一起设计）。
- 提前引入会让配置 schema 复杂化，无收益。

**升级路径**：Phase 4 增加 `routes.yaml` 定义 model_list + fallback chain，`LiteLLMProvider` 内部从 `acompletion` 切到 `Router.acompletion`，业务层无感。

### 决策 7：范畴 A，不做用户级 BYOK

**为什么**：

- 当前是单人 / 单实例项目，用户级 BYOK 需要 user 表 / 密钥加密 / per-request 路由 / cost 归属，整个数据模型都要动。
- 范畴 A 已经覆盖"部署者按需配自己的 provider"这个核心动机，足够支撑 Phase 1-3。
- 范畴 B 留作独立 change `add-user-byok-chat-routing`，等真有多人协作场景或商业化诉求时再做。

## Risks / Trade-offs

- **[Risk] LiteLLM 抽象漏出**：provider 特异参数（thinking、cache_control、JSON mode 等）跨 provider 不一致。→ Mitigation：业务层只用最小子集；provider 特异参数走 `extra_body` 透传；Phase 2 业务接入时按场景验证。
- **[Risk] LiteLLM 升级 breaking change**：1.x 小版本偶尔改默认。→ Mitigation：`pyproject.toml` 锁次版本，升级走回归测试。
- **[Risk] cost tracking 不准**：LiteLLM 单价表对小众 provider 可能未覆盖或滞后。→ Mitigation：`cost_usd` 允许为 None；不依赖它做硬性配额（Phase 4 做配额时再补 fallback 计算）。
- **[Trade-off] 双 provider 配置 vs 单一配置**：故事 / 审计分两段配置看似冗余，但好处是允许两端跑不同 provider；如果都用一家完全可以两段写同样 env 值。
- **[Trade-off] 不做 Router / fallback**：单 provider 失效时无降级。→ 接受，Phase 4 统一做。

## Migration Plan

本 change 仅锁方向，不动代码。Phase 2 接 LangGraph 时按以下步骤落地：

1. **依赖安装**：`uv add 'litellm>=1.86,<1.90'`，运行 `uv sync` 锁定。
2. **配置扩展**：`.env.example` 与 `apps/api/app/config.py` 加 `STORY_LLM_*` / `AUDIT_LLM_*` 字段。
3. **Provider 实现**：新增 `services/providers/litellm_provider.py`，封装 `litellm.acompletion`；返回 `GenerationResult` 含 `cost_usd`。
4. **业务接入**：Phase 2 LangGraph 节点初始化 `LiteLLMProvider(STORY_LLM_*)` 和 `LiteLLMProvider(AUDIT_LLM_*)`；调用走 `provider.generate(messages, **kwargs)`。
5. **测试迁移**：`services/providers/tests/test_providers.py` 改为 mock `litellm.acompletion`；老的 `test_openai_provider` / `test_deepseek_provider` 删除或改为 LiteLLMProvider 端到端测试。
6. **删除旧 provider**：所有 chat 调用走 `LiteLLMProvider` 后，删 `openai_provider.py` / `deepseek_provider.py`。
7. **回滚**：保留 `BaseProvider` 抽象前提下，`LiteLLMProvider` 内部可改回原生 SDK；env schema 不变。

## Open Questions

- **`extra_body` 透传策略**：Phase 2 业务层直接透传，还是 `LiteLLMProvider` 维护一份 provider→默认 extra_body 的小映射？接 LangGraph 时再决定。
- **streaming**：MVP 故事生成是否需要 streaming（前端逐字显示）？如果需要，`LiteLLMProvider` 要加 `agenerate_stream`。Phase 2 业务侧确认后再补。
- **JSON mode / structured output**：审计场景大概率需要 JSON 输出。LiteLLM 的 `response_format={"type":"json_object"}` 在 OpenAI / DeepSeek 通，Gemini 要走 `response_mime_type` extra_body。Phase 2 接审计时再统一适配。
