"""Load SRD records from local 5e-database JSON files."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from app.config import get_settings

from services.rag.schemas import RawSrdRecord

FILE_TO_SOURCE: dict[str, str] = {
    "5e-SRD-Ability-Scores.json": "phb",
    "5e-SRD-Alignments.json": "phb",
    "5e-SRD-Backgrounds.json": "phb",
    "5e-SRD-Classes.json": "phb",
    "5e-SRD-Conditions.json": "srd_misc",
    "5e-SRD-Damage-Types.json": "srd_misc",
    "5e-SRD-Equipment-Categories.json": "phb",
    "5e-SRD-Equipment.json": "phb",
    "5e-SRD-Features.json": "phb",
    "5e-SRD-Feats.json": "phb",
    "5e-SRD-Languages.json": "phb",
    "5e-SRD-Levels.json": "phb",
    "5e-SRD-Magic-Items.json": "srd_misc",
    "5e-SRD-Magic-Schools.json": "srd_misc",
    "5e-SRD-Monsters.json": "monster_manual",
    "5e-SRD-Proficiencies.json": "phb",
    "5e-SRD-Races.json": "phb",
    "5e-SRD-Rule-Sections.json": "dmg",
    "5e-SRD-Rules.json": "dmg",
    "5e-SRD-Skills.json": "phb",
    "5e-SRD-Spells.json": "phb",
    "5e-SRD-Subclasses.json": "phb",
    "5e-SRD-Subraces.json": "phb",
    "5e-SRD-Traits.json": "phb",
    "5e-SRD-Weapon-Properties.json": "phb",
}


def _resolve_srd_path(srd_path: str | Path | None) -> Path:
    path = Path(srd_path) if srd_path else Path(get_settings().SRD_DATA_PATH)
    if not path.exists() or not path.is_dir():
        raise ValueError(
            f"SRD_DATA_PATH is invalid: {path}. "
            "Set SRD_DATA_PATH to a valid 5e-database directory."
        )
    return path


def _category_from_file_name(file_name: str) -> str:
    stem = Path(file_name).stem
    if stem.startswith("5e-SRD-"):
        stem = stem[len("5e-SRD-") :]
    return stem.lower()


def _read_items(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, list):
        raise ValueError(f"SRD file must contain a JSON array: {path}")
    return [item for item in payload if isinstance(item, dict)]


def iter_records(srd_path: str | Path | None = None) -> Iterator[RawSrdRecord]:
    base_dir = _resolve_srd_path(srd_path)
    for file_path in sorted(base_dir.glob("5e-SRD-*.json")):
        file_name = file_path.name
        source = FILE_TO_SOURCE.get(file_name, "srd_misc")
        category = _category_from_file_name(file_name)
        for item in _read_items(file_path):
            record_index = str(item.get("index") or item.get("name") or "")
            name = str(item.get("name") or record_index or "unknown")
            yield RawSrdRecord(
                source=source,  # type: ignore[arg-type]
                file_name=file_name,
                category=category,
                index=record_index,
                name=name,
                raw_json=item,
            )
