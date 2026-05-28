"""Retrieval configuration loader.

Loads stage-based retrieval weights from `config/retrieval.yaml`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RETRIEVAL_CONFIG_PATH = PROJECT_ROOT / "config" / "retrieval.yaml"


class StageConfig(BaseModel):
    vector_weight: float = Field(ge=0)
    bm25_weight: float = Field(ge=0)
    source_weights: dict[str, float] = Field(default_factory=dict)


class RetrievalConfig(BaseModel):
    default: StageConfig
    world_audit: StageConfig

    def get_stage(self, stage: str | None) -> StageConfig:
        if not stage:
            return self.default
        return getattr(self, stage, self.default)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Retrieval config file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        payload = yaml.safe_load(f) or {}
    if not isinstance(payload, dict):
        raise ValueError("Retrieval config must be a mapping of stages.")
    return payload


@lru_cache(maxsize=1)
def get_retrieval_config(path: str | Path | None = None) -> RetrievalConfig:
    config_path = Path(path) if path else RETRIEVAL_CONFIG_PATH
    return RetrievalConfig.model_validate(_load_yaml(config_path))
