from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.rag.cli import main
from services.rag.srd_loader import iter_records


@pytest.fixture
def srd_fixture_dir(tmp_path: Path) -> Path:
    samples = {
        "5e-SRD-Monsters.json": [{"index": "young-red-dragon", "name": "Young Red Dragon"}],
        "5e-SRD-Spells.json": [{"index": "fireball", "name": "Fireball"}],
        "5e-SRD-Rules.json": [{"index": "combat", "name": "Combat"}],
        "5e-SRD-Magic-Items.json": [{"index": "bag-of-holding", "name": "Bag of Holding"}],
    }
    for file_name, payload in samples.items():
        (tmp_path / file_name).write_text(json.dumps(payload), encoding="utf-8")
    return tmp_path


def test_iter_records_maps_monsters_spells_rules_misc(srd_fixture_dir: Path) -> None:
    records = list(iter_records(srd_fixture_dir))
    mapping = {(r.file_name, r.index): (r.source, r.category) for r in records}

    assert mapping[("5e-SRD-Monsters.json", "young-red-dragon")] == (
        "monster_manual",
        "monsters",
    )
    assert mapping[("5e-SRD-Spells.json", "fireball")] == ("phb", "spells")
    assert mapping[("5e-SRD-Rules.json", "combat")] == ("dmg", "rules")
    assert mapping[("5e-SRD-Magic-Items.json", "bag-of-holding")] == (
        "srd_misc",
        "magic-items",
    )


def test_iter_records_raises_on_missing_dir(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    with pytest.raises(ValueError, match="SRD_DATA_PATH is invalid"):
        list(iter_records(missing))


def test_load_srd_dry_run_prints_per_file_counts(srd_fixture_dir: Path, capsys) -> None:
    exit_code = main(["load-srd", "--dry-run", "--srd-path", str(srd_fixture_dir)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "5e-SRD-Monsters.json\t1" in captured.out
    assert "5e-SRD-Spells.json\t1" in captured.out
