"""Loading a lot's documents, its later corrections and records, and the specification revisions."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

DOCUMENTS = {
    "certificate": "certificate_of_analysis.md",
    "batch_record": "batch_record.md",
    "deviation_log": "deviation_log.md",
}
SECTION_BY_FILE = {v: k for k, v in DOCUMENTS.items()}


@dataclass
class LotPackage:
    lot_id: str
    docs: dict[str, list[str]]  # section -> lines
    versions: dict[str, str] = field(default_factory=dict)  # section -> version, when not the original

    def line(self, section: str, number: int | None) -> str | None:
        lines = self.docs.get(section, [])
        if number is None or number < 1 or number > len(lines):
            return None
        return lines[number - 1]

    def numbered(self, section: str) -> str:
        return "\n".join(f"L{i:02d}: {text}" for i, text in enumerate(self.docs[section], start=1))

    def filename(self, section: str) -> str:
        return DOCUMENTS[section]

    def version_label(self) -> str:
        return ", ".join(f"{DOCUMENTS[s]} {v}" for s, v in sorted(self.versions.items())) or "originals"

    def fingerprint(self) -> str:
        """A hash of exactly what was read. A decision is only valid for this."""
        h = hashlib.sha256()
        for section in DOCUMENTS:
            h.update(section.encode())
            h.update("\n".join(self.docs[section]).encode())
        return h.hexdigest()[:16]


def list_lots(data_dir: Path) -> list[str]:
    return sorted(p.name for p in (data_dir / "lots").iterdir() if p.is_dir())


def corrections(data_dir: Path, lot_id: str) -> list[tuple[str, str]]:
    """Corrected document versions on file for a lot, as (section, version)."""
    folder = data_dir / "lots" / lot_id / "corrections"
    out = []
    for path in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        stem, _, version = path.stem.rpartition(".")
        if stem in {Path(f).stem for f in DOCUMENTS.values()} and version:
            out.append((SECTION_BY_FILE[stem + ".md"], version))
    return out


def load_lot(data_dir: Path, lot_id: str, versions: dict[str, str] | None = None) -> LotPackage:
    folder = data_dir / "lots" / lot_id
    if not folder.is_dir():
        raise FileNotFoundError(f"No lot package at {folder}")
    versions = dict(versions or {})
    docs = {}
    for section, name in DOCUMENTS.items():
        if section in versions:
            path = folder / "corrections" / f"{Path(name).stem}.{versions[section]}.md"
        else:
            path = folder / name
        docs[section] = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    return LotPackage(lot_id=lot_id, docs=docs, versions=versions)


def case_info(data_dir: Path, lot_id: str) -> dict:
    """The short human title and summary a reviewer sees in the queue."""
    path = data_dir / "lots" / lot_id / "case.yaml"
    info = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    return {"title": info.get("title", lot_id), "summary": info.get("summary", ""), "product_code": info.get("product_code", "")}


def list_records(data_dir: Path, lot_id: str) -> list[str]:
    folder = data_dir / "lots" / lot_id / "records"
    return sorted(p.name for p in folder.glob("*.md")) if folder.is_dir() else []


def read_record(data_dir: Path, lot_id: str, name: str) -> list[str] | None:
    if name not in list_records(data_dir, lot_id):
        return None
    return (data_dir / "lots" / lot_id / "records" / name).read_text(encoding="utf-8").splitlines()


# ------------------------------------------------------------ specifications


def load_specs(data_dir: Path, product_code: str = "FH-DBC-050") -> list[dict]:
    folder = data_dir / "spec" / product_code
    specs = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("rev-*.yaml"))]
    return sorted(specs, key=lambda s: str(s["effective_from"]))


def governing_spec(specs: list[dict], made_on: date | None) -> dict | None:
    """The revision in force on the date of manufacture, or None if no date or no match."""
    if made_on is None:
        return None
    for s in specs:
        start = s["effective_from"]
        end = s.get("effective_to")
        if start <= made_on and (end is None or made_on <= end):
            return s
    return None


def load_spec(data_dir: Path, product_code: str = "FH-DBC-050") -> dict:
    """The latest revision. Used where no date applies, such as reading prompts."""
    return load_specs(data_dir, product_code)[-1]
