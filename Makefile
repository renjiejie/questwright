# Convenience targets for local dev.
# Repo root must be on PYTHONPATH so `services.*` resolves; `apps/api` so
# `app.*` resolves. Pytest already configures these via pyproject; uvicorn /
# alembic / one-off scripts go through this file.

PY := uv run
PYTHONPATH := .:apps/api
export PYTHONPATH

.PHONY: install migrate api web test lint srd-update

install:
	uv sync
	pnpm install

migrate:
	$(PY) alembic upgrade head

api:
	$(PY) uvicorn app.main:app --reload --port 8765

web:
	pnpm --filter web dev

test:
	$(PY) pytest -q

lint:
	$(PY) ruff check .

# Pull SRD JSON snapshot. Idempotent; first run clones, subsequent runs pull.
srd-update:
	@if [ ! -d vendor/5e-database ]; then \
		git clone --depth 1 https://github.com/5e-bits/5e-database.git vendor/5e-database; \
	else \
		git -C vendor/5e-database pull --depth 1; \
	fi
