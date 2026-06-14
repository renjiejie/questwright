## ADDED Requirements

### Requirement: 统一 chat LLM 路由后端

系统 SHALL 通过 LiteLLM 作为统一 chat LLM 后端，封装在 `LiteLLMProvider`（继承自现有 `BaseProvider`）中。业务层 MUST 仅依赖 `BaseProvider` 接口（`async generate(messages, **kwargs) -> GenerationResult`），不得直接 import `litellm`。

#### Scenario: 业务层不感知具体 provider

- **WHEN** 业务代码（如 LangGraph 故事生成节点）调用 `provider.generate(messages)`
- **THEN** 调用方代码与具体 provider（OpenAI / Gemini / DeepSeek / Qwen 等）无关；切换 provider 仅通过 env 配置完成，业务代码不变

#### Scenario: 通过 LiteLLM model 字符串切 provider

- **WHEN** `STORY_LLM_MODEL=gemini/gemini-2.0-flash` 时调用故事生成
- **THEN** 实际请求落到 Gemini；将值改为 `openai/gpt-4o-mini` 后调用同一业务代码，请求落到 OpenAI；其余调用方代码无变更

#### Scenario: OpenAI 兼容自定义端点

- **WHEN** `STORY_LLM_MODEL=openai/qwen-plus`、`STORY_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1`、`STORY_LLM_API_KEY=<DashScope key>`
- **THEN** 请求落到 DashScope OpenAI 兼容端点；`LiteLLMProvider` MUST 通过 `api_base` 参数把 `base_url` 透传给 `litellm.acompletion`

### Requirement: 故事与审计独立配置

系统 SHALL 把"故事生成"与"世界观审计"作为两个独立 LLM 用途，分别用 `STORY_LLM_*` 与 `AUDIT_LLM_*` env 段配置（`MODEL` / `API_KEY` / `BASE_URL` / `TEMPERATURE` / `MAX_TOKENS`）。两段 MUST 互不影响：可以指向不同 provider、不同 key、不同模型。

#### Scenario: 两端不同 provider 共存

- **WHEN** `STORY_LLM_MODEL=gemini/gemini-2.0-flash` 而 `AUDIT_LLM_MODEL=deepseek/deepseek-chat`
- **THEN** 故事生成请求走 Gemini；审计请求走 DeepSeek；两者各自从对应 env 段读 api_key 与 base_url

#### Scenario: 缺失必填 key 启动失败

- **WHEN** 启动时 `STORY_LLM_API_KEY` 或 `AUDIT_LLM_API_KEY` 任一为空
- **THEN** 应用启动失败并给出明确错误，指明缺失的字段名；不进入运行态

### Requirement: GenerationResult 暴露 cost 与 usage

系统 SHALL 在 `LiteLLMProvider.generate` 返回的 `GenerationResult` 上暴露：`text`（生成文本）、`usage`（含 `prompt_tokens` / `completion_tokens` / `total_tokens`）、`cost_usd`（美元成本，float 或 None）、`raw_response`（LiteLLM 原始响应，便于 debug）。`cost_usd` MUST 从 `response._hidden_params["response_cost"]` 读取；当 LiteLLM 未提供该字段（如未知 model）时，`cost_usd` MUST 为 None。

#### Scenario: 主流 provider 返回 cost

- **WHEN** 调用 `LiteLLMProvider(model="gemini/gemini-2.0-flash", ...)` 生成一段文本
- **THEN** 返回的 `GenerationResult.cost_usd` 为非负 float；`usage.total_tokens` 等于 `prompt_tokens + completion_tokens`

#### Scenario: 未知 model cost 为 None

- **WHEN** 调用一个 LiteLLM 单价表未覆盖的小众 model
- **THEN** `GenerationResult.cost_usd` 为 None；其余字段（text / usage）正常返回；不抛异常

### Requirement: 旧 provider 模块在迁移完成后移除

系统 SHALL 在 Phase 2 业务全量切到 `LiteLLMProvider` 后，移除 `services/providers/openai_provider.py` 与 `services/providers/deepseek_provider.py`，并清理对应测试。`BaseProvider` 抽象 MUST 保留（业务层依赖）；`__init__.py` 仅导出 `BaseProvider` 与 `LiteLLMProvider`。

#### Scenario: 不再有 import 旧 provider

- **WHEN** 迁移完成时全仓搜索 `from services.providers.openai_provider` 或 `from services.providers.deepseek_provider`
- **THEN** 仅 deprecated 标记或测试文件中可能存在临时引用，业务路径与 LangGraph 节点 MUST 全部走 `LiteLLMProvider`

#### Scenario: 删除后测试仍通过

- **WHEN** 删除旧 provider 模块与对应测试用例后，跑 `uv run pytest`
- **THEN** 全部通过；`LiteLLMProvider` 的单测覆盖原有 provider 测试中的关键路径（成功生成、api_key/base_url 透传、cost 提取）
