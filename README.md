# Questwright

人类把关的 DND 模组逐步生成系统。设计与实施细节见:

- [设计草案.md](设计草案.md)
- [实施方案.md](实施方案.md)

## 工具链

| 层 | 工具 | 备注 |
| --- | --- | --- |
| Python 包管理 | [uv](https://docs.astral.sh/uv/) | 自动建 `.venv/` 隔离,不污染本机 |
| JS/TS 包管理 | [pnpm](https://pnpm.io) workspace | 根级 `pnpm-workspace.yaml` |
| Python | 3.12(uv 自动下载) | |
| Node | 20+(本机 24 也兼容) | |

## 一次性初始化

```bash
uv sync           # 建 .venv 并装 Python 依赖
pnpm install      # 装 web workspace 依赖
cp .env.example .env  # 然后手动填 OPENAI_API_KEY / DEEPSEEK_API_KEY
```

## 开发服务器端口

本项目默认端口与本机其他项目错开:

| 服务 | 端口 | 启动命令 |
| --- | --- | --- |
| API (FastAPI) | **8765** | `uv run --directory apps/api uvicorn app.main:app --port 8765 --reload` |
| Web (Next.js) | **3765** | `pnpm --filter web dev` |

## 验收命令(Phase 0)

```bash
# 健康检查
curl http://localhost:8765/healthz   # → {"status":"ok","env":"dev"}

# 前端
curl -I http://localhost:3765        # → HTTP/1.1 200
```
