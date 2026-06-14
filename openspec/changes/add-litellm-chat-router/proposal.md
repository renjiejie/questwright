## Why

Phase 0/1a 把 chat LLM provider 抽象成 `BaseProvider` + `OpenAIProvider` / `DeepSeekProvider`，但每加一个 provider 就要写一份适配器，且没有统一 cost tracking、fallback、模型路由能力。本人当前想把"故事生成"换成 Gemini（额度更宽松），但更长期目标是允许部署者按 env 任意挑主流 AI（OpenAI / Gemini / DeepSeek / Qwen / Kimi / Anthropic / OpenRouter / 任意 OpenAI 兼容端点）。

直接把 chat 调用底层换成 [LiteLLM](https://github.com/BerriAI/litellm) 是当前最低成本的 generalize 路径：

- 一行 `model="gemini/gemini-2.0-flash"` / `"deepseek/deepseek-chat"` / `"openai/gpt-4o"` 切 provider，不再写新 SDK 适配。
- 内置 cost tracking（response 含 `_hidden_params["response_cost"]`），不用我们自己维护单价表。
- `Router` 类原生支持 fallback / retry / load balance，Phase 4 想做"主备 LLM"零额外代码。
- Embedding 路径已在 1a 走 OpenAI 兼容端点（DashScope）实现解耦，不属于本 change 范围。

本 change 仅改方案，不动代码。代码落地推迟到 Phase 2 接 LangGraph 时一起做（那时才有真实 chat 调用场景），但本 change 锁定方向，避免 Phase 2 重新选型。

## What Changes

- **新增 capability**：`chat-llm-routing`（chat LLM 调用统一路由层）。
- **依赖**：引入 `litellm`（PyPI 1.86.x，Python ≥3.10），Phase 2 实施时 `uv add`。
- **配置解耦**：故事生成与世界观审计分别走独立 env 段，沿用 1a embedding 解耦的命名风格（`STORY_LLM_*` / `AUDIT_LLM_*`），值都是 LiteLLM 的 `provider/model` 字符串。
- **Provider 抽象保留**：`BaseProvider` 接口不变，新增 `LiteLLMProvider` 作为通用后端；老的 `OpenAIProvider` / `DeepSeekProvider` 标记为 deprecated，Phase 2 切完后移除。
- **范畴 A（部署者 BYOK）**：本 change 只覆盖单实例运维者通过 env 配 key/model 的场景。终端用户 BYOK（每个玩家填自己的 key、per-request 路由）属于范畴 B，留作后续独立 change（`add-user-byok-chat-routing`）。
- **故事生成默认 provider 切到 Gemini**：默认 `STORY_LLM_MODEL=gemini/gemini-2.0-flash`，但任意 LiteLLM 支持的 provider 都可通过 env 切换。审计保留 DeepSeek 默认。
- **不做的事**：不改 embedding 路径（1a 已落地，DashScope OpenAI 兼容继续走原生 OpenAI SDK）；不引入 LiteLLM Proxy server；不做 cost 限额 / quota / 计量上报（Phase 4）。

## Impact

- **Affected specs**：新增 `chat-llm-routing`。
- **Affected code（Phase 2 落地时）**：
  - `services/providers/litellm_provider.py`（新增）
  - `services/providers/__init__.py`（导出 `LiteLLMProvider`、保留旧 provider 直到 Phase 2 完成迁移）
  - `apps/api/app/config.py`（新增 `STORY_LLM_*` / `AUDIT_LLM_*` 字段）
  - `.env.example`（新增配置示例 + 注释说明 Gemini / OpenAI / DeepSeek / Qwen 切换样例）
  - `pyproject.toml`（`uv add litellm`）
- **风险**：LiteLLM 抽象漏出（thinking blocks、prompt caching、JSON mode 边界差异）；依赖体量增加；升级节奏快需锁版本。详见 design.md。
