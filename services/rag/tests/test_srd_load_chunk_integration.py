from __future__ import annotations

import json
from pathlib import Path

from services.rag.chunkers import chunk_record
from services.rag.srd_loader import FILE_TO_SOURCE, iter_records


def test_all_srd_files_can_load_and_chunk(tmp_path: Path) -> None:
    for file_name in FILE_TO_SOURCE:
        payload = [{"index": file_name.lower(), "name": file_name, "desc": ["sample"]}]
        (tmp_path / file_name).write_text(json.dumps(payload), encoding="utf-8")

    records = list(iter_records(tmp_path))
    chunks = [chunk_record(record) for record in records]

    assert len(records) == len(FILE_TO_SOURCE)
    assert len(chunks) > 0
