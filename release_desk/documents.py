"""Loading a lot's documents and the product specification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DOCUMENTS = {
    "certificate": "certificate_of_analysis.md",
    "batch_record": "batch_record.md",
    "deviation_log": "deviation_log.md",
}


@dataclass
class LotPackage:
    lot_id: str
    docs: dict[str, list[str]]  # section -> lines (1-indexed by position + 1)

    def line(self, section: str, number: int | None) -> str | None:
        lines = self.docs.get(section, [])
        if number is None or number < 1 or number > len(lines):
            return None
        return lines[number - 1]

    def numbered(self, section: str) -> str:
        return "\n".join(f"L{i:02d}: {text}" for i, text in enumerate(self.docs[section], start=1))

    def filename(self, section: str) -> str:
        return DOCUMENTS[section]


def list_lots(data_dir: Path) -> list[str]:
    return sorted(p.name for p in (data_dir / "lots").iterdir() if p.is_dir())


def load_lot(data_dir: Path, lot_id: str) -> LotPackage:
    folder = data_dir / "lots" / lot_id
    if not folder.is_dir():
        raise FileNotFoundError(f"No lot package at {folder}")
    docs = {}
    for section, name in DOCUMENTS.items():
        path = folder / name
        docs[section] = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    return LotPackage(lot_id=lot_id, docs=docs)


def load_spec(data_dir: Path, product_code: str = "FH-DBC-050") -> dict:
    return yaml.safe_load((data_dir / "spec" / f"{product_code}.yaml").read_text(encoding="utf-8"))
