from __future__ import annotations

from services.rag.chunkers import chunk_record
from services.rag.schemas import RawSrdRecord


def _record(
    category: str,
    name: str,
    payload: dict,
    file_name: str = "5e-SRD-Test.json",
) -> RawSrdRecord:
    return RawSrdRecord(
        source="srd_misc",
        file_name=file_name,
        category=category,
        index=name.lower().replace(" ", "-"),
        name=name,
        raw_json=payload,
    )


def test_monster_chunker_typical_record() -> None:
    chunk = chunk_record(
        RawSrdRecord(
            source="monster_manual",
            file_name="5e-SRD-Monsters.json",
            category="monsters",
            index="young-red-dragon",
            name="Young Red Dragon",
            raw_json={
                "challenge_rating": "10",
                "size": "Large",
                "type": "dragon",
                "armor_class": 18,
                "hit_points": 178,
                "actions": [
                    {"name": "Bite", "desc": "Melee attack dealing 2d10+6 piercing."},
                    {"name": "Fire Breath", "desc": "Exhales fire in a 30-foot cone."},
                ],
                "special_abilities": [
                    {"name": "Legendary Resistance", "desc": "3/day auto-save."},
                ],
            },
        )
    )
    assert chunk.chunk_type == "monster_statblock"
    assert chunk.metadata["cr"] == "10"
    assert "Fire Breath" in chunk.text


def test_monster_chunker_missing_fields() -> None:
    chunk = chunk_record(
        RawSrdRecord(
            source="monster_manual",
            file_name="5e-SRD-Monsters.json",
            category="monsters",
            index="kobold",
            name="Kobold",
            raw_json={},
        )
    )
    assert chunk.chunk_type == "monster_statblock"
    assert "Kobold" in chunk.text


def test_monster_chunker_empty_desc() -> None:
    chunk = chunk_record(
        RawSrdRecord(
            source="monster_manual",
            file_name="5e-SRD-Monsters.json",
            category="monsters",
            index="dummy",
            name="Dummy Monster",
            raw_json={"actions": [], "special_abilities": []},
        )
    )
    assert chunk.metadata["cr"] == ""


def test_spell_chunker_typical_record() -> None:
    chunk = chunk_record(
        _record(
            "spells",
            "Fireball",
            {
                "level": 3,
                "school": "evocation",
                "range": "150 feet",
                "components": "V,S,M",
                "desc": ["A bright streak flashes."],
                "higher_level": ["Damage increases by 1d6."],
            },
            file_name="5e-SRD-Spells.json",
        )
    )
    assert chunk.chunk_type == "spell_chunk"
    assert chunk.metadata["spell_level"] == 3
    assert "evocation" in chunk.text


def test_spell_chunker_missing_fields() -> None:
    chunk = chunk_record(
        _record("spells", "Unknown Spell", {}, file_name="5e-SRD-Spells.json")
    )
    assert chunk.chunk_type == "spell_chunk"
    assert "Unknown Spell" in chunk.text


def test_spell_chunker_empty_desc() -> None:
    chunk = chunk_record(
        _record(
            "spells",
            "Silent Spell",
            {"desc": [], "higher_level": []},
            file_name="5e-SRD-Spells.json",
        )
    )
    assert chunk.metadata["school"] is None


def test_class_feature_chunker_typical_record() -> None:
    chunk = chunk_record(
        _record("classes", "Wizard", {"desc": ["Scholarly spellcasters."]})
    )
    assert chunk.chunk_type == "classes_chunk"
    assert "Scholarly spellcasters." in chunk.text


def test_class_feature_chunker_missing_fields() -> None:
    chunk = chunk_record(_record("races", "Elf", {}))
    assert chunk.chunk_type == "races_chunk"
    assert "Elf" in chunk.text


def test_class_feature_chunker_empty_desc() -> None:
    chunk = chunk_record(_record("features", "Action Surge", {"desc": []}))
    assert chunk.metadata["category"] == "features"


def test_rule_chunker_typical_record() -> None:
    chunk = chunk_record(
        _record("rules", "Combat", {"desc": ["Turn order and initiative."]})
    )
    assert chunk.chunk_type == "rule_chunk"
    assert "initiative" in chunk.text


def test_rule_chunker_missing_fields() -> None:
    chunk = chunk_record(_record("rule-sections", "Movement", {}))
    assert chunk.chunk_type == "rule_chunk"
    assert "Movement" in chunk.text


def test_rule_chunker_empty_desc() -> None:
    chunk = chunk_record(_record("rules", "Resting", {"desc": []}))
    assert chunk.metadata["category"] == "rules"


def test_misc_chunker_typical_record() -> None:
    chunk = chunk_record(
        _record("magic-items", "Bag of Holding", {"desc": ["This bag has an interior."]})
    )
    assert chunk.chunk_type == "misc_chunk"
    assert "Bag of Holding" in chunk.text


def test_misc_chunker_missing_fields() -> None:
    chunk = chunk_record(_record("conditions", "Grappled", {}))
    assert chunk.chunk_type == "misc_chunk"
    assert "Grappled" in chunk.text


def test_misc_chunker_empty_desc() -> None:
    chunk = chunk_record(_record("equipment", "Longsword", {"desc": []}))
    assert chunk.metadata["category"] == "equipment"
