## 1. 方向锁定（本 change 仅完成此节）

- [ ] 1.1 proposal / design / spec delta 经用户审阅通过
- [ ] 1.2 `openspec validate add-litellm-chat-router --strict` 通过

## 2. 依赖与配置（Phase 2 接 LangGraph 时执行）

- [ ] 2.1 `uv add 'litellm>=1.86,<1.90'`，运行 `uv sync` 锁定 lockfile
- [ ] 2.2 `apps/api/app/config.py` 的 `Settings` 新增字段：`STORY_LLM_MODEL` / `STORY_LLM_API_KEY` / `STORY_LLM_BASE_URL` / `STORY_LLM_TEMPERATURE` / `STORY_LLM_MAX_TOKENS` / `AUDIT_LLM_MODEL` / `AUDIT_LLM_API_KEY` / `AUDIT_LLM_BASE_URL` / `AUDIT_LLM_TEMPERATURE` / `AUDIT_LLM_MAX_TOKENS`
- [ ] 2.3 `.env.example` 补齐对应字段，附 5 组样例（Gemini / OpenAI / DeepSeek / Qwen / 自定义 OpenAI 兼容端点）
- [ ] 2.4 `Settings` 启动校验：`STORY_LLM_API_KEY` / `AUDIT_LLM_API_KEY` 必填，缺失给清晰错误

## 3. LiteLLMProvider 实现

- [ ] 3.1 新增 `services/providers/litellm_provider.py`：`LiteLLMProvider(BaseProvider)`，构造参数 `model` / `api_key` / `base_url` / `default_kwargs`
- [ ] 3.2 `async def generate(messages, **kwargs)` 调 `litellm.acompletion`；返回 `GenerationResult`（含 `text` / `usage` / `cost_usd` / `raw_response`）
- [ ] 3.3 `cost_usd` 从 `response._hidden_params.get("response_cost")` 读，缺失时填 None
- [ ] 3.4 `api_key` 通过 `litellm.acompletion` 的 `api_key` 参数传，不污染全局 env
- [ ] 3.5 `base_url` 通过 `api_base` 参数传（OpenAI 兼容端点用）
- [ ] 3.6 单测：mock `litellm.acompletion`，覆盖（a）成功路径返回 text + cost；（b）`api_key` / `api_base` 透传；（c）`extra_body` 透传；（d）cost 缺失时 `cost_usd is None`

## 4. 业务接入（Phase 2 LangGraph 节点）

- [ ] 4.1 故事生成节点初始化 `LiteLLMProvider` 用 `STORY_LLM_*` 配置；审计节点用 `AUDIT_LLM_*`
- [ ] 4.2 LangGraph 节点内调用 `provider.generate(messages, **kwargs)`，不直接依赖 `litellm`
- [ ] 4.3 端到端测试：默认 env（Gemini 故事 + DeepSeek 审计）跑通最小 brief 流程
- [ ] 4.4 切换测试：把 `STORY_LLM_MODEL` 改成 `openai/gpt-4o-mini` + 对应 key，回归通过

## 5. 旧 provider 清理

- [ ] 5.1 业务层全部走 `LiteLLMProvider` 后，删除 `services/providers/openai_provider.py` / `services/providers/deepseek_provider.py`
- [ ] 5.2 `services/providers/tests/test_providers.py` 删除老的 `test_openai_provider` / `test_deepseek_provider` 用例；保留 mock `litellm.acompletion` 的新测试
- [ ] 5.3 `services/providers/__init__.py` 移除旧 provider 导出

## 6. 归档前清单

- [ ] 6.1 `uv run pytest services/providers/tests` 全部通过
- [ ] 6.2 `.env.example` 与 README（如有）保持同步
- [ ] 6.3 用 OpenSpec archive 流程归档；spec promote 到 `openspec/specs/chat-llm-routing/`
